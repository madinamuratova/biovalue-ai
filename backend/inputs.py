"""Turning dashboard input into a validated project.

The dashboard edits a copy of the feedstock record (the same JSON as data/demo_feedstock.json) and, optionally,
economic assumptions for each pathway. Before validation the server:

- recalculates dry matter from the wet quantity and moisture, so the two can't disagree
- labels every figure's basis from the chosen data source (fictional demo, measured, or mixed)
- keeps the data-gap list in step with the form: a blank figure gets a 'missing' gap, a filled one loses it

Everything else is checked by the same schemas as the files in data/. Problems come back as a list of
{field, message} pairs the form can show next to the right input.
"""

import copy

from pydantic import ValidationError

from backend import calc, data
from backend.config import MAX_LIST_ITEMS, MAX_TEXT_CHARS
from backend.feedstock import FeedstockProfile
from backend.project import Project

BASIS_FOR_STATUS = {"fictional_demo": "fictional_assumption", "measured": "measured", "mixed": "estimated"}
USER_DISCLAIMER = "Values entered by the user in the BioValue AI dashboard; not independently verified."
DRY_MATTER_METHOD = "Calculated by the server: annual wet quantity x (1 - moisture)"


class InputError(ValueError):
    """Input that failed validation, with one {field, message} entry per problem."""

    def __init__(self, errors: list[dict]):
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))
        self.errors = errors


MESSAGE_ALIASES = {"moisture": "moisture_pct", "dry matter": "dry_matter", "lignin + ash": "composition.lignin_pct"}


def _field_named_in(message: str, loc: str, paths: list[str]) -> str:
    """Model-level checks report no field of their own; find the field their message names, so the form can show
    the error next to the right input."""
    for path in sorted(paths, key=len, reverse=True):
        leaf = path.rsplit(".", 1)[-1]
        if (path in message or leaf in message) and path.startswith(loc):
            return path
    for alias, path in MESSAGE_ALIASES.items():
        if message.startswith(alias) and path.startswith(loc):
            return path
    return loc


def _from_validation(exc: ValidationError, prefix: str, paths: list[str] | None = None) -> InputError:
    errors = []
    for e in exc.errors():
        loc = ".".join(str(p) for p in e["loc"])
        message = e["msg"].removeprefix("Value error, ")
        if paths and (not loc or loc == "composition"):
            loc = _field_named_in(message, loc, paths)
        errors.append({"field": f"{prefix}.{loc}" if loc else prefix, "message": message})
    return InputError(errors)


def _quantity_slots(d: dict) -> list[tuple[str, dict]]:
    """Every figure in a feedstock dict, with its dotted path (the same paths the schema uses)."""
    slots = [(k, d[k]) for k in ("annual_wet_quantity", "moisture_pct", "dry_matter") if isinstance(d.get(k), dict)]
    comp = d.get("composition") or {}
    slots += [(f"composition.{k}", v) for k, v in comp.items() if k != "other" and isinstance(v, dict)]
    slots += [(f"composition.other.{k}", v) for k, v in (comp.get("other") or {}).items() if isinstance(v, dict)]
    slots += [(f"infrastructure[{i}].capacity", a["capacity"]) for i, a in enumerate(d.get("infrastructure") or [])
              if isinstance(a, dict) and isinstance(a.get("capacity"), dict)]
    return slots


def _dry_matter(wet: dict, moisture: dict) -> dict | None:
    try:
        def dry(w, m):
            return round(calc.dry_mass(w, wet["unit"], m, moisture["unit"]), 6)

        value = dry(wet["value"], moisture["value"])
        ranged = any(x.get(k) is not None for x in (wet, moisture) for k in ("low", "high"))
        low = dry(wet.get("low") or wet["value"], moisture.get("high") or moisture["value"]) if ranged else None
        high = dry(wet.get("high") or wet["value"], moisture.get("low") or moisture["value"]) if ranged else None
    except (KeyError, TypeError, ValueError):
        return None  # the schema check below reports what is wrong with the wet quantity or moisture
    return {"value": value, "low": low, "high": high, "unit": "t/yr", "basis": "calculated", "method": DRY_MATTER_METHOD,
            "note": "Recalculated from the wet quantity and moisture."}


def prepare_feedstock(raw: dict) -> FeedstockProfile:
    """Validate a feedstock edited in the dashboard. Raises InputError with field-level messages."""
    d = copy.deepcopy(raw)
    status = d.get("data_status", "fictional_demo")
    basis = BASIS_FOR_STATUS.get(status, "estimated")
    for path, q in _quantity_slots(d):
        if path != "dry_matter":
            q["basis"] = basis
    dry = _dry_matter(d.get("annual_wet_quantity") or {}, d.get("moisture_pct") or {})
    if dry is not None:
        d["dry_matter"] = dry

    missing_now = {path for path, q in _quantity_slots(d) if q.get("value") is None}
    gaps = [g for g in d.get("data_gaps") or [] if isinstance(g, dict)]
    kept = [g for g in gaps if g.get("issue") != "missing" or g.get("field") in missing_now]
    if status != "fictional_demo":
        kept = [g for g in kept if g.get("issue") != "fictional"]
    covered = {g.get("field") for g in kept if g.get("issue") == "missing"}
    kept += [{"field": path, "issue": "missing", "severity": "medium",
              "impact": "Left blank in the input form, so it can't be checked against any requirement.",
              "next_step": "Measure or obtain this value."} for path in sorted(missing_now - covered)]
    d["data_gaps"] = kept
    if status != "fictional_demo":
        d["disclaimer"] = USER_DISCLAIMER
    elif "fictional" not in str(d.get("disclaimer", "")).lower():
        d["disclaimer"] = "Fictional demo data, edited in the dashboard: illustrative values, not measurements."
    try:
        return FeedstockProfile.model_validate(d)
    except ValidationError as exc:
        raise _from_validation(exc, "feedstock", [path for path, _ in _quantity_slots(d)]) from None


def size_problems(value, path: str = "") -> list[dict]:
    """Text fields longer than MAX_TEXT_CHARS and lists longer than MAX_LIST_ITEMS, as {field, message} errors."""
    if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
        return [{"field": path, "message": f"Too long: {len(value):,} characters (limit {MAX_TEXT_CHARS:,})."}]
    if isinstance(value, list):
        errors = [{"field": path, "message": f"Too many items: {len(value)} (limit {MAX_LIST_ITEMS})."}] if len(value) > MAX_LIST_ITEMS else []
        for i, v in enumerate(value[:MAX_LIST_ITEMS + 1]):
            errors += size_problems(v, f"{path}[{i}]")
        return errors
    if isinstance(value, dict):
        if len(value) > MAX_LIST_ITEMS * 4:
            return [{"field": path, "message": f"Too many fields: {len(value)}."}]
        return [e for k, v in value.items() for e in size_problems(v, f"{path}.{k}" if path else str(k))]
    return []


def build_project(body: dict) -> Project:
    """A project from dashboard input: the edited feedstock and economic assumptions, with the demo project's
    evidence library and pathways. Missing parts fall back to the demo project."""
    if problems := size_problems(body):
        raise InputError(problems[:20])
    demo = data.project()
    feedstock = prepare_feedstock(body["feedstock"]) if body.get("feedstock") is not None else demo.feedstock
    raw = body.get("economic_assumptions")
    if raw is None:
        return demo.model_copy(update={"feedstock": feedstock, "id": "dashboard",
                                       "name": f"{feedstock.name}: dashboard assessment"})
    errors, assumptions = [], {}
    for pid, value in raw.items():
        prefix = f"economic_assumptions.{pid}"
        if pid not in demo.pathway_ids:
            errors.append({"field": prefix, "message": f"unknown pathway; use one of {list(demo.pathway_ids)}"})
            continue
        try:
            assumptions[pid] = calc.PathwayAssumptions.model_validate(value)
            calc.build_pathway_inputs(pid, feedstock, assumptions[pid], default_product=pid)
        except ValidationError as exc:
            errors += _from_validation(exc, prefix).errors
    if errors:
        raise InputError(errors)
    return Project(id="dashboard", name=f"{feedstock.name}: dashboard assessment", description=demo.description,
                   feedstock=feedstock, evidence=demo.evidence, pathway_ids=demo.pathway_ids,
                   economic_assumptions=assumptions)
