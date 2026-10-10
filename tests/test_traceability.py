"""Every dollar of credit links back to a real touch_id, on the full fixtures."""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import pytest

from pipeline_attribution.attribution import attribute_all
from pipeline_attribution.ingest import parse_opportunities, parse_touches
from pipeline_attribution.models import MODELS
from pipeline_attribution.readout import build_play_stats, render_report
from pipeline_attribution.storage import Store

REPO = Path(__file__).resolve().parent.parent
TOUCHES = parse_touches(REPO / "fixtures" / "touches.csv")
OPPS = parse_opportunities(REPO / "fixtures" / "opportunities.csv")
CREDITS = attribute_all(OPPS, TOUCHES)


def test_every_credit_points_at_an_eligible_touch() -> None:
    touches = {t.touch_id: t for t in TOUCHES}
    opps = {o.opp_id: o for o in OPPS}
    for c in CREDITS:
        t = touches[c.touch_id]
        o = opps[c.opp_id]
        assert t.account_id == o.account_id == c.account_id
        assert t.timestamp <= o.created_at
        assert t.play == c.play


@pytest.mark.parametrize("model", MODELS)
def test_each_opp_is_allocated_exactly_once(model: str) -> None:
    allocated: dict[str, float] = defaultdict(float)
    weights: dict[str, Fraction] = defaultdict(Fraction)
    for c in CREDITS:
        if c.model == model:
            allocated[c.opp_id] += c.credit
            weights[c.opp_id] += c.weight
    for o in OPPS:
        assert allocated[o.opp_id] == pytest.approx(o.amount)
        assert weights[o.opp_id] == 1


def test_play_totals_are_sums_of_credit_rows() -> None:
    stats = {s.play: s for s in build_play_stats(TOUCHES, CREDITS)}
    for model in MODELS:
        for play, s in stats.items():
            expected = sum(c.credit for c in CREDITS if c.model == model and c.play == play)
            assert s.credited(model) == pytest.approx(expected)


def test_report_ledger_names_every_credited_touch() -> None:
    text = render_report("position-based", TOUCHES, OPPS, CREDITS, 90)
    ledger = text.split("## Credit ledger")[1]
    for c in CREDITS:
        if c.model == "position-based":
            assert f"`{c.touch_id}`" in ledger


def test_credits_survive_storage_round_trip_exactly(tmp_path: Path) -> None:
    store = Store(tmp_path / "t.db")
    store.save_touches(TOUCHES)
    store.save_opportunities(OPPS)
    store.replace_attributions(CREDITS, 90)
    stored = store.credits()
    store.close()
    key = lambda c: (c.model, c.opp_id, c.touch_id)  # noqa: E731
    assert sorted(stored, key=key) == sorted(CREDITS, key=key)
