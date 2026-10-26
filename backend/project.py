"""A project: one feedstock, the evidence library, and the product pathways in scope.

`uncertainty_flags()` gathers, in plain language, everything a reader should know before trusting a result:
the feedstock's own data gaps, feedstock properties the evidence says matter but the profile doesn't report,
and pathways whose evidence is thin or unverified.
"""

from pydantic import Field, model_validator

from backend.calc import PathwayAssumptions, PathwayInputs, build_pathway_inputs
from backend.evidence import EvidenceLibrary
from backend.feedstock import FeedstockProfile
from backend.models import Frozen


class Project(Frozen):
    id: str
    name: str
    description: str
    feedstock: FeedstockProfile
    evidence: EvidenceLibrary
    pathway_ids: tuple[str, ...]
    economic_assumptions: dict[str, PathwayAssumptions] = Field(default_factory=dict)  # by pathway id

    @model_validator(mode="after")
    def _check(self):
        known = {p.id for p in self.evidence.pathways}
        unknown = [p for p in self.pathway_ids if p not in known]
        if unknown:
            raise ValueError(f"project lists unknown pathways: {unknown}")
        if len(set(self.pathway_ids)) != len(self.pathway_ids):
            raise ValueError("project lists a pathway twice")
        stray = sorted(set(self.economic_assumptions) - set(self.pathway_ids))
        if stray:
            raise ValueError(f"economic assumptions given for pathways not in the project: {stray}")
        for pid in self.pathway_ids:
            self.pathway_inputs(pid)  # fails early if the assumptions don't fit the feedstock (units, currencies)
        return self

    def pathway_inputs(self, pathway_id: str) -> PathwayInputs:
        """The economic inputs for one pathway: feedstock wet mass and moisture plus the supplied assumptions."""
        return build_pathway_inputs(pathway_id, self.feedstock, self.economic_assumptions.get(pathway_id),
                                    default_product=self.evidence.pathway(pathway_id).name)

    def missing_properties(self, pathway_id: str) -> list[str]:
        """Feedstock properties that a supported requirement for this pathway mentions but the profile lacks."""
        props = {req.property for _, req in self.evidence.requirements_for(pathway_id) if req.property}
        return sorted(p for p in props if self.feedstock.property_value(p) is None)

    def uncertainty_flags(self) -> list[str]:
        flags = []
        if self.feedstock.data_status != "measured":
            flags.append(f"Feedstock data is {self.feedstock.data_status.replace('_', ' ')}: {self.feedstock.disclaimer}")
        for gap in self.feedstock.data_gaps:
            flags.append(f"Feedstock {gap.issue} ({gap.severity}): {gap.field}. {gap.impact}")
        for pid in self.pathway_ids:
            name = self.evidence.pathway(pid).name
            for prop in self.missing_properties(pid):
                flags.append(f"{name}: the evidence sets a requirement on {prop}, but the feedstock profile doesn't report it.")
            records = self.evidence.records_for(pid)
            verified = [r for r in records if r.quality != "unverified"]
            if not verified:
                flags.append(f"{name}: no verified evidence yet.")
            elif not any(r.quality == "high" for r in verified):
                best = "moderate" if any(r.quality == "moderate" for r in verified) else "low"
                flags.append(f"{name}: no high-quality evidence; the best available is '{best}'.")
        return flags
