"""Feedstock schema: one lignin-rich stream at one mill.

Every figure is a `Quantity`: a value (None when missing), a unit, how it was obtained (measured, estimated,
calculated, or a fictional assumption), an optional low/high range for its variability over a year, and
the measurement method where that matters. The profile checks itself when it loads:

- mass flows use known units, and dry matter matches wet quantity x (1 - moisture)
- composition percentages are on a dry basis, between 0 and 100, and don't add up to more than the whole
- every missing figure has a matching data-gap entry, and every data gap points at a real field
- a fictional demo profile can't contain "measured" figures, and a measured one can't contain fictional ones
"""

import re
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.models import Frozen, LigninProperty

QuantityBasis = Literal["measured", "estimated", "calculated", "fictional_assumption", "literature"]
AssetKind = Literal[
    "lignin_precipitation", "washing_and_filtration", "drying", "fractionation", "chemical_modification",
    "packaging_and_storage", "rail_or_port_access", "steam_and_power", "other",
]
MASS_FLOW_UNITS = {"t/yr": 1.0, "kt/yr": 1000.0}
DRY_PCT = "% of dry matter"
PROPERTY_UNITS: dict[str, str] = {
    "lignin_pct": DRY_PCT, "ash_pct": DRY_PCT, "sulfur_pct": DRY_PCT, "carbohydrates_pct": DRY_PCT,
    "mw_g_per_mol": "g/mol", "phenolic_oh_mmol_per_g": "mmol/g",
}
DRY_MATTER_TOLERANCE = 0.005  # dry matter may differ from wet x (1 - moisture) by 0.5% for rounding


class Quantity(Frozen):
    """One feedstock figure. `low`/`high` give its expected range over a year of normal operation."""

    value: float | None  # None when the figure is missing
    unit: str
    basis: QuantityBasis
    low: float | None = None
    high: float | None = None
    method: str = ""  # measurement basis or standard, e.g. what the lignin percentage includes
    note: str = ""
    source: str = ""  # key into FeedstockProfile.sources; required when basis is "literature"

    @model_validator(mode="after")
    def _check(self):
        if self.value is None:
            if self.low is not None or self.high is not None:
                raise ValueError("a missing figure can't have a range")
            return self
        lo = self.value if self.low is None else self.low
        hi = self.value if self.high is None else self.high
        if not lo <= self.value <= hi:
            raise ValueError(f"range must satisfy low <= value <= high (got {self.low}, {self.value}, {self.high})")
        return self

    def bounds(self) -> tuple[float, float] | None:
        if self.value is None:
            return None
        return (self.value if self.low is None else self.low, self.value if self.high is None else self.high)


class Composition(Frozen):
    """Composition of the dry matter. The fields named in models.LigninProperty are what quality specs check."""

    lignin_pct: Quantity  # its `method` must say what was measured (e.g. acid-insoluble + acid-soluble lignin)
    ash_pct: Quantity
    sulfur_pct: Quantity
    carbohydrates_pct: Quantity
    mw_g_per_mol: Quantity
    phenolic_oh_mmol_per_g: Quantity
    other: dict[str, Quantity] = Field(default_factory=dict)  # anything else on file, e.g. sodium

    @model_validator(mode="after")
    def _check(self):
        if not self.lignin_pct.method.strip():
            raise ValueError("lignin_pct needs its measurement basis in `method`")
        for name, unit in PROPERTY_UNITS.items():
            q = getattr(self, name)
            if q.unit != unit:
                raise ValueError(f"composition.{name} must be in '{unit}' (got '{q.unit}')")
            if unit == DRY_PCT and q.bounds() and not (0 <= q.bounds()[0] and q.bounds()[1] <= 100):
                raise ValueError(f"composition.{name} must stay between 0 and 100%")
        known = [getattr(self, n).value for n in ("lignin_pct", "ash_pct", "carbohydrates_pct")]
        if all(v is not None for v in known) and sum(known) > 101:  # 1 point of slack for rounding
            raise ValueError(f"lignin + ash + carbohydrates add up to {sum(known):g}%, more than the whole")
        return self


class Variability(Frozen):
    summary: str
    drivers: tuple[str, ...]


class CurrentUse(Frozen):
    route: Literal["recovery_boiler_fuel", "internal_fuel", "sold_as_fuel", "sold_as_material", "landfill", "other"]
    description: str


class ProcessingAsset(Frozen):
    kind: AssetKind
    name: str
    status: Literal["operating", "planned", "not_available"]
    capacity: Quantity | None = None
    note: str = ""


class GeographicMarket(Frozen):
    mill_location: str
    target_markets: tuple[str, ...]
    logistics: str


class DataGap(Frozen):
    """A missing or uncertain figure, why it matters, and how to close the gap."""

    field: str  # dotted path into the profile, e.g. "composition.phenolic_oh_mmol_per_g"
    issue: Literal["missing", "uncertain", "method_unclear", "fictional"]
    severity: Literal["low", "medium", "high"]
    impact: str
    next_step: str


class LiteratureSource(Frozen):
    """A published source behind literature-based figures, with the passages that support them (quoted verbatim)."""

    key: str
    citation: str
    url: str
    verified_on: str  # the date the URL was opened and the quotes were checked against the source's own text
    quotes: tuple[str, ...]

    @model_validator(mode="after")
    def _check(self):
        if not self.url.startswith("https://"):
            raise ValueError(f"source {self.key}: url must be https")
        if not self.quotes or not all(q.strip() for q in self.quotes):
            raise ValueError(f"source {self.key}: at least one verbatim quote is required")
        return self


class FeedstockProfile(Frozen):
    id: str
    name: str
    data_status: Literal["fictional_demo", "measured", "mixed", "literature_reference"]
    disclaimer: str
    feedstock_type: str
    wood_type: Literal["softwood", "hardwood", "mixed"]
    annual_wet_quantity: Quantity
    moisture_pct: Quantity  # % of the wet mass
    dry_matter: Quantity
    composition: Composition
    variability: Variability
    current_use: CurrentUse
    infrastructure: tuple[ProcessingAsset, ...]
    geographic_market: GeographicMarket
    data_gaps: tuple[DataGap, ...] = ()
    sources: tuple[LiteratureSource, ...] = ()  # for literature-based figures

    @model_validator(mode="after")
    def _check(self):
        for name in ("annual_wet_quantity", "dry_matter"):
            q = getattr(self, name)
            if q.unit not in MASS_FLOW_UNITS:
                raise ValueError(f"{name} must be in one of {list(MASS_FLOW_UNITS)} (got '{q.unit}')")
            if q.value is None or q.value <= 0:
                raise ValueError(f"{name} is required and must be positive")
        if self.moisture_pct.unit != "% of wet mass" or self.moisture_pct.value is None:
            raise ValueError("moisture_pct is required, in '% of wet mass'")
        lo, hi = self.moisture_pct.bounds()
        if not (0 <= lo and hi < 100):
            raise ValueError("moisture must be at least 0% and below 100%")

        expected = self._tonnes(self.annual_wet_quantity) * (1 - self.moisture_pct.value / 100)
        if abs(self.dry_matter_t_per_year - expected) > DRY_MATTER_TOLERANCE * expected:
            raise ValueError(f"dry matter {self.dry_matter_t_per_year:,.0f} t/yr doesn't match wet quantity x "
                             f"(1 - moisture) = {expected:,.0f} t/yr")

        quantities = dict(self.quantities())
        missing = {path for path, q in quantities.items() if q.value is None}
        flagged = {g.field for g in self.data_gaps if g.issue == "missing"}
        if missing - flagged:
            raise ValueError(f"missing figures need a data gap with issue 'missing': {sorted(missing - flagged)}")
        if flagged - missing:
            raise ValueError(f"data gaps marked 'missing' point at figures that have values: {sorted(flagged - missing)}")
        unknown = [g.field for g in self.data_gaps if not _path_exists(self, g.field)]
        if unknown:
            raise ValueError(f"data gaps point at fields that don't exist: {unknown}")

        bases = {q.basis for q in quantities.values()}
        if self.data_status == "fictional_demo":
            if "measured" in bases:
                raise ValueError("a fictional demo profile can't contain measured figures")
            if "fictional" not in self.disclaimer.lower():
                raise ValueError("a fictional demo profile's disclaimer must say it is fictional")
        if self.data_status == "measured" and "fictional_assumption" in bases:
            raise ValueError("a measured profile can't contain fictional assumptions")

        keys = [src.key for src in self.sources]
        if len(keys) != len(set(keys)):
            raise ValueError("source keys must be unique")
        for path, q in quantities.items():
            if q.basis == "literature" and q.value is not None and not q.source:
                raise ValueError(f"{path} is a literature value and needs a source")
            if q.source and q.source not in keys:
                raise ValueError(f"{path} cites source '{q.source}', which is not in the profile's sources")
        if self.data_status == "literature_reference":
            if bases & {"fictional_assumption", "measured"}:
                raise ValueError("a literature-based profile can't contain fictional or measured figures")
            if "literature" not in self.disclaimer.lower():
                raise ValueError("a literature-based profile's disclaimer must say it is literature-based")
        return self

    @staticmethod
    def _tonnes(q: Quantity) -> float:
        return q.value * MASS_FLOW_UNITS[q.unit]

    @property
    def dry_matter_t_per_year(self) -> float:
        return self._tonnes(self.dry_matter)

    @property
    def dry_lignin_t_per_year(self) -> float | None:
        lignin = self.composition.lignin_pct.value
        return None if lignin is None else self.dry_matter_t_per_year * lignin / 100

    def property_value(self, prop: LigninProperty) -> float | None:
        return getattr(self.composition, prop).value

    def has_operating(self, kind: AssetKind) -> bool:
        return any(a.kind == kind and a.status == "operating" for a in self.infrastructure)

    def quantities(self) -> Iterator[tuple[str, Quantity]]:
        """Every figure in the profile, with its dotted path."""
        yield from _walk(self, "")

    def missing_fields(self) -> list[str]:
        return [path for path, q in self.quantities() if q.value is None]


def _walk(obj: object, path: str) -> Iterator[tuple[str, Quantity]]:
    if isinstance(obj, Quantity):
        yield path, obj
    elif isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            yield from _walk(getattr(obj, name), f"{path}.{name}" if path else name)
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            yield from _walk(item, f"{path}[{i}]")
    elif isinstance(obj, dict):
        for key, item in obj.items():
            yield from _walk(item, f"{path}.{key}")


def get_path(obj: object, path: str) -> object:
    """The value at a dotted path such as 'composition.other.sodium_pct' or 'infrastructure[2].capacity'.
    Raises KeyError when the path doesn't resolve."""
    for part in path.split("."):
        m = re.fullmatch(r"(\w+)((?:\[\d+\])*)", part)
        if not m:
            raise KeyError(path)
        name, indexes = m.group(1), [int(i) for i in re.findall(r"\[(\d+)\]", m.group(2))]
        if isinstance(obj, BaseModel) and name in type(obj).model_fields:
            obj = getattr(obj, name)
        elif isinstance(obj, dict) and name in obj:
            obj = obj[name]
        else:
            raise KeyError(path)
        for i in indexes:
            if not isinstance(obj, (list, tuple)) or i >= len(obj):
                raise KeyError(path)
            obj = obj[i]
    return obj


def _path_exists(obj: object, path: str) -> bool:
    """True when a dotted path such as 'composition.other.sodium_pct' or 'infrastructure[2].capacity' resolves."""
    try:
        get_path(obj, path)
    except KeyError:
        return False
    return True
