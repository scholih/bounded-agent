"""Chapter 4 — ledgers: append-only evidence + alert-once-per-period dedup.

The invariants under test:
- the evidence ledger only ever appends (one JSONL line per record, partitioned by period);
- the idempotency ledger reports a fingerprint as new exactly once per period, cumulatively;
- writes are atomic (tmp + rename) so a crash never leaves a half-written dedup file.
"""
from __future__ import annotations

import datetime as dt
import json

from pydantic import BaseModel

from bounded_agent.ledgers import EvidenceLedger, IdempotencyLedger

DAY = dt.date(2026, 8, 1)


class _Rec(BaseModel):
    action: str
    ok: bool


def test_idempotency_round_trip(tmp_path):
    led = IdempotencyLedger(tmp_path / "dedup")
    assert led.new_fingerprints(DAY, ["a", "b"]) == ["a", "b"]
    led.record(DAY, ["a", "b"])
    assert led.new_fingerprints(DAY, ["a", "b", "c"]) == ["c"]
    assert led.seen(DAY) == {"a", "b"}


def test_idempotency_record_is_cumulative(tmp_path):
    led = IdempotencyLedger(tmp_path / "dedup")
    led.record(DAY, ["a"])
    led.record(DAY, ["b"])
    assert led.seen(DAY) == {"a", "b"}


def test_idempotency_periods_are_independent(tmp_path):
    led = IdempotencyLedger(tmp_path / "dedup")
    led.record(DAY, ["a"])
    assert led.new_fingerprints(DAY + dt.timedelta(days=1), ["a"]) == ["a"]


def test_idempotency_accepts_string_periods(tmp_path):
    led = IdempotencyLedger(tmp_path / "dedup")
    led.record("2026-W31", ["a"])
    assert led.seen("2026-W31") == {"a"}


def test_evidence_appends_one_line_per_record(tmp_path):
    led = EvidenceLedger(tmp_path / "evidence")
    led.append(_Rec(action="restart", ok=True), period=DAY)
    led.append({"action": "verify", "ok": False}, period=DAY)   # plain dicts too
    lines = (tmp_path / "evidence" / f"{DAY.isoformat()}.jsonl").read_text().splitlines()
    assert [json.loads(x)["action"] for x in lines] == ["restart", "verify"]


def test_evidence_partitions_by_period(tmp_path):
    led = EvidenceLedger(tmp_path / "evidence")
    led.append({"x": 1}, period=DAY)
    led.append({"x": 2}, period="2026-W31")
    assert (tmp_path / "evidence" / f"{DAY.isoformat()}.jsonl").exists()
    assert (tmp_path / "evidence" / "2026-W31.jsonl").exists()
