"""Turn a scenario in evals/scenarios.json into dashboard-style inputs and a validated project.

Scenarios are written as changes to the fictional demo project:
    feedstock_set            dotted path -> figure (value, low, high, unit); basis follows the data source
    feedstock_set_text       dotted path -> text ("LONG_1500" means 1,500 characters)
    feedstock_set_list       dotted path -> number of generated list items
    feedstock_blank          dotted paths of figures to leave blank (missing)
    economic_assumptions     replaces all economic assumptions
    economic_assumptions_set pathway id -> assumptions, merged into the demo's
    evidence_add             synthetic evidence records added to the library (clearly labelled test fixtures)
"""

import copy
import json
from pathlib import Path

from backend import data
from backend.config import DATA_DIR
from backend.evidence import EvidenceLibrary
from backend.inputs import build_project

SCENARIOS_FILE = Path(__file__).resolve().parent / "scenarios.json"


def load_scenarios() -> dict:
    return json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))


def _set_path(d: dict, path: str, value) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def _get_path(d: dict, path: str):
    for part in path.split("."):
        d = d[part]
    return d


def demo_inputs() -> dict:
    feedstock = json.loads((DATA_DIR / "demo_feedstock.json").read_text(encoding="utf-8"))
    feedstock.pop("about")
    demo = data.project()
    return {"feedstock": feedstock,
            "economic_assumptions": {k: v.model_dump(mode="json", exclude_none=True) for k, v in demo.economic_assumptions.items()}}


def build_inputs(spec: dict) -> dict:
    """Dashboard-style inputs ({feedstock, economic_assumptions}) for one scenario or API request spec."""
    inputs = demo_inputs()
    fs = inputs["feedstock"]
    for path, figure in spec.get("feedstock_set", {}).items():
        current = copy.deepcopy(_get_path(fs, path)) if _exists(fs, path) else {"basis": "fictional_assumption"}
        current.update({"low": None, "high": None, **figure})
        _set_path(fs, path, current)
    for path in spec.get("feedstock_blank", []):
        q = _get_path(fs, path)
        q.update({"value": None, "low": None, "high": None})
    for path, text in spec.get("feedstock_set_text", {}).items():
        _set_path(fs, path, "x" * 1_500 if text == "LONG_1500" else text)
    for path, count in spec.get("feedstock_set_list", {}).items():
        _set_path(fs, path, [f"market {i}" for i in range(count)])
    if "economic_assumptions" in spec:
        inputs["economic_assumptions"] = copy.deepcopy(spec["economic_assumptions"])
    for pid, assumptions in spec.get("economic_assumptions_set", {}).items():
        inputs["economic_assumptions"][pid] = copy.deepcopy(assumptions)
    return inputs


def _exists(d: dict, path: str) -> bool:
    try:
        _get_path(d, path)
        return True
    except (KeyError, TypeError):
        return False


def build_scenario_project(scenario: dict):
    """The validated project for a live scenario, through the same input path the API uses."""
    inputs = build_inputs(scenario.get("inputs", {}))
    project = build_project(inputs)
    added = scenario.get("inputs", {}).get("evidence_add")
    if added:
        lib = project.evidence.model_dump(mode="json")
        lib["records"] += copy.deepcopy(added)
        project = project.model_copy(update={"evidence": EvidenceLibrary.model_validate(lib)})
    return project, inputs
