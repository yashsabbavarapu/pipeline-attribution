"""The three attribution models. All of the math lives in this file.

For an opportunity, the eligible touches are that account's touches with
    created_at - lookback_days <= timestamp <= created_at
ordered by (timestamp, touch_id). Call that ordered list t_1 .. t_n.

Each model is a weight function n -> [w_1 .. w_n] with sum(w_i) == 1, and
    credit(t_i) = amount * w_i

    first-touch:     w_1 = 1, every other w_i = 0
    last-touch:      w_n = 1, every other w_i = 0
    position-based:  n == 1:  w_1 = 1
                     n == 2:  w_1 = w_2 = 1/2
                     n >= 3:  w_1 = w_n = 2/5, each middle w_i = (1/5) / (n - 2)

Weights are exact Fractions, so they always sum to exactly 1 and every dollar
of an opportunity is assigned to a specific touch_id. Zero-weight touches are
not emitted. An opportunity with no eligible touches yields no credits; the
readout reports it as unattributed pipeline instead of guessing.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import timedelta
from fractions import Fraction

from pipeline_attribution.models import (
    FIRST_TOUCH,
    LAST_TOUCH,
    POSITION_BASED,
    Credit,
    Opportunity,
    Touch,
)

DEFAULT_LOOKBACK_DAYS = 90

FIRST_SHARE = Fraction(2, 5)
LAST_SHARE = Fraction(2, 5)
MIDDLE_SHARE = Fraction(1, 5)


def first_touch_weights(n: int) -> list[Fraction]:
    return [Fraction(1) if i == 0 else Fraction(0) for i in range(n)]


def last_touch_weights(n: int) -> list[Fraction]:
    return [Fraction(1) if i == n - 1 else Fraction(0) for i in range(n)]


def position_based_weights(n: int) -> list[Fraction]:
    if n == 1:
        return [Fraction(1)]
    if n == 2:
        return [Fraction(1, 2), Fraction(1, 2)]
    middle = MIDDLE_SHARE / (n - 2)
    return [FIRST_SHARE] + [middle] * (n - 2) + [LAST_SHARE]


WEIGHTS: dict[str, Callable[[int], list[Fraction]]] = {
    FIRST_TOUCH: first_touch_weights,
    LAST_TOUCH: last_touch_weights,
    POSITION_BASED: position_based_weights,
}


def eligible_touches(
    opp: Opportunity, touches: Iterable[Touch], lookback_days: int = DEFAULT_LOOKBACK_DAYS
) -> list[Touch]:
    start = opp.created_at - timedelta(days=lookback_days)
    path = [
        t
        for t in touches
        if t.account_id == opp.account_id and start <= t.timestamp <= opp.created_at
    ]
    return sorted(path, key=lambda t: (t.timestamp, t.touch_id))


def attribute(
    opp: Opportunity,
    touches: Iterable[Touch],
    model: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[Credit]:
    if model not in WEIGHTS:
        raise ValueError(f"unknown model {model!r}, expected one of {', '.join(WEIGHTS)}")
    path = eligible_touches(opp, touches, lookback_days)
    if not path:
        return []
    weights = WEIGHTS[model](len(path))
    assert sum(weights) == 1, "weights must allocate exactly 100% of the opportunity"
    return [
        Credit(
            model=model,
            opp_id=opp.opp_id,
            account_id=opp.account_id,
            touch_id=touch.touch_id,
            play=touch.play,
            weight=weight,
            credit=float(Fraction(opp.amount) * weight),
        )
        for touch, weight in zip(path, weights)
        if weight > 0
    ]


def attribute_all(
    opps: Iterable[Opportunity],
    touches: Iterable[Touch],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[Credit]:
    """Credits for every opportunity under every model."""
    by_account: dict[str, list[Touch]] = defaultdict(list)
    for touch in touches:
        by_account[touch.account_id].append(touch)
    credits: list[Credit] = []
    for opp in sorted(opps, key=lambda o: o.opp_id):
        for model in WEIGHTS:
            credits.extend(attribute(opp, by_account[opp.account_id], model, lookback_days))
    return credits
