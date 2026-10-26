"""Evidence library: what published sources say about each kraft lignin product pathway.

Each record is one source. It lists the claims the source supports, the technical requirements it states,
and its limitations, with an evidence-quality label. The library enforces these rules when it loads:

- a URL is included only after it was opened and checked; `url_verified_on` records the date
- a record without a verified URL is labelled 'unverified', and so is every claim and requirement in it
- a 'supported' claim or requirement carries the passage (or its location) that supports it
- a numeric threshold is allowed only on a supported requirement, so no unverified number can reach scoring
- 'high' quality is reserved for peer-reviewed work and government or national-lab reports; trade press and
  market-research summaries are at most 'low'
"""

import re
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from backend.models import Frozen, LigninProperty

EvidenceQuality = Literal["high", "moderate", "low", "unverified"]
SourceType = Literal[
    "peer_reviewed_article", "review_article", "government_or_lab_report", "company_publication", "trade_press",
    "market_research_summary",
]
ClaimStatus = Literal["supported", "unverified"]

QUALITY_LABELS: tuple[EvidenceQuality, ...] = ("high", "moderate", "low", "unverified")
HIGH_QUALITY_TYPES = {"peer_reviewed_article", "review_article", "government_or_lab_report"}
SECONDARY_TYPES = {"trade_press", "market_research_summary"}
PUBLISHED = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")  # YYYY, YYYY-MM, or YYYY-MM-DD
RECORD_ID = re.compile(r"EV-[A-Z]+-\d{2}")


class Claim(Frozen):
    text: str
    status: ClaimStatus
    support: str = ""  # quoted passage or its location in the source

    @model_validator(mode="after")
    def _check(self):
        if self.status == "supported" and not self.support.strip():
            raise ValueError(f"supported claim needs its supporting passage: {self.text!r}")
        return self


class TechnicalRequirement(Frozen):
    parameter: str  # e.g. "ash content"
    requirement: str  # as the source states it
    applies_to: str = ""  # the product it is for, when a pathway covers several (e.g. "carbon fiber precursor")
    property: LigninProperty | None = None  # the feedstock field it maps to, if any
    min: float | None = None  # only when the source states the number
    max: float | None = None
    status: ClaimStatus
    support: str = ""

    @model_validator(mode="after")
    def _check(self):
        if self.status == "supported" and not self.support.strip():
            raise ValueError(f"supported requirement needs its supporting passage: {self.parameter!r}")
        has_number = self.min is not None or self.max is not None
        if has_number and (self.status != "supported" or self.property is None):
            raise ValueError(f"numeric threshold for {self.parameter!r} must be supported and mapped to a feedstock property")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"requirement {self.parameter!r} has min above max")
        return self


class EvidenceRecord(Frozen):
    id: str  # EV-<PATHWAY CODE>-<two digits>, e.g. EV-PF-01
    pathway: str
    title: str
    publisher: str  # journal, agency, company, or outlet
    authors: str = ""
    published: str | None = None  # YYYY, YYYY-MM, or YYYY-MM-DD; None when unknown
    url: str | None = None  # only when verified
    url_verified_on: date | None = None
    source_type: SourceType
    quality: EvidenceQuality
    claims: tuple[Claim, ...] = Field(min_length=1)
    technical_requirements: tuple[TechnicalRequirement, ...] = ()
    limitations: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self):
        if not RECORD_ID.fullmatch(self.id):
            raise ValueError(f"record id {self.id!r} must look like EV-PF-01")
        if self.published is not None and not PUBLISHED.fullmatch(self.published):
            raise ValueError(f"{self.id}: published must be YYYY, YYYY-MM, or YYYY-MM-DD")
        if (self.url is None) != (self.url_verified_on is None):
            raise ValueError(f"{self.id}: a URL is included only with the date it was verified")
        if self.url is not None and not self.url.startswith("https://"):
            raise ValueError(f"{self.id}: URL must use https")
        if self.url is None and self.quality != "unverified":
            raise ValueError(f"{self.id}: a record without a verified URL must be labelled 'unverified'")
        if self.quality == "unverified" and any(
                c.status == "supported" for c in (*self.claims, *self.technical_requirements)):
            raise ValueError(f"{self.id}: an unverified record can't contain supported claims or requirements")
        if self.quality == "high" and self.source_type not in HIGH_QUALITY_TYPES:
            raise ValueError(f"{self.id}: 'high' quality is only for peer-reviewed work and government or lab reports")
        if self.source_type in SECONDARY_TYPES and self.quality in ("high", "moderate"):
            raise ValueError(f"{self.id}: {self.source_type} is at most 'low' quality")
        return self


class Pathway(Frozen):
    id: str
    code: str  # the letters used in its record ids, e.g. PF
    name: str
    description: str
    example_products: tuple[str, ...]
    incumbent_materials: tuple[str, ...]


class EvidenceLibrary(Frozen):
    quality_labels: dict[EvidenceQuality, str]  # what each label means
    pathways: tuple[Pathway, ...]
    records: tuple[EvidenceRecord, ...]

    @model_validator(mode="after")
    def _check(self):
        if set(self.quality_labels) != set(QUALITY_LABELS):
            raise ValueError(f"quality_labels must define exactly {list(QUALITY_LABELS)}")
        for kind, ids in (("pathway", [p.id for p in self.pathways]), ("record", [r.id for r in self.records])):
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {kind} ids")
        codes = {p.id: p.code for p in self.pathways}
        for r in self.records:
            if r.pathway not in codes:
                raise ValueError(f"{r.id} belongs to unknown pathway {r.pathway!r}")
            if not r.id.startswith(f"EV-{codes[r.pathway]}-"):
                raise ValueError(f"{r.id} should start with EV-{codes[r.pathway]}- for pathway {r.pathway}")
        empty = [p.id for p in self.pathways if not self.records_for(p.id)]
        if empty:
            raise ValueError(f"pathways without evidence: {empty}")
        return self

    def pathway(self, pathway_id: str) -> Pathway:
        for p in self.pathways:
            if p.id == pathway_id:
                return p
        raise KeyError(f"unknown pathway {pathway_id!r}. Known: {[p.id for p in self.pathways]}")

    def record(self, record_id: str) -> EvidenceRecord:
        for r in self.records:
            if r.id == record_id:
                return r
        raise KeyError(f"unknown evidence record {record_id!r}")

    def records_for(self, pathway_id: str) -> tuple[EvidenceRecord, ...]:
        return tuple(r for r in self.records if r.pathway == pathway_id)

    def requirements_for(self, pathway_id: str, supported_only: bool = True) -> list[tuple[str, TechnicalRequirement]]:
        """(record id, requirement) pairs for a pathway; by default only the supported ones."""
        return [(r.id, req) for r in self.records_for(pathway_id) for req in r.technical_requirements
                if req.status == "supported" or not supported_only]
