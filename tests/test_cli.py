"""CLI smoke tests: ingest fixtures, report under each model, trace one opp."""
from pathlib import Path

import pytest

from pipeline_attribution.__main__ import main

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "cli.db"
    assert main(["ingest", "--touches", str(REPO / "fixtures" / "touches.csv"),
                 "--opportunities", str(REPO / "fixtures" / "opportunities.csv"),
                 "--db", str(path)]) == 0
    return path


@pytest.mark.parametrize("model", ["first-touch", "last-touch", "position-based"])
def test_report_each_model(db: Path, tmp_path: Path, model: str) -> None:
    out = tmp_path / f"{model}.md"
    assert main(["report", "--model", model, "--db", str(db), "--output", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Pipeline Attribution Readout")
    assert f"_Model: **{model}**" in text
    assert "Paid search looks like the winner" in text
    assert "\u2014" not in text  # house style: no em dashes


def test_trace(db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["trace", "--opp", "OPP-001", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("OPP-001")
    assert "| touch_id |" in out and "100%" in out


def test_trace_unknown_opp(db: Path) -> None:
    assert main(["trace", "--opp", "NOPE", "--db", str(db)]) == 1


def test_unknown_model_rejected(db: Path) -> None:
    with pytest.raises(SystemExit):
        main(["report", "--model", "linear", "--db", str(db)])
