"""SQLite storage (stdlib only). Tables: touchpoints, opportunities, attributions, meta.

Re-ingesting is idempotent: touchpoints are replaced by touch_id and
opportunities by opp_id. Attributions are a pure function of those two
tables, so they are rebuilt in full (inside one transaction) after every
ingest rather than appended. Each attribution row is one touch_id's credit
on one opp_id under one model, which is what makes every dollar traceable.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from pipeline_attribution.models import Credit, Opportunity, Touch

_SCHEMA = """
CREATE TABLE IF NOT EXISTS touchpoints(
    touch_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    play TEXT NOT NULL,
    channel TEXT NOT NULL,
    cost REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS opportunities(
    opp_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS attributions(
    model TEXT NOT NULL,
    opp_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    touch_id TEXT NOT NULL,
    play TEXT NOT NULL,
    weight TEXT NOT NULL,
    credit REAL NOT NULL,
    PRIMARY KEY (model, opp_id, touch_id)
);
CREATE TABLE IF NOT EXISTS meta(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def save_touches(self, rows: list[Touch]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO touchpoints VALUES (?,?,?,?,?,?)",
            [
                (t.touch_id, t.account_id, t.timestamp.isoformat(), t.play, t.channel, t.cost)
                for t in rows
            ],
        )
        self._conn.commit()

    def save_opportunities(self, rows: list[Opportunity]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO opportunities VALUES (?,?,?,?)",
            [(o.opp_id, o.account_id, o.created_at.isoformat(), o.amount) for o in rows],
        )
        self._conn.commit()

    def replace_attributions(self, credits: list[Credit], lookback_days: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM attributions")
            self._conn.executemany(
                "INSERT INTO attributions VALUES (?,?,?,?,?,?,?)",
                [
                    (c.model, c.opp_id, c.account_id, c.touch_id, c.play, str(c.weight), c.credit)
                    for c in credits
                ],
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO meta VALUES ('lookback_days', ?)", (str(lookback_days),)
            )

    def touches(self) -> list[Touch]:
        cur = self._conn.execute(
            "SELECT touch_id, account_id, timestamp, play, channel, cost FROM touchpoints"
            " ORDER BY timestamp, touch_id"
        )
        return [
            Touch(
                touch_id=str(r[0]),
                account_id=str(r[1]),
                timestamp=datetime.fromisoformat(str(r[2])),
                play=str(r[3]),
                channel=str(r[4]),
                cost=float(r[5]),
            )
            for r in cur.fetchall()
        ]

    def opportunities(self) -> list[Opportunity]:
        cur = self._conn.execute(
            "SELECT opp_id, account_id, created_at, amount FROM opportunities ORDER BY opp_id"
        )
        return [
            Opportunity(
                opp_id=str(r[0]),
                account_id=str(r[1]),
                created_at=datetime.fromisoformat(str(r[2])),
                amount=float(r[3]),
            )
            for r in cur.fetchall()
        ]

    def credits(self, model: str | None = None) -> list[Credit]:
        sql = "SELECT a.model, a.opp_id, a.account_id, a.touch_id, a.play, a.weight, a.credit"
        sql += " FROM attributions a JOIN touchpoints t ON t.touch_id = a.touch_id"
        params: tuple[str, ...] = ()
        if model is not None:
            sql += " WHERE a.model = ?"
            params = (model,)
        sql += " ORDER BY a.model, a.opp_id, t.timestamp, a.touch_id"
        return [
            Credit(
                model=str(r[0]),
                opp_id=str(r[1]),
                account_id=str(r[2]),
                touch_id=str(r[3]),
                play=str(r[4]),
                weight=Fraction(str(r[5])),
                credit=float(r[6]),
            )
            for r in self._conn.execute(sql, params).fetchall()
        ]

    def lookback_days(self) -> int | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'lookback_days'").fetchone()
        return None if row is None else int(row[0])

    def counts(self) -> dict[str, int]:
        return {
            table: int(self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("touchpoints", "opportunities", "attributions")
        }
