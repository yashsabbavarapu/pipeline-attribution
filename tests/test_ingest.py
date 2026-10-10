"""CSV parsing: normalization, validation, malformed rows."""
from datetime import timezone
from pathlib import Path

import pytest

from pipeline_attribution.ingest import normalize_play, parse_opportunities, parse_touches

HEADER = "touch_id,account_id,timestamp,play,channel,cost\n"


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_parses_and_normalizes(tmp_path: Path) -> None:
    path = write(tmp_path, "t.csv", HEADER + "T1,acme,2026-09-01T10:00:00Z,Paid Search,google_ads,120\n")
    [t] = parse_touches(path)
    assert t.play == "paid_search"
    assert t.cost == 120.0
    assert t.timestamp.tzinfo is not None


def test_naive_timestamp_read_as_utc(tmp_path: Path) -> None:
    path = write(tmp_path, "t.csv", HEADER + "T1,acme,2026-09-01 10:00,referral,partner,0\n")
    [t] = parse_touches(path)
    assert t.timestamp.tzinfo == timezone.utc


@pytest.mark.parametrize(
    "raw,expected",
    [("Paid social / ABM", "paid_social_abm"), ("outbound-sequence", "outbound_sequence"),
     ("  Website Visit ", "website_visit")],
)
def test_normalize_play(raw: str, expected: str) -> None:
    assert normalize_play(raw) == expected


def test_malformed_rows_skipped_with_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    body = HEADER + (
        "T1,acme,2026-09-01T10:00:00Z,referral,partner,0\n"
        "T2,acme,not-a-date,referral,partner,0\n"
        "T3,acme,2026-09-01T10:00:00Z,referral,partner,-5\n"
        ",acme,2026-09-01T10:00:00Z,referral,partner,0\n"
    )
    touches = parse_touches(write(tmp_path, "t.csv", body))
    assert [t.touch_id for t in touches] == ["T1"]
    assert capsys.readouterr().err.count("row skipped") == 3


def test_duplicate_touch_id_keeps_later_row(tmp_path: Path) -> None:
    body = HEADER + (
        "T1,acme,2026-09-01T10:00:00Z,referral,partner,0\n"
        "T1,acme,2026-09-01T10:00:00Z,referral,partner,50\n"
    )
    [t] = parse_touches(write(tmp_path, "t.csv", body))
    assert t.cost == 50.0


def test_missing_column_is_fatal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cost"):
        parse_touches(write(tmp_path, "t.csv", "touch_id,account_id,timestamp,play,channel\n"))


def test_parses_opportunities(tmp_path: Path) -> None:
    body = "opp_id,account_id,created_at,amount\nO1,acme,2026-09-10T00:00:00Z,48000\nO2,acme,2026-09-10,0\n"
    opps = parse_opportunities(write(tmp_path, "o.csv", body))
    assert [(o.opp_id, o.amount) for o in opps] == [("O1", 48_000.0)]
