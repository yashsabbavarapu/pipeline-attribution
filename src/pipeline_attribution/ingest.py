"""CSV parsing for touchpoint streams and opportunities.

Malformed rows are skipped with a stderr warning, never fatal. Timestamps are
ISO 8601; naive timestamps are read as UTC so every comparison is tz-aware.
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline_attribution.models import Opportunity, Touch

TOUCH_COLUMNS = ("touch_id", "account_id", "timestamp", "play", "channel", "cost")
OPP_COLUMNS = ("opp_id", "account_id", "created_at", "amount")


def parse_timestamp(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.strip())
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_play(raw: str) -> str:
    """'Paid Search' and 'paid-search' both become 'paid_search'."""
    return "_".join(raw.strip().lower().replace("-", " ").replace("/", " ").split())


def _warn(path: Path, line: int, reason: str) -> None:
    print(f"warning: {path.name} line {line}: {reason}, row skipped", file=sys.stderr)


def _check_header(path: Path, fieldnames: list[str] | None, required: tuple[str, ...]) -> None:
    missing = [c for c in required if c not in (fieldnames or [])]
    if missing:
        raise ValueError(f"{path}: missing columns {', '.join(missing)}")


def parse_touches(path: Path) -> list[Touch]:
    touches: dict[str, Touch] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        _check_header(path, list(reader.fieldnames or []), TOUCH_COLUMNS)
        for line, row in enumerate(reader, start=2):
            try:
                touch_id = (row["touch_id"] or "").strip()
                account_id = (row["account_id"] or "").strip()
                play = normalize_play(row["play"] or "")
                if not touch_id or not account_id or not play:
                    raise ValueError("touch_id, account_id and play are required")
                cost = float(row["cost"] or 0)
                if cost < 0:
                    raise ValueError("cost must be >= 0")
                touch = Touch(
                    touch_id=touch_id,
                    account_id=account_id,
                    timestamp=parse_timestamp(row["timestamp"] or ""),
                    play=play,
                    channel=(row["channel"] or "").strip(),
                    cost=cost,
                )
            except (ValueError, TypeError) as exc:
                _warn(path, line, str(exc))
                continue
            if touch_id in touches:
                _warn(path, line, f"duplicate touch_id {touch_id}, keeping the later row")
            touches[touch_id] = touch
    return list(touches.values())


def parse_opportunities(path: Path) -> list[Opportunity]:
    opps: dict[str, Opportunity] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        _check_header(path, list(reader.fieldnames or []), OPP_COLUMNS)
        for line, row in enumerate(reader, start=2):
            try:
                opp_id = (row["opp_id"] or "").strip()
                account_id = (row["account_id"] or "").strip()
                if not opp_id or not account_id:
                    raise ValueError("opp_id and account_id are required")
                amount = float(row["amount"] or "")
                if amount <= 0:
                    raise ValueError("amount must be > 0")
                opp = Opportunity(
                    opp_id=opp_id,
                    account_id=account_id,
                    created_at=parse_timestamp(row["created_at"] or ""),
                    amount=amount,
                )
            except (ValueError, TypeError) as exc:
                _warn(path, line, str(exc))
                continue
            opps[opp_id] = opp
    return list(opps.values())
