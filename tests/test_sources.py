"""The ingest boundary: CSV works, CRM sources are explicit v2 stubs."""
from pathlib import Path

import pytest

from pipeline_attribution.sources import CsvSource, HubSpotSource, SalesforceSource, Source

REPO = Path(__file__).resolve().parent.parent


def test_csv_source() -> None:
    source: Source = CsvSource(REPO / "fixtures" / "touches.csv")
    assert len(source.touches()) > 150
    assert source.opportunities() == []


@pytest.mark.parametrize("source", [SalesforceSource(), HubSpotSource()])
def test_crm_sources_are_honest_stubs(source: Source) -> None:
    with pytest.raises(NotImplementedError, match="v2"):
        source.touches()
    with pytest.raises(NotImplementedError, match="v2"):
        source.opportunities()
