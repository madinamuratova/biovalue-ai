"""The evidence schema: verified URLs, supported claims, numeric thresholds, quality labels, and the library."""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.evidence import Claim, EvidenceLibrary, EvidenceRecord, Pathway, TechnicalRequirement

LABELS = {"high": "h", "moderate": "m", "low": "l", "unverified": "u"}


def claim(status: str = "supported") -> Claim:
    return Claim(text="toy claim", status=status, support="toy passage, p. 3" if status == "supported" else "")


def requirement(**changes) -> TechnicalRequirement:
    fields = dict(parameter="ash content", requirement="below 1%", property="ash_pct", max=1.0,
                  status="supported", support="Table 2")
    fields.update(changes)
    return TechnicalRequirement(**fields)


def record(**changes) -> EvidenceRecord:
    fields = dict(
        id="EV-PF-01", pathway="phenolic_resins", title="Toy paper", publisher="Toy Journal", published="2020",
        url="https://example.org/paper", url_verified_on=date(2026, 10, 24), source_type="peer_reviewed_article",
        quality="high", claims=(claim(),), limitations=("toy limitation",),
    )
    fields.update(changes)
    return EvidenceRecord(**fields)


def pathway(pid: str = "phenolic_resins", code: str = "PF") -> Pathway:
    return Pathway(id=pid, code=code, name=pid, description="toy", example_products=(), incumbent_materials=())


def library(records=None, pathways=None, labels=None) -> EvidenceLibrary:
    return EvidenceLibrary(quality_labels=labels or LABELS, pathways=pathways or (pathway(),),
                           records=records if records is not None else (record(),))


UNVERIFIED = dict(url=None, url_verified_on=None, quality="unverified", claims=(claim("unverified"),))


# --- Records ---------------------------------------------------------------------------------


def test_valid_record():
    assert record().quality == "high"


def test_unverified_record_without_url_is_accepted():
    r = record(**UNVERIFIED)
    assert r.url is None and r.quality == "unverified"


@pytest.mark.parametrize("bad_id", ["PF-01", "EV-pf-01", "EV-PF-1", "EV-PF-001"])
def test_record_id_format(bad_id):
    with pytest.raises(ValidationError, match="must look like EV-PF-01"):
        record(id=bad_id)


@pytest.mark.parametrize("published, ok", [("2020", True), ("2020-05", True), ("2020-05-17", True), (None, True),
                                           ("May 2020", False), ("20", False)])
def test_published_format(published, ok):
    if ok:
        assert record(published=published).published == published
    else:
        with pytest.raises(ValidationError, match="published must be"):
            record(published=published)


def test_url_needs_its_verification_date():
    with pytest.raises(ValidationError, match="only with the date it was verified"):
        record(url_verified_on=None)
    with pytest.raises(ValidationError, match="only with the date it was verified"):
        record(url=None)


def test_url_must_use_https():
    with pytest.raises(ValidationError, match="https"):
        record(url="http://example.org/paper")


def test_record_without_verified_url_must_be_unverified():
    with pytest.raises(ValidationError, match="must be labelled 'unverified'"):
        record(url=None, url_verified_on=None)


def test_unverified_record_cannot_hold_supported_claims():
    with pytest.raises(ValidationError, match="can't contain supported"):
        record(**{**UNVERIFIED, "claims": (claim("supported"),)})
    with pytest.raises(ValidationError, match="can't contain supported"):
        record(**UNVERIFIED, technical_requirements=(requirement(),))


def test_supported_claim_needs_its_passage():
    with pytest.raises(ValidationError, match="needs its supporting passage"):
        Claim(text="toy claim", status="supported")


def test_record_needs_a_claim_and_a_limitation():
    with pytest.raises(ValidationError):
        record(claims=())
    with pytest.raises(ValidationError):
        record(limitations=())


@pytest.mark.parametrize("source_type", ["company_publication", "trade_press", "market_research_summary"])
def test_high_quality_is_only_for_peer_reviewed_or_official_work(source_type):
    with pytest.raises(ValidationError):
        record(source_type=source_type, quality="high")


@pytest.mark.parametrize("source_type", ["trade_press", "market_research_summary"])
def test_secondary_sources_are_at_most_low(source_type):
    with pytest.raises(ValidationError, match="at most 'low'"):
        record(source_type=source_type, quality="moderate")
    assert record(source_type=source_type, quality="low").quality == "low"


# --- Technical requirements ---------------------------------------------------------------------


def test_numeric_threshold_must_be_supported():
    with pytest.raises(ValidationError, match="must be supported and mapped"):
        requirement(status="unverified", support="")


def test_numeric_threshold_must_map_to_a_feedstock_property():
    with pytest.raises(ValidationError, match="must be supported and mapped"):
        requirement(property=None)


def test_text_only_requirement_can_be_unverified():
    r = requirement(property=None, max=None, status="unverified", support="", requirement="low ash")
    assert r.max is None and r.status == "unverified"


def test_requirement_min_cannot_exceed_max():
    with pytest.raises(ValidationError, match="min above max"):
        requirement(min=2.0, max=1.0)


# --- Library ---------------------------------------------------------------------------------


def test_library_lookups():
    lib = library(records=(record(technical_requirements=(requirement(),)),
                           record(id="EV-PF-02", **UNVERIFIED,
                                  technical_requirements=(requirement(property=None, max=None, status="unverified", support=""),))))
    assert lib.pathway("phenolic_resins").code == "PF"
    assert lib.record("EV-PF-02").quality == "unverified"
    assert [r.id for r in lib.records_for("phenolic_resins")] == ["EV-PF-01", "EV-PF-02"]
    assert [rid for rid, _ in lib.requirements_for("phenolic_resins")] == ["EV-PF-01"]
    assert [rid for rid, _ in lib.requirements_for("phenolic_resins", supported_only=False)] == ["EV-PF-01", "EV-PF-02"]
    with pytest.raises(KeyError):
        lib.pathway("nope")
    with pytest.raises(KeyError):
        lib.record("EV-PF-99")


def test_quality_labels_must_all_be_defined():
    with pytest.raises(ValidationError):
        library(labels={"high": "h"})


def test_record_must_belong_to_a_known_pathway():
    with pytest.raises(ValidationError, match="unknown pathway"):
        library(records=(record(pathway="biofuel"),))


def test_record_id_must_use_its_pathway_code():
    with pytest.raises(ValidationError, match="should start with EV-PF-"):
        library(records=(record(id="EV-PU-01"),))


def test_every_pathway_needs_evidence():
    with pytest.raises(ValidationError, match="pathways without evidence"):
        library(pathways=(pathway(), pathway("polyurethanes", "PU")))


def test_ids_must_be_unique():
    with pytest.raises(ValidationError, match="duplicate record ids"):
        library(records=(record(), record()))
    with pytest.raises(ValidationError, match="duplicate pathway ids"):
        library(pathways=(pathway(), pathway()))
