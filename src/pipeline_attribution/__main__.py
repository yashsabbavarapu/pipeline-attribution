"""CLI: ingest touchpoints (and opportunities), then render a readout or trace one opp."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline_attribution.attribution import DEFAULT_LOOKBACK_DAYS, attribute_all, eligible_touches
from pipeline_attribution.models import MODELS
from pipeline_attribution.readout import render_report, render_trace
from pipeline_attribution.sources import CsvSource, Source
from pipeline_attribution.storage import Store

DEFAULT_DB = "pipeline_attribution.db"


def cmd_ingest(args: argparse.Namespace) -> int:
    store = Store(Path(args.db))
    try:
        source: Source = CsvSource(
            Path(args.touches), Path(args.opportunities) if args.opportunities else None
        )
        touches = source.touches()
        store.save_touches(touches)
        opps = source.opportunities()
        store.save_opportunities(opps)
        credits = attribute_all(store.opportunities(), store.touches(), args.lookback_days)
        store.replace_attributions(credits, args.lookback_days)
        counts = store.counts()
    finally:
        store.close()
    print(
        f"ingested {len(touches)} touches, {len(opps)} opportunities into {args.db};"
        f" store now holds {counts['touchpoints']} touches, {counts['opportunities']}"
        f" opportunities, {counts['attributions']} attribution rows"
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = Store(Path(args.db))
    try:
        text = render_report(
            args.model,
            store.touches(),
            store.opportunities(),
            store.credits(),
            store.lookback_days() or DEFAULT_LOOKBACK_DAYS,
        )
    finally:
        store.close()
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.model} report to {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    store = Store(Path(args.db))
    try:
        opps = {o.opp_id: o for o in store.opportunities()}
        if args.opp not in opps:
            print(f"error: no opportunity {args.opp!r} in {args.db}", file=sys.stderr)
            return 1
        opp = opps[args.opp]
        path = eligible_touches(opp, store.touches(), store.lookback_days() or DEFAULT_LOOKBACK_DAYS)
        text = render_trace(opp, path, store.credits())
    finally:
        store.close()
    sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline-attribution", description="Transparent multi-touch pipeline attribution"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Load touchpoints (and opportunities), re-attribute")
    p_ingest.add_argument("--touches", required=True, help="Path to touchpoints CSV")
    p_ingest.add_argument("--opportunities", default=None, help="Path to opportunities CSV")
    p_ingest.add_argument("--db", default=DEFAULT_DB, help="SQLite path")
    p_ingest.add_argument(
        "--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
        help="Touches older than this before an opp are not credited",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_report = sub.add_parser("report", help="Render the Markdown attribution readout")
    p_report.add_argument("--model", choices=MODELS, default="position-based")
    p_report.add_argument("--db", default=DEFAULT_DB, help="SQLite path")
    p_report.add_argument("--output", default=None, help="Write report to file instead of stdout")
    p_report.set_defaults(func=cmd_report)

    p_trace = sub.add_parser("trace", help="Show every touch and its credit for one opportunity")
    p_trace.add_argument("--opp", required=True, help="Opportunity id, e.g. OPP-001")
    p_trace.add_argument("--db", default=DEFAULT_DB, help="SQLite path")
    p_trace.set_defaults(func=cmd_trace)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
