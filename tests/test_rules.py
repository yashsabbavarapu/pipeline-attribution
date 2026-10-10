"""Readout rule tables: one test per verdict rule and role rule."""
from pipeline_attribution.rules import PlayStats, recommend, role

BLENDED = 0.05


def stats(cost: float, first: float = 0, last: float = 0, position: float = 0) -> PlayStats:
    return PlayStats(
        play="p",
        touches=10,
        cost=cost,
        credit={"first-touch": first, "last-touch": last, "position-based": position},
    )


def test_r1_single_touch_model_undercounts() -> None:
    rec = recommend(stats(5_000, first=0, last=10_000, position=40_000), "last-touch", BLENDED)
    assert (rec.verdict, rec.rule) == ("Hold", "R1 undercounted")


def test_r1_does_not_apply_to_position_based() -> None:
    rec = recommend(stats(5_000, last=0, position=0), "position-based", BLENDED)
    assert rec.rule == "R2 no-pipeline"


def test_r2_spend_with_no_pipeline() -> None:
    rec = recommend(stats(5_000), "first-touch", BLENDED)
    assert (rec.verdict, rec.rule) == ("Less", "R2 no-pipeline")
    assert "$5,000" in rec.reason


def test_r3_organic() -> None:
    rec = recommend(stats(0, position=50_000), "position-based", BLENDED)
    assert (rec.verdict, rec.rule) == ("Keep", "R3 organic")


def test_r4_efficient() -> None:
    rec = recommend(stats(1_000, position=100_000), "position-based", BLENDED)  # $0.01
    assert (rec.verdict, rec.rule) == ("More", "R4 efficient")


def test_r5_expensive() -> None:
    rec = recommend(stats(20_000, position=100_000), "position-based", BLENDED)  # $0.20
    assert (rec.verdict, rec.rule) == ("Less", "R5 expensive")
    assert "4.0x" in rec.reason


def test_r6_in_range() -> None:
    rec = recommend(stats(6_000, position=100_000), "position-based", BLENDED)  # $0.06
    assert (rec.verdict, rec.rule) == ("Hold", "R6 in-range")


def test_thresholds_are_inclusive() -> None:
    assert recommend(stats(2_500, position=100_000), "position-based", BLENDED).rule == "R4 efficient"
    assert recommend(stats(10_000, position=100_000), "position-based", BLENDED).rule == "R5 expensive"


def test_roles() -> None:
    total = 1_000_000
    assert role(stats(1, first=400_000, last=100_000, position=250_000), total).name == "Sourcer"
    assert role(stats(1, first=100_000, last=400_000, position=250_000), total).name == "Closer"
    assert role(stats(0, first=0, last=0, position=120_000), total).name == "Assist"
    assert role(stats(1, first=300_000, last=300_000, position=300_000), total).name == "Balanced"
    assert role(stats(1), 0).name == "Balanced"
