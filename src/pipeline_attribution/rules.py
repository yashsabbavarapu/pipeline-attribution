"""Rule tables that turn per-play numbers into plain-language advice.

Two small tables, both readable top to bottom:

VERDICT_RULES (first match wins), evaluated under the model the report uses:
    R1 undercounted  single-touch model, play has spend, and position-based
                     credits it >= 1.5x this model                     -> Hold
    R2 no-pipeline   play has spend and $0 credited                    -> Less
    R3 organic       play has no spend                                 -> Keep
    R4 efficient     cost per pipeline $ <= 0.5x blended               -> More
    R5 expensive     cost per pipeline $ >= 2x blended                 -> Less
    R6 in-range      anything else                                     -> Hold

ROLE_RULES (first match wins), always comparing first-touch vs last-touch
share of attributed pipeline, so the role is the same whichever model the
report uses:
    Sourcer   first share >= 5% and >= 1.5x last share
    Closer    last share >= 5% and >= 1.5x first share
    Assist    position-based share exceeds both first and last share
    Balanced  anything else
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pipeline_attribution.models import FIRST_TOUCH, LAST_TOUCH, POSITION_BASED

UNDERCOUNT_RATIO = 1.5
EFFICIENT_RATIO = 0.5
EXPENSIVE_RATIO = 2.0
ROLE_RATIO = 1.5
MIN_ROLE_SHARE = 0.05


@dataclass(frozen=True)
class PlayStats:
    play: str
    touches: int
    cost: float
    credit: dict[str, float] = field(default_factory=dict)  # model -> pipeline $

    def credited(self, model: str) -> float:
        return self.credit.get(model, 0.0)

    def cost_per_dollar(self, model: str) -> float | None:
        credited = self.credited(model)
        return None if credited <= 0 else self.cost / credited


@dataclass(frozen=True)
class Recommendation:
    verdict: str  # More, Less, Hold, Keep
    rule: str
    reason: str


@dataclass(frozen=True)
class Role:
    name: str
    reason: str


def _money(value: float) -> str:
    return f"${value:,.0f}"


def recommend(stats: PlayStats, model: str, blended: float | None) -> Recommendation:
    """Apply VERDICT_RULES. `blended` is total spend / total attributed pipeline."""
    credited = stats.credited(model)
    position = stats.credited(POSITION_BASED)
    if (
        model in (FIRST_TOUCH, LAST_TOUCH)
        and stats.cost > 0
        and position > 0
        and position >= UNDERCOUNT_RATIO * credited
    ):
        return Recommendation(
            "Hold",
            "R1 undercounted",
            f"{model} credits it {_money(credited)} but position-based credits"
            f" {_money(position)}. This model undercounts it, so do not cut on this view.",
        )
    if stats.cost > 0 and credited <= 0:
        return Recommendation(
            "Less",
            "R2 no-pipeline",
            f"spent {_money(stats.cost)} and earned $0 of pipeline under {model}."
            " Pause it or rework the targeting.",
        )
    if stats.cost <= 0:
        return Recommendation(
            "Keep",
            "R3 organic",
            "no direct spend to reallocate. This is where demand shows up,"
            " so route it to sales fast rather than budgeting for it.",
        )
    cpd = stats.cost_per_dollar(model)
    assert cpd is not None and blended is not None and blended > 0
    if cpd <= EFFICIENT_RATIO * blended:
        return Recommendation(
            "More",
            "R4 efficient",
            f"${cpd:.3f} per pipeline dollar, under half the blended ${blended:.3f}."
            " Scale it until the rate climbs toward blended.",
        )
    if cpd >= EXPENSIVE_RATIO * blended:
        return Recommendation(
            "Less",
            "R5 expensive",
            f"${cpd:.3f} per pipeline dollar, {cpd / blended:.1f}x the blended ${blended:.3f}."
            " Shift budget to the efficient plays.",
        )
    return Recommendation(
        "Hold",
        "R6 in-range",
        f"${cpd:.3f} per pipeline dollar, within 2x of the blended ${blended:.3f}.",
    )


def role(stats: PlayStats, total_pipeline: float) -> Role:
    """Apply ROLE_RULES. `total_pipeline` is attributed pipeline (same under every model)."""
    if total_pipeline <= 0:
        return Role("Balanced", "no attributed pipeline yet.")
    first = stats.credited(FIRST_TOUCH) / total_pipeline
    last = stats.credited(LAST_TOUCH) / total_pipeline
    position = stats.credited(POSITION_BASED) / total_pipeline
    if first >= MIN_ROLE_SHARE and first >= ROLE_RATIO * last:
        return Role(
            "Sourcer",
            f"opens {first:.0%} of pipeline but closes {last:.0%}. Last-touch hides it.",
        )
    if last >= MIN_ROLE_SHARE and last >= ROLE_RATIO * first:
        return Role(
            "Closer",
            f"closes {last:.0%} of pipeline but opens {first:.0%}."
            " It converts demand other plays created.",
        )
    if position > max(first, last):
        return Role(
            "Assist",
            f"shows up mid-journey: {position:.0%} under position-based,"
            f" {first:.0%} first-touch, {last:.0%} last-touch.",
        )
    return Role("Balanced", f"opens {first:.0%} and closes {last:.0%} of pipeline.")
