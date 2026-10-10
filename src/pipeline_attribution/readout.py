"""Render the Markdown readout a RevOps lead can audit line by line.

Every number in the report is a sum over attribution rows, and the credit
ledger at the end lists the touch_ids behind each opportunity's credit.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction

from pipeline_attribution.attribution import eligible_touches
from pipeline_attribution.models import (
    FIRST_TOUCH,
    LAST_TOUCH,
    MODELS,
    POSITION_BASED,
    Credit,
    Opportunity,
    Touch,
    play_label,
)
from pipeline_attribution.rules import PlayStats, recommend, role

MODEL_FORMULAS = {
    FIRST_TOUCH: "100% of each opportunity to the earliest touch in its lookback window.",
    LAST_TOUCH: "100% of each opportunity to the latest touch at or before its creation.",
    POSITION_BASED: (
        "40% to the first touch, 40% to the last, 20% split evenly across the middle"
        " touches. Two touches split 50/50, one touch takes 100%."
    ),
}


def money(value: float) -> str:
    return f"${value:,.0f}"


def pct(value: float) -> str:
    return f"{value:.0%}"


def weight_pct(weight: Fraction) -> str:
    value = float(weight) * 100
    return f"{value:.0f}%" if value == round(value) else f"{value:.1f}%"


def build_play_stats(touches: list[Touch], credits: list[Credit]) -> list[PlayStats]:
    counts: dict[str, int] = defaultdict(int)
    costs: dict[str, float] = defaultdict(float)
    for t in touches:
        counts[t.play] += 1
        costs[t.play] += t.cost
    credit: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for c in credits:
        credit[c.play][c.model] += c.credit
    plays = sorted(set(counts) | set(credit))
    return [
        PlayStats(
            play=p,
            touches=counts[p],
            cost=costs[p],
            credit={m: credit[p][m] for m in MODELS},
        )
        for p in plays
    ]


def attributed_pipeline(credits: list[Credit], model: str) -> float:
    return sum(c.credit for c in credits if c.model == model)


def before_after(credits: list[Credit]) -> list[str]:
    """Compare the last-touch winner with what the other models say about its pipeline."""
    last: dict[str, float] = defaultdict(float)
    position: dict[str, float] = defaultdict(float)
    for c in credits:
        if c.model == LAST_TOUCH:
            last[c.play] += c.credit
        elif c.model == POSITION_BASED:
            position[c.play] += c.credit
    total = sum(last.values())
    if total <= 0:
        return ["No attributed pipeline yet, so there is nothing to compare."]

    winner = max(last, key=lambda p: (last[p], p))
    won_opps = {c.opp_id for c in credits if c.model == LAST_TOUCH and c.play == winner}
    won_amount = sum(c.credit for c in credits if c.model == LAST_TOUCH and c.opp_id in won_opps)
    sourced: dict[str, float] = defaultdict(float)
    for c in credits:
        if c.model == FIRST_TOUCH and c.opp_id in won_opps and c.play != winner:
            sourced[c.play] += c.credit

    w = play_label(winner)
    lines = [
        f"**Before (last-touch):** {w} looks like the winner with {money(last[winner])},"
        f" {pct(last[winner] / total)} of attributed pipeline. It was the last touch on"
        f" {len(won_opps)} opportunities.",
        "",
    ]
    if not sourced:
        lines.append(
            f"**After:** {w} also opened every one of those opportunities, so the other"
            " models agree with last-touch here."
        )
        return lines

    sourcer = max(sourced, key=lambda p: (sourced[p], p))
    s = play_label(sourcer)
    share = sourced[sourcer] / won_amount
    split: dict[str, float] = defaultdict(float)
    for c in credits:
        if c.model == POSITION_BASED and c.opp_id in won_opps:
            split[c.play] += c.credit
    lines += [
        f"**After (first-touch and position-based):** of the {money(won_amount)} last-touch"
        f" hands to {w}, {s} was the first touch on {money(sourced[sourcer])}. {s} sourced"
        f" {pct(share)} of it. Position-based splits those same opportunities"
        f" {pct(split[winner] / won_amount)} {w}, {pct(split[sourcer] / won_amount)} {s}.",
        "",
        f"Across all pipeline, position-based moves {w} from {money(last[winner])} to"
        f" {money(position[winner])} and {s} from {money(last[sourcer])} to"
        f" {money(position[sourcer])}.",
        "",
        f"**So what:** a last-touch dashboard says move budget into {w}. Cutting {s} on"
        f" that view would cut the play that opened {pct(share)} of {w}'s pipeline.",
    ]
    return lines


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def render_report(
    model: str,
    touches: list[Touch],
    opps: list[Opportunity],
    credits: list[Credit],
    lookback_days: int,
) -> str:
    if model not in MODELS:
        raise ValueError(f"unknown model {model!r}")
    stats = build_play_stats(touches, credits)
    total = attributed_pipeline(credits, model)
    spend = sum(t.cost for t in touches)
    blended = spend / total if total > 0 else None
    model_credits = [c for c in credits if c.model == model]
    attributed_opps = {c.opp_id for c in model_credits}
    unattributed = [o for o in opps if o.opp_id not in attributed_opps]
    accounts = {t.account_id for t in touches}
    by_credit = sorted(stats, key=lambda s: (-s.credited(model), s.play))

    lines = [
        "# Pipeline Attribution Readout",
        "",
        f"_Model: **{model}** · {len(opps)} opportunities · {money(total)} attributed pipeline"
        f" · {len(touches)} touches across {len(accounts)} accounts · {money(spend)} spend"
        f" · {lookback_days}-day lookback_",
        "",
        f"How credit is assigned: {MODEL_FORMULAS[model]}",
        "",
        f"## Credit by play ({model})",
        "",
    ]
    rows = []
    for s in by_credit:
        cpd = s.cost_per_dollar(model)
        rows.append(
            [
                play_label(s.play),
                str(s.touches),
                money(s.cost),
                money(s.credited(model)),
                pct(s.credited(model) / total) if total > 0 else "0%",
                "n/a" if cpd is None else f"${cpd:.3f}",
                recommend(s, model, blended).verdict,
            ]
        )
    lines += _table(
        ["Play", "Touches", "Cost", "Pipeline credited", "Share", "Cost per $1 pipeline", "Verdict"],
        rows,
    )
    if blended is not None:
        lines += ["", f"Blended: {money(spend)} spend / {money(total)} pipeline = ${blended:.3f}"
                  " per pipeline dollar."]
    if unattributed:
        missed = sum(o.amount for o in unattributed)
        ids = ", ".join(o.opp_id for o in unattributed)
        lines += ["", f"Unattributed: {len(unattributed)} opportunities ({money(missed)}) had no"
                  f" touches in the lookback window: {ids}."]

    lines += ["", "## Same pipeline, three models", ""]
    rows = []
    for s in by_credit:
        r = role(s, total)
        rows.append(
            [play_label(s.play)]
            + [money(s.credited(m)) for m in MODELS]
            + [f"**{r.name}**: {r.reason}"]
        )
    lines += _table(["Play", "First-touch", "Last-touch", "Position-based", "Role"], rows)

    lines += ["", "## What to do more of, less of", ""]
    recs = [(s, recommend(s, model, blended)) for s in by_credit]
    for verdict in ("More", "Less", "Hold", "Keep"):
        for s, rec in recs:
            if rec.verdict == verdict:
                lines.append(f"- **{verdict}: {play_label(s.play)}.** {rec.reason[0].upper()}"
                             f"{rec.reason[1:]} _({rec.rule})_")

    lines += ["", "## Before and after", ""]
    lines += before_after(credits)

    lines += ["", f"## Credit ledger ({model})", "",
              "Every opportunity, its touch path in order, and the share each touch_id earned.",
              ""]
    touch_by_id = {t.touch_id: t for t in touches}
    weights = {(c.opp_id, c.touch_id): c.weight for c in model_credits}
    for opp in sorted(opps, key=lambda o: o.opp_id):
        path = eligible_touches(opp, touch_by_id.values(), lookback_days)
        steps = " → ".join(
            f"`{t.touch_id}` {play_label(t.play)}"
            f" {weight_pct(weights.get((opp.opp_id, t.touch_id), Fraction(0)))}"
            for t in path
        ) or "_no touches in window_"
        lines.append(
            f"- **{opp.opp_id}** {opp.account_id} · {money(opp.amount)} ·"
            f" {opp.created_at.date().isoformat()}: {steps}"
        )
    return "\n".join(lines) + "\n"


def render_trace(opp: Opportunity, path: list[Touch], credits: list[Credit]) -> str:
    """One opportunity, every touch, and its credit under all three models."""
    by_key = {(c.model, c.touch_id): c for c in credits if c.opp_id == opp.opp_id}
    lines = [
        f"{opp.opp_id} · {opp.account_id} · {money(opp.amount)} · created"
        f" {opp.created_at.isoformat()}",
        "",
    ]
    header = ["touch_id", "timestamp", "play", "channel", "cost"] + list(MODELS)
    rows = []
    for t in path:
        cells = [t.touch_id, t.timestamp.strftime("%Y-%m-%d %H:%M"), play_label(t.play),
                 t.channel, money(t.cost)]
        for m in MODELS:
            c = by_key.get((m, t.touch_id))
            cells.append("-" if c is None else f"{weight_pct(c.weight)} {money(c.credit)}")
        rows.append(cells)
    lines += _table(header, rows)
    return "\n".join(lines) + "\n"
