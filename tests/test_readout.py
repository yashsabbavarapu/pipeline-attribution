"""Readout content: the before/after narrative and report sections."""
from fractions import Fraction

from conftest import opp, touch
from pipeline_attribution.attribution import attribute_all
from pipeline_attribution.readout import before_after, render_report, weight_pct

# Two opps, both closed by paid search. Outbound opened the $60k one.
TOUCHES = [
    touch("a1", 0, "outbound_sequence", "a", cost=100),
    touch("a2", 5, "website_visit", "a"),
    touch("a3", 9, "paid_search", "a", cost=400),
    touch("b1", 2, "paid_search", "b", cost=400),
    touch("b2", 8, "paid_search", "b", cost=400),
    touch("c1", 1, "paid_social_abm", "c", cost=900),
]
OPPS = [opp("O1", 10, 60_000, "a"), opp("O2", 10, 40_000, "b"), opp("O3", 10, 5_000, "nobody")]
CREDITS = attribute_all(OPPS, TOUCHES)


def test_before_after_hand_computed() -> None:
    text = "\n".join(before_after(CREDITS))
    assert "Paid search looks like the winner with $100,000, 100% of attributed pipeline" in text
    assert "last touch on 2 opportunities" in text
    assert "Outbound sequence was the first touch on $60,000" in text
    assert "sourced 60% of it" in text
    # Position-based: O1 = 40% outbound, 20% web, 40% search; O2 = 100% search.
    # Search: 24k + 40k = 64k of 100k; outbound 24k.
    assert "64% Paid search, 24% Outbound sequence" in text
    assert "from $100,000 to $64,000" in text


def test_before_after_with_no_pipeline() -> None:
    assert before_after([]) == ["No attributed pipeline yet, so there is nothing to compare."]


def test_report_sections_and_unattributed() -> None:
    text = render_report("position-based", TOUCHES, OPPS, CREDITS, 90)
    for heading in ("## Credit by play (position-based)", "## Same pipeline, three models",
                    "## What to do more of, less of", "## Before and after", "## Credit ledger"):
        assert heading in text
    assert "Unattributed: 1 opportunities ($5,000)" in text
    assert "O3" in text and "_no touches in window_" in text
    # ABM spent $900 and is credited nothing under any model.
    assert "**Less: Paid social / ABM.** Spent $900" in text


def test_last_touch_report_protects_sourcer() -> None:
    text = render_report("last-touch", TOUCHES, OPPS, CREDITS, 90)
    assert "**Hold: Outbound sequence.** Last-touch credits it $0 but position-based" in text


def test_weight_pct() -> None:
    assert weight_pct(Fraction(2, 5)) == "40%"
    assert weight_pct(Fraction(1, 15)) == "6.7%"
