"""Evidence references and the number check.

Agents cite evidence by reference instead of copying it:

    EV-PF-01#2                  claim 2 of evidence record EV-PF-01
    EV-PF-01#R1                 technical requirement 1 of record EV-PF-01
    feedstock:composition.ash_pct   a field of the feedstock record
    feedstock:constraints[0]        a field of the Feedstock Agent's validated findings

Code resolves every reference, so an agent can't cite a record, claim, or field that doesn't exist. The number
check then makes sure every number an agent writes appears in what it cited or in a deterministic tool result.
"""

import json
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from backend.feedstock import get_path
from backend.project import Project

EVIDENCE_REF = re.compile(r"(EV-[A-Z]+-\d{2})#(R?)(\d+)")
FEEDSTOCK_PREFIX = "feedstock:"
REF_HELP = ("Use EV-PF-01#2 for claim 2 of a record, EV-PF-01#R1 for its requirement 1, or feedstock:<field path> for "
            "the feedstock record or the Feedstock Agent's findings.")

# A number not glued to a letter or another number: skips 'CO2', 'H2SO4', 'PF2'; reads '1,000' and '0.25' whole.
NUMBER = re.compile(r"(?<![A-Za-z0-9_.,])\d+(?:,\d{3})*(?:\.\d+)?")
# References and ids contain digits that are not claims about the world.
NOT_NUMBERS = re.compile(r"EV-[A-Z]+-\d{2}(?:#R?\d+)?|feedstock:[\w.\[\]]+|\b\d{4}-\d{2}-\d{2}\b")


@dataclass(frozen=True)
class Resolved:
    ref: str
    kind: Literal["claim", "requirement", "feedstock"]
    record_id: str | None
    pathway_id: str | None  # None for feedstock references, which apply to every pathway
    supported: bool
    text: str  # what the reference points at; numbers in it may be repeated by the agent


def resolve(project: Project, ref: str, feedstock_findings: BaseModel | None = None) -> Resolved:
    """Resolve one reference. A feedstock: path is looked up in the feedstock record, then in the Feedstock Agent's
    validated findings when they are given. Raises ValueError with a message the agent can act on."""
    ref = ref.strip()
    if ref.startswith(FEEDSTOCK_PREFIX):
        path = ref[len(FEEDSTOCK_PREFIX):]
        value, found = None, False
        for source in (project.feedstock, feedstock_findings):
            if source is None:
                continue
            try:
                value, found = get_path(source, path), True
                break
            except KeyError:
                continue
        if not found:
            where = "the feedstock record or the Feedstock Agent's findings" if feedstock_findings else "the feedstock record"
            raise ValueError(f"{ref}: no such field in {where}")
        dumped = value.model_dump() if isinstance(value, BaseModel) else value
        return Resolved(ref, "feedstock", None, None, True, json.dumps(dumped, default=str))
    m = EVIDENCE_REF.fullmatch(ref)
    if not m:
        raise ValueError(f"{ref!r} is not a reference. {REF_HELP}")
    try:
        record = project.evidence.record(m.group(1))
    except KeyError:
        raise ValueError(f"{ref}: there is no evidence record {m.group(1)}") from None
    is_requirement, index = bool(m.group(2)), int(m.group(3))
    items = record.technical_requirements if is_requirement else record.claims
    kind = "requirement" if is_requirement else "claim"
    if not 1 <= index <= len(items):
        raise ValueError(f"{ref}: record {record.id} has {len(items)} {kind}(s)")
    item = items[index - 1]
    text = f"{item.parameter} {item.requirement} {item.support}" if is_requirement else f"{item.text} {item.support}"
    return Resolved(ref, kind, record.id, record.pathway, item.status == "supported", text)


def ref_problems(project: Project, refs: tuple[str, ...] | list[str], pathway_id: str,
                 feedstock_findings: BaseModel | None = None) -> list[str]:
    """Why any of these references can't be used for this pathway (empty when all are fine)."""
    problems = []
    for ref in refs:
        try:
            r = resolve(project, ref, feedstock_findings)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if not r.supported:
            problems.append(f"{ref} is marked unverified in the library and can't support a statement")
        if r.pathway_id is not None and r.pathway_id != pathway_id:
            problems.append(f"{ref} belongs to pathway {r.pathway_id}, not {pathway_id}")
    return problems


def record_ids(refs: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """The evidence record ids behind a list of references (feedstock references have none)."""
    return tuple(dict.fromkeys(m.group(1) for ref in refs if (m := EVIDENCE_REF.fullmatch(ref.strip()))))


def numbers_in(text: str) -> list[str]:
    return NUMBER.findall(NOT_NUMBERS.sub(" ", text))


def number_values(text: str) -> set[float]:
    return {float(token.replace(",", "")) for token in NUMBER.findall(text)}


def _matches(token: str, allowed: set[float]) -> bool:
    x = float(token.replace(",", ""))
    decimals = len(token.split(".")[1]) if "." in token else 0
    for y in allowed:
        for candidate in (y, y * 100):  # a fraction such as 0.25 may be written as 25 (%)
            if abs(candidate - x) < 1e-9 or round(candidate, decimals) == x:
                return True
    return False


def unsupported_numbers(text: str, allowed: set[float]) -> list[str]:
    """Numbers in `text` that don't appear in `allowed` (allowing rounding and fraction-to-percent)."""
    return [token for token in numbers_in(text) if not _matches(token, allowed)]


def cited_numbers(project: Project, refs: tuple[str, ...] | list[str],
                  feedstock_findings: BaseModel | None = None) -> set[float]:
    values: set[float] = set()
    for ref in refs:
        try:
            values |= number_values(resolve(project, ref, feedstock_findings).text)
        except ValueError:
            pass
    return values
