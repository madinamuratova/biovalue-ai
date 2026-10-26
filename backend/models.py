"""Shared building blocks for BioValue AI's models.

Each module defines the models it owns:
- backend/feedstock.py: the feedstock profile
- backend/evidence.py: the evidence library and product pathways
- backend/calc.py: economic inputs, steps, and scenario results
- backend/scoring.py: the scoring rubric, assessments, and rankings
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

# Feedstock properties that technical requirements can refer to. Each one is a field of feedstock.Composition.
LigninProperty = Literal["lignin_pct", "ash_pct", "sulfur_pct", "carbohydrates_pct", "mw_g_per_mol", "phenolic_oh_mmol_per_g"]


class Frozen(BaseModel):
    """Immutable, and rejects unknown fields so a typo in a data file is an error, not a silent default."""

    model_config = ConfigDict(frozen=True, extra="forbid")
