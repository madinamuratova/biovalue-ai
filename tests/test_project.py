"""A project joins a feedstock to the evidence library and reports what is missing or uncertain."""

import pytest
from pydantic import ValidationError

from backend.project import Project
from tests.conftest import make_feedstock, missing
from tests.test_evidence import UNVERIFIED, claim, library, pathway, record, requirement

NO_PHENOLIC_OH = make_feedstock(props={"phenolic_oh_mmol_per_g": None},
                                data_gaps=(missing("composition.phenolic_oh_mmol_per_g"),))

LIBRARY = library(
    pathways=(pathway(), pathway("polyurethanes", "PU"), pathway("carbon_materials", "CM")),
    records=(
        # resins: high quality, with a supported requirement on phenolic OH
        record(technical_requirements=(requirement(parameter="phenolic OH", property="phenolic_oh_mmol_per_g",
                                                   max=None, min=2.0),)),
        # polyurethanes: only a company publication
        record(id="EV-PU-01", pathway="polyurethanes", source_type="company_publication", quality="moderate",
               claims=(claim(),)),
        # carbon materials: nothing verified
        record(id="EV-CM-01", pathway="carbon_materials", **UNVERIFIED),
    ),
)


def make_project(**changes) -> Project:
    fields = dict(id="toy", name="Toy project", description="toy", feedstock=NO_PHENOLIC_OH, evidence=LIBRARY,
                  pathway_ids=("phenolic_resins", "polyurethanes", "carbon_materials"))
    fields.update(changes)
    return Project(**fields)


def test_missing_properties_come_from_supported_requirements():
    p = make_project()
    assert p.missing_properties("phenolic_resins") == ["phenolic_oh_mmol_per_g"]
    assert p.missing_properties("polyurethanes") == []
    assert make_project(feedstock=make_feedstock()).missing_properties("phenolic_resins") == []


def test_uncertainty_flags_cover_feedstock_and_evidence():
    flags = make_project().uncertainty_flags()
    assert flags[0].startswith("Feedstock data is fictional demo")
    assert any("Feedstock missing (medium): composition.phenolic_oh_mmol_per_g" in f for f in flags)
    assert any(f.startswith("phenolic_resins: the evidence sets a requirement on phenolic_oh_mmol_per_g") for f in flags)
    assert "polyurethanes: no high-quality evidence; the best available is 'moderate'." in flags
    assert "carbon_materials: no verified evidence yet." in flags


def test_project_pathways_must_exist_and_be_unique():
    with pytest.raises(ValidationError, match="unknown pathways"):
        make_project(pathway_ids=("phenolic_resins", "biofuel"))
    with pytest.raises(ValidationError, match="pathway twice"):
        make_project(pathway_ids=("phenolic_resins", "phenolic_resins"))
