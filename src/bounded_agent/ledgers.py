"""Chapter 4 — Ledgers: append-only evidence, and alerting once instead of forever.

Two small ledgers carry the entire audit story of a bounded agent:

- ``EvidenceLedger`` — **append-only truth.** Every action taken (and refused) and every
  verdict formed is one JSONL line, partitioned by period. Nothing is ever rewritten; if a
  later reading disagrees with an earlier one, that disagreement is itself a new line. This
  is what lets a human audit an unattended agent after the fact — and what makes the agent's
  own reports checkable against ground truth.

- ``IdempotencyLedger`` — **the anti-alert-rot mechanism.** A finding fingerprint is "new"
  exactly once per period; repeats are recorded but not re-raised. Alert fatigue is a safety
  failure — a pager that fires on the same stale finding every run trains its humans to stop
  reading it, which is how real incidents get ignored.

Both write atomically (tmp + rename) into a directory the agent OWNS — a bounded agent never
writes outside its own namespace.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

#: Periods are dates or plain strings ("2026-W31") — the dedup window is the caller's choice.
Period = dt.date | str


def _key(period: Period) -> str:
    return period.isoformat() if isinstance(period, dt.date) else str(period)


class EvidenceLedger:
    """Append-only JSONL evidence log, partitioned by period."""

    def __init__(self, ledger_dir: Path | str) -> None:
        self._dir = Path(ledger_dir)

    def append(self, record: BaseModel | dict[str, Any], *, period: Period) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = record.model_dump() if isinstance(record, BaseModel) else dict(record)
        with (self._dir / f"{_key(period)}.jsonl").open("a") as f:
            f.write(json.dumps(payload) + "\n")


class IdempotencyLedger:
    """Fingerprint-per-period dedup with atomic writes."""

    def __init__(self, ledger_dir: Path | str) -> None:
        self._dir = Path(ledger_dir)

    def _path(self, period: Period) -> Path:
        return self._dir / f"seen_{_key(period)}.json"

    def seen(self, period: Period) -> set[str]:
        p = self._path(period)
        if not p.exists():
            return set()
        return set(json.loads(p.read_text()).get("fingerprints", []))

    def new_fingerprints(self, period: Period, fingerprints: list[str]) -> list[str]:
        seen = self.seen(period)
        return [f for f in fingerprints if f not in seen]

    def record(self, period: Period, fingerprints: list[str]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        merged = sorted(self.seen(period) | set(fingerprints))
        p = self._path(period)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"period": _key(period), "fingerprints": merged},
                                  indent=2) + "\n")
        os.replace(tmp, p)      # atomic: a crash never leaves a half-written dedup file
