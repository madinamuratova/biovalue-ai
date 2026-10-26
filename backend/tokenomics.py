"""Token usage, cost, and monthly cost estimates.

- Token counts come only from the provider's usage metadata (PydanticAI's RunUsage, filled from the OpenAI Responses
  API through Portkey): input, cached input, output, and reasoning tokens.
- Prices come only from data/model_prices.json (verified course prices). A model without a verified price gets no
  cost. Next to it, a proxy estimate at another model's verified price is given and labelled as such, so runs can be
  compared in dollars without pretending to know the real price.
- Usage assumptions for monthly estimates (assessments per user, user counts) live in
  data/tokenomics_assumptions.json, with their reasons. Hosting and other costs are kept separate from model costs.
"""

import json
from dataclasses import dataclass
from typing import Literal

from backend.config import DATA_DIR
from backend.models import Frozen
from backend.trace import Usage

MILLION = 1_000_000


@dataclass(frozen=True)
class Price:
    model: str
    input_per_1m: float
    cached_input_per_1m: float
    output_per_1m: float
    source: str


class CostReport(Frozen):
    status: Literal["calculated", "not_calculated"]
    usd: float | None  # at the run model's verified price; None when there is none
    note: str
    proxy_usd: float | None = None  # at the proxy model's verified price, labelled as an estimate
    proxy_note: str = ""


def _prices() -> dict:
    return json.loads((DATA_DIR / "model_prices.json").read_text(encoding="utf-8"))["models"]


def assumptions() -> dict:
    data = json.loads((DATA_DIR / "tokenomics_assumptions.json").read_text(encoding="utf-8"))
    data.pop("about", None)
    return data


def verified_price(model: str) -> Price | None:
    p = _prices().get(model)
    return None if p is None else Price(model, p["input_per_1m"], p["cached_input_per_1m"], p["output_per_1m"], p["source"])


def proxy_price() -> Price:
    model = assumptions()["proxy_price_model"]
    price = verified_price(model)
    if price is None:
        raise RuntimeError(f"proxy model {model} has no verified price in data/model_prices.json")
    return price


def cost_usd(usage: Usage, price: Price) -> float:
    """Uncached input, cached input, and output tokens, each at its own rate."""
    uncached = usage.input_tokens - usage.cache_read_tokens
    return (uncached * price.input_per_1m + usage.cache_read_tokens * price.cached_input_per_1m
            + usage.output_tokens * price.output_per_1m) / MILLION


def cost_report(model: str, usage: Usage) -> CostReport:
    proxy = proxy_price()
    proxy_note = (f"Estimate only: priced as {proxy.model} ({proxy.source}), not the price of {model}."
                  if proxy.model != model else f"At {proxy.model}'s verified price.")
    proxy_usd = round(cost_usd(usage, proxy), 6)
    price = verified_price(model)
    if price is None:
        return CostReport(status="not_calculated", usd=None, proxy_usd=proxy_usd, proxy_note=proxy_note,
                          note=f"No verified price for {model} in data/model_prices.json; token counts are measured.")
    return CostReport(status="calculated", usd=round(cost_usd(usage, price), 6), note=f"At {model}'s verified course price ({price.source}).",
                      proxy_usd=proxy_usd, proxy_note=proxy_note)


def monthly_estimate(per_assessment: Usage, users: int, assessments_per_user: float, price: Price) -> dict:
    """Model cost for a month: users x assessments per user x measured tokens per assessment, at `price`."""
    runs = users * assessments_per_user
    tokens = {name: getattr(per_assessment, name) * runs
              for name in ("input_tokens", "cache_read_tokens", "output_tokens")}
    usd = cost_usd(per_assessment, price) * runs
    return {"users": users, "assessments_per_month": runs, "tokens": tokens, "model_cost_usd": round(usd, 2),
            "price_model": price.model}
