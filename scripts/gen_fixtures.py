"""Generate deterministic demo fixtures: a 90-day touch stream across 40 accounts.

Run: python scripts/gen_fixtures.py  (writes fixtures/touches.csv, fixtures/opportunities.csv)
Seeded RNG, so output is stable across runs. Accounts follow journey archetypes
so the demo shows real attribution tension: outbound opens deals that paid
search closes, ABM assists deals a demo request closes, referrals source
cheaply, and some spend never turns into pipeline at all.
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOW_START = datetime(2026, 7, 12, tzinfo=timezone.utc)
WINDOW_DAYS = 90
SEED = 7

COST = {
    "outbound_sequence": 150.0,  # loaded SDR time plus tooling, per step
    "paid_search": 400.0,  # B2B clicks plus the impressions behind each engaged click
    "paid_social_abm": 450.0,  # ABM spend per engaged target-account touch
    "website_visit": 0.0,
    "demo_request": 0.0,
    "referral": 1500.0,  # partner or customer referral fee
}
CHANNELS = {
    "outbound_sequence": ["email", "email", "linkedin", "phone"],
    "paid_search": ["google_ads"],
    "paid_social_abm": ["linkedin_ads"],
    "website_visit": ["web"],
    "demo_request": ["web_form"],
    "referral": ["partner", "customer"],
}
AMOUNTS = [24_000, 36_000, 48_000, 60_000, 72_000, 96_000, 120_000]

OB, PS, SOC, WEB, DEMO, REF = (
    "outbound_sequence", "paid_search", "paid_social_abm",
    "website_visit", "demo_request", "referral",
)


def journey(rng: random.Random, archetype: str) -> list[str]:
    """Ordered plays for one account, earliest first."""
    def n(lo: int, hi: int) -> int:
        return rng.randint(lo, hi)

    if archetype == "outbound_then_search":  # outbound opens, paid search closes
        return [OB] * n(3, 5) + [WEB] * n(1, 2) + [PS] * n(0, 1) + [WEB] * n(0, 1) + [PS]
    if archetype == "search_inbound":  # pure inbound via search
        return [PS] + [WEB] * n(1, 3) + [PS]
    if archetype == "abm_to_demo":  # ABM warms, outbound follows up, demo closes
        return [SOC] * n(2, 3) + [WEB] * n(1, 2) + [OB] * n(1, 2) + [DEMO]
    if archetype == "referral":
        return [REF] + [WEB] * n(0, 1) + [DEMO]
    if archetype == "outbound_direct":  # outbound books the meeting itself
        return [OB] * n(4, 6)
    if archetype == "cold_outbound":  # sequences that never convert
        return [OB] * n(3, 6) + [WEB] * n(0, 1)
    if archetype == "search_tire_kicker":
        return [PS] * n(1, 2) + [WEB] * n(1, 2)
    if archetype == "abm_impressions":
        return [SOC] * n(2, 4) + [WEB] * n(0, 1)
    raise ValueError(archetype)


# account_id, archetype, becomes pipeline
ACCOUNTS: list[tuple[str, str, bool]] = [
    ("northwind", "outbound_then_search", True),
    ("globex", "outbound_then_search", True),
    ("initech", "outbound_then_search", True),
    ("hooli", "outbound_then_search", True),
    ("vandelay", "outbound_then_search", True),
    ("soylent", "outbound_then_search", True),
    ("acme", "search_inbound", True),
    ("stark", "search_inbound", True),
    ("wayne", "search_inbound", True),
    ("wonka", "search_inbound", True),
    ("cyberdyne", "outbound_then_search", True),
    ("umbrella", "search_inbound", True),
    ("tyrell", "search_inbound", True),
    ("oscorp", "abm_to_demo", True),
    ("massive", "abm_to_demo", True),
    ("aperture", "abm_to_demo", True),
    ("blackmesa", "abm_to_demo", True),
    ("pied-piper", "referral", True),
    ("dunder", "referral", True),
    ("prestige", "referral", True),
    ("gringotts", "outbound_direct", True),
    ("monarch", "outbound_direct", True),
    ("bluth", "cold_outbound", False),
    ("sterling", "cold_outbound", False),
    ("krusty", "cold_outbound", False),
    ("planet-express", "cold_outbound", False),
    ("nakatomi", "cold_outbound", False),
    ("rekall", "cold_outbound", False),
    ("weyland", "search_tire_kicker", False),
    ("duff", "search_tire_kicker", False),
    ("gekko", "search_tire_kicker", False),
    ("ollivanders", "search_tire_kicker", False),
    ("spacely", "search_tire_kicker", False),
    ("cogswell", "abm_impressions", False),
    ("yoyodyne", "abm_impressions", False),
    ("virtucon", "abm_impressions", False),
    ("contoso", "abm_impressions", False),
    ("fabrikam", "abm_impressions", False),
    ("tessier", "abm_impressions", False),
    ("zorg", "abm_impressions", False),
]


def main() -> None:
    rng = random.Random(SEED)
    touches: list[tuple[str, str, datetime, str, float]] = []
    opps: list[tuple[str, str, datetime, int]] = []
    for account_id, archetype, converts in ACCOUNTS:
        plays = journey(rng, archetype)
        span_days = rng.randint(12, 45)
        end_day = rng.randint(span_days + 1, WINDOW_DAYS - 2)
        end = WINDOW_START + timedelta(days=end_day, hours=rng.randint(9, 17))
        offsets = sorted(rng.uniform(0, span_days * 24) for _ in plays[:-1])
        times = [end - timedelta(hours=span_days * 24 - h) for h in offsets] + [end]
        for play, ts in zip(plays, times):
            touches.append((account_id, play, ts.replace(second=0, microsecond=0),
                            rng.choice(CHANNELS[play]), COST[play]))
        if converts:
            created = end + timedelta(hours=rng.randint(1, 48))
            opps.append((account_id, account_id, created.replace(minute=0), rng.choice(AMOUNTS)))

    touches.sort(key=lambda t: (t[2], t[0]))
    (ROOT / "fixtures").mkdir(exist_ok=True)
    with (ROOT / "fixtures" / "touches.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["touch_id", "account_id", "timestamp", "play", "channel", "cost"])
        for i, (account_id, play, ts, channel, cost) in enumerate(touches, start=1):
            w.writerow([f"T{i:04d}", account_id, ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        play, channel, f"{cost:.2f}"])

    opps.sort(key=lambda o: o[2])
    with (ROOT / "fixtures" / "opportunities.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["opp_id", "account_id", "created_at", "amount"])
        for i, (_, account_id, created, amount) in enumerate(opps, start=1):
            w.writerow([f"OPP-{i:03d}", account_id, created.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        amount])
    print(f"wrote {len(touches)} touches and {len(opps)} opportunities to fixtures/")


if __name__ == "__main__":
    main()
