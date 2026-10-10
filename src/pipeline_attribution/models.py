"""Domain models for pipeline attribution."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

FIRST_TOUCH = "first-touch"
LAST_TOUCH = "last-touch"
POSITION_BASED = "position-based"
MODELS = (FIRST_TOUCH, LAST_TOUCH, POSITION_BASED)

# Display labels for the plays the fixtures use. Any other play name is
# accepted on ingest and shown title-cased.
PLAY_LABELS = {
    "outbound_sequence": "Outbound sequence",
    "paid_search": "Paid search",
    "paid_social_abm": "Paid social / ABM",
    "website_visit": "Website visit",
    "demo_request": "Demo request",
    "referral": "Referral",
}


def play_label(play: str) -> str:
    return PLAY_LABELS.get(play, play.replace("_", " ").capitalize())


@dataclass(frozen=True)
class Touch:
    """One marketing or sales touchpoint on an account."""

    touch_id: str
    account_id: str
    timestamp: datetime  # always timezone-aware UTC
    play: str
    channel: str
    cost: float


@dataclass(frozen=True)
class Opportunity:
    """An account becoming pipeline: the event credit is assigned to."""

    opp_id: str
    account_id: str
    created_at: datetime  # always timezone-aware UTC
    amount: float


@dataclass(frozen=True)
class Credit:
    """One traceable unit of credit: this touch earned this share of this opp."""

    model: str
    opp_id: str
    account_id: str
    touch_id: str
    play: str
    weight: Fraction
    credit: float  # opp amount * weight, in dollars
