"""Each model's math on hand-computed fixtures."""
from fractions import Fraction

import pytest

from conftest import opp, touch
from pipeline_attribution.attribution import (
    attribute,
    attribute_all,
    eligible_touches,
    first_touch_weights,
    last_touch_weights,
    position_based_weights,
)

# Path for a $100,000 opp: outbound, outbound, website, paid search, paid search.
PATH = [
    touch("t1", 0, "outbound_sequence"),
    touch("t2", 3, "outbound_sequence"),
    touch("t3", 7, "website_visit"),
    touch("t4", 10, "paid_search"),
    touch("t5", 12, "paid_search"),
]
OPP = opp("o1", 13, 100_000)


def by_touch(model: str) -> dict[str, float]:
    return {c.touch_id: c.credit for c in attribute(OPP, PATH, model)}


def by_play(model: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for c in attribute(OPP, PATH, model):
        out[c.play] = out.get(c.play, 0.0) + c.credit
    return out


def test_single_touch_weight_vectors() -> None:
    assert first_touch_weights(4) == [1, 0, 0, 0]
    assert last_touch_weights(4) == [0, 0, 0, 1]
    assert first_touch_weights(1) == last_touch_weights(1) == [1]


def test_position_based_weight_vectors() -> None:
    assert position_based_weights(1) == [1]
    assert position_based_weights(2) == [Fraction(1, 2), Fraction(1, 2)]
    assert position_based_weights(3) == [Fraction(2, 5), Fraction(1, 5), Fraction(2, 5)]
    assert position_based_weights(6) == [Fraction(2, 5)] + [Fraction(1, 20)] * 4 + [Fraction(2, 5)]


@pytest.mark.parametrize("n", range(1, 25))
def test_weights_always_sum_to_exactly_one(n: int) -> None:
    for fn in (first_touch_weights, last_touch_weights, position_based_weights):
        assert sum(fn(n)) == 1


def test_first_touch_hand_computed() -> None:
    assert by_touch("first-touch") == {"t1": 100_000}


def test_last_touch_hand_computed() -> None:
    assert by_touch("last-touch") == {"t5": 100_000}


def test_position_based_hand_computed() -> None:
    # 40% first, 40% last, 20% / 3 middle touches = 6.667% each.
    credits = by_touch("position-based")
    assert credits["t1"] == pytest.approx(40_000)
    assert credits["t5"] == pytest.approx(40_000)
    for middle in ("t2", "t3", "t4"):
        assert credits[middle] == pytest.approx(20_000 / 3)
    plays = by_play("position-based")
    assert plays["outbound_sequence"] == pytest.approx(40_000 + 20_000 / 3)  # 46,666.67
    assert plays["website_visit"] == pytest.approx(20_000 / 3)  # 6,666.67
    assert plays["paid_search"] == pytest.approx(40_000 + 20_000 / 3)  # 46,666.67


def test_two_touch_path_splits_evenly() -> None:
    credits = {c.touch_id: c.credit for c in attribute(opp("o", 5, 50_000), PATH[:2], "position-based")}
    assert credits == {"t1": 25_000, "t2": 25_000}


def test_eligibility_window_and_account_scope() -> None:
    touches = [
        touch("old", -100, "paid_search"),  # outside 90-day lookback
        touch("in", -10, "referral"),
        touch("after", 2, "paid_search"),  # after opp creation, never credited
        touch("other", -5, "outbound_sequence", account_id="someone-else"),
    ]
    path = eligible_touches(opp("o", 0, 10_000), touches, lookback_days=90)
    assert [t.touch_id for t in path] == ["in"]
    path = eligible_touches(opp("o", 0, 10_000), touches, lookback_days=120)
    assert [t.touch_id for t in path] == ["old", "in"]


def test_touch_at_exact_creation_time_counts() -> None:
    path = eligible_touches(opp("o", 3, 1), [touch("same", 3, "demo_request")])
    assert [t.touch_id for t in path] == ["same"]


def test_ties_are_ordered_by_touch_id() -> None:
    touches = [touch("b", 0, "paid_search"), touch("a", 0, "outbound_sequence")]
    credits = attribute(opp("o", 1, 1_000), touches, "first-touch")
    assert [c.touch_id for c in credits] == ["a"]


def test_no_touches_means_no_credit() -> None:
    assert attribute(opp("o", 1, 1_000), [], "position-based") == []


def test_unknown_model_rejected() -> None:
    with pytest.raises(ValueError):
        attribute(OPP, PATH, "linear")


def test_attribute_all_covers_every_model() -> None:
    credits = attribute_all([OPP], PATH)
    assert {c.model for c in credits} == {"first-touch", "last-touch", "position-based"}
    assert len(credits) == 1 + 1 + 5
