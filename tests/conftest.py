"""Shared builders for hand-computed fixtures."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pipeline_attribution.models import Opportunity, Touch

T0 = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def touch(
    touch_id: str, day: float, play: str, account_id: str = "acct", cost: float = 0.0
) -> Touch:
    return Touch(
        touch_id=touch_id,
        account_id=account_id,
        timestamp=T0 + timedelta(days=day),
        play=play,
        channel="test",
        cost=cost,
    )


def opp(opp_id: str, day: float, amount: float, account_id: str = "acct") -> Opportunity:
    return Opportunity(
        opp_id=opp_id, account_id=account_id, created_at=T0 + timedelta(days=day), amount=amount
    )
