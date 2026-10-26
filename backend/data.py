"""Load and validate the data in data/.

Every file is checked against its schema when it loads, so a missing figure without a data gap, an
unverified URL, or weights that don't sum to 1 stop the app instead of producing a bad answer. Each file
has an "about" string for readers; the loader ignores it.
"""

import json
from functools import lru_cache

from backend.config import DATA_DIR
from backend.evidence import EvidenceLibrary
from backend.feedstock import FeedstockProfile
from backend.project import Project
from backend.scoring import ScoringConfig

DEMO_PROJECT_FILE = "demo_project.json"
SCORING_FILE = "scoring_config.json"


def _read(name: str) -> dict:
    data = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    data.pop("about", None)
    return data


@lru_cache
def feedstock(name: str) -> FeedstockProfile:
    return FeedstockProfile.model_validate(_read(name))


@lru_cache
def evidence_library(name: str) -> EvidenceLibrary:
    return EvidenceLibrary.model_validate(_read(name))


@lru_cache
def scoring_config() -> ScoringConfig:
    return ScoringConfig.model_validate(_read(SCORING_FILE))


@lru_cache
def project(name: str = DEMO_PROJECT_FILE) -> Project:
    """A project manifest names its feedstock file, evidence file, and the pathways in scope."""
    manifest = _read(name)
    return Project(
        id=manifest["id"],
        name=manifest["name"],
        description=manifest["description"],
        feedstock=feedstock(manifest["feedstock_file"]),
        evidence=evidence_library(manifest["evidence_file"]),
        pathway_ids=tuple(manifest["pathways"]),
        economic_assumptions=manifest.get("economic_assumptions", {}),
    )
