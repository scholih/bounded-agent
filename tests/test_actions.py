"""Chapter 3 — the double-closed action set.

The invariants under test:
- nothing runs through a disarmed envelope or past a kill-switch;
- an action runs only if BOTH contracted (in the granted map) AND registered (implemented) —
  a contracted-but-unregistered action is refused, recorded, and never executed;
- a handler that RAISES becomes an executed-failed record (ledgered + notified + counted
  toward the breaker) — never an exception escaping the loop;
- the breaker halts at the budget and the halt itself is recorded;
- every record lands in the evidence ledger and through notify (silence impossible).
"""
from __future__ import annotations

import datetime as dt
import json

from bounded_agent.actions import ActionSet
from bounded_agent.envelope import Envelope
from bounded_agent.ledgers import EvidenceLedger

DAY = dt.date(2026, 8, 1)


def _actions(calls: list[str], *, failing: set[str] = frozenset()) -> ActionSet:
    acts = ActionSet()
    for name in ("restart_worker", "clear_cache", "rotate_logs"):
        def handler(n=name):
            calls.append(n)
            return (n not in failing, f"ran {n}")
        acts.register(name, handler)
    return acts


def test_disarmed_runs_nothing():
    calls: list[str] = []
    out = _actions(calls).execute([("queue-worker", ("restart_worker",))], Envelope())
    assert out.blocked_reason == "disarmed" and calls == [] and out.executed == 0
    assert out.records[0].status == "halted"


def test_kill_switch_runs_nothing(tmp_path):
    ks = tmp_path / "STOP"
    ks.touch()
    calls: list[str] = []
    out = _actions(calls).execute([("queue-worker", ("restart_worker",))],
                                  Envelope(armed=True, kill_switch_path=ks))
    assert out.blocked_reason == "kill-switch" and calls == []


def test_contracted_and_registered_executes():
    calls: list[str] = []
    out = _actions(calls).execute([("queue-worker", ("restart_worker",))],
                                  Envelope(armed=True, max_actions_per_run=5))
    assert calls == ["restart_worker"]
    assert out.records[0].status == "executed-ok" and out.executed == 1


def test_contracted_but_unregistered_is_refused():
    calls: list[str] = []
    out = _actions(calls).execute([("queue-worker", ("drop_database",))],
                                  Envelope(armed=True, max_actions_per_run=5))
    assert calls == [] and out.executed == 0
    assert out.records[0].status == "refused"


def test_failing_handler_records_executed_failed():
    calls: list[str] = []
    out = _actions(calls, failing={"clear_cache"}).execute(
        [("cache", ("clear_cache",))], Envelope(armed=True, max_actions_per_run=5))
    assert out.records[0].status == "executed-failed"


def test_raising_handler_is_a_record_not_an_escape(tmp_path):
    acts = ActionSet()

    def boom():
        raise RuntimeError("handler exploded")
    acts.register("boom", boom)

    seen: list[str] = []
    ledger = EvidenceLedger(tmp_path / "ev")
    out = acts.execute([("svc", ("boom",))],
                       Envelope(armed=True, max_actions_per_run=5, notify=seen.append),
                       ledger=ledger, period=DAY)
    assert out.records[0].status == "executed-failed"
    assert "handler exploded" in out.records[0].detail
    assert out.executed == 1                       # a crash still spends breaker budget
    assert seen and "boom" in seen[0]              # act-then-report on failure too
    line = (tmp_path / "ev" / f"{DAY.isoformat()}.jsonl").read_text().strip()
    assert json.loads(line)["status"] == "executed-failed"


def test_breaker_halts_at_budget_and_records_the_halt():
    calls: list[str] = []
    out = _actions(calls).execute([("svc", ("restart_worker", "clear_cache"))],
                                  Envelope(armed=True, max_actions_per_run=1))
    assert calls == ["restart_worker"]
    assert [r.status for r in out.records] == ["executed-ok", "halted"]


def test_every_record_is_notified_and_ledgered(tmp_path):
    calls: list[str] = []
    seen: list[str] = []
    ledger = EvidenceLedger(tmp_path / "ev")
    _actions(calls).execute([("svc", ("restart_worker", "drop_database"))],
                            Envelope(armed=True, max_actions_per_run=5, notify=seen.append),
                            ledger=ledger, period=DAY)
    lines = (tmp_path / "ev" / f"{DAY.isoformat()}.jsonl").read_text().splitlines()
    assert len(lines) == 2 and len(seen) == 2       # the refusal is recorded too


def test_outcome_summary_reads_like_a_report():
    calls: list[str] = []
    out = _actions(calls).execute([("svc", ("restart_worker", "drop_database"))],
                                  Envelope(armed=True, max_actions_per_run=5))
    s = out.summary()
    assert "1 executed" in s
    assert "svc:restart_worker=executed-ok" in s
    assert "svc:drop_database=refused" in s


def test_outcome_summary_when_blocked():
    out = _actions([]).execute([("svc", ("restart_worker",))], Envelope())
    assert out.summary() == "blocked: disarmed"
