"""The ingest boundary. v1 ships the CSV source; CRM sources are v2 stubs.

Anything that can produce Touch and Opportunity records plugs in here, and
attribution, storage and the readout never change.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pipeline_attribution.ingest import parse_opportunities, parse_touches
from pipeline_attribution.models import Opportunity, Touch


class Source(Protocol):
    def touches(self) -> list[Touch]: ...

    def opportunities(self) -> list[Opportunity]: ...


class CsvSource:
    def __init__(self, touches: Path, opportunities: Path | None = None) -> None:
        self._touches = touches
        self._opportunities = opportunities

    def touches(self) -> list[Touch]:
        return parse_touches(self._touches)

    def opportunities(self) -> list[Opportunity]:
        return parse_opportunities(self._opportunities) if self._opportunities else []


class SalesforceSource:
    """v2: campaign members and tasks as touches, opportunities with created dates."""

    def touches(self) -> list[Touch]:
        raise NotImplementedError("Salesforce touchpoint sync is on the v2 roadmap")

    def opportunities(self) -> list[Opportunity]:
        raise NotImplementedError("Salesforce opportunity sync is on the v2 roadmap")


class HubSpotSource:
    """v2: marketing events and engagements as touches, deals as opportunities."""

    def touches(self) -> list[Touch]:
        raise NotImplementedError("HubSpot touchpoint sync is on the v2 roadmap")

    def opportunities(self) -> list[Opportunity]:
        raise NotImplementedError("HubSpot deal sync is on the v2 roadmap")
