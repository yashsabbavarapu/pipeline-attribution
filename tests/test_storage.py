"""Idempotent re-ingestion through the CLI and the store."""
from pathlib import Path

from pipeline_attribution.__main__ import main
from pipeline_attribution.storage import Store

REPO = Path(__file__).resolve().parent.parent
FIXTURES = ["--touches", str(REPO / "fixtures" / "touches.csv"),
            "--opportunities", str(REPO / "fixtures" / "opportunities.csv")]


def snapshot(db: Path) -> tuple[dict[str, int], list[tuple[str, str, str, str, float]]]:
    store = Store(db)
    try:
        rows = [(c.model, c.opp_id, c.touch_id, str(c.weight), c.credit) for c in store.credits()]
        return store.counts(), rows
    finally:
        store.close()


def test_reingest_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    assert main(["ingest", *FIXTURES, "--db", str(db)]) == 0
    first = snapshot(db)
    assert main(["ingest", *FIXTURES, "--db", str(db)]) == 0
    assert main(["ingest", *FIXTURES, "--db", str(db)]) == 0
    assert snapshot(db) == first
    assert first[0]["touchpoints"] > 150 and first[0]["opportunities"] > 15


def test_touches_then_opportunities_in_separate_runs(tmp_path: Path) -> None:
    db = tmp_path / "b.db"
    assert main(["ingest", "--touches", FIXTURES[1], "--db", str(db)]) == 0
    assert snapshot(db)[0]["attributions"] == 0
    assert main(["ingest", *FIXTURES, "--db", str(db)]) == 0
    together = tmp_path / "c.db"
    assert main(["ingest", *FIXTURES, "--db", str(together)]) == 0
    assert snapshot(db) == snapshot(together)


def test_reingest_with_corrected_cost_updates_in_place(tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    csv1 = tmp_path / "t1.csv"
    csv2 = tmp_path / "t2.csv"
    header = "touch_id,account_id,timestamp,play,channel,cost\n"
    csv1.write_text(header + "T1,acme,2026-09-01T10:00:00Z,paid_search,google_ads,100\n")
    csv2.write_text(header + "T1,acme,2026-09-01T10:00:00Z,paid_search,google_ads,250\n")
    main(["ingest", "--touches", str(csv1), "--db", str(db)])
    main(["ingest", "--touches", str(csv2), "--db", str(db)])
    store = Store(db)
    [t] = store.touches()
    store.close()
    assert t.cost == 250.0
