"""Chapter 5 — the safety envelope.

The invariants under test:
- ships DISARMED (armed=False is the constructor default — autonomy is opt-in, per deploy);
- a kill-switch file blocks everything even when armed, checked before any work;
- the breaker trips at exactly the budget, not one past it;
- notify is always callable (act-then-report needs a hook that can't be None).
"""
from __future__ import annotations

from bounded_agent.envelope import Envelope


def test_ships_disarmed():
    assert Envelope().blocked_reason() == "disarmed"


def test_armed_and_clear():
    assert Envelope(armed=True).blocked_reason() is None


def test_kill_switch_blocks_even_armed(tmp_path):
    ks = tmp_path / "STOP"
    ks.touch()
    assert Envelope(armed=True, kill_switch_path=ks).blocked_reason() == "kill-switch"


def test_kill_switch_absent_is_clear(tmp_path):
    assert Envelope(armed=True, kill_switch_path=tmp_path / "STOP").blocked_reason() is None


def test_breaker_trips_at_budget():
    env = Envelope(armed=True, max_actions_per_run=2)
    assert [env.breaker_tripped(n) for n in (0, 1, 2, 3)] == [False, False, True, True]


def test_notify_hooks():
    seen: list[str] = []
    Envelope(notify=seen.append).notify("acted")
    assert seen == ["acted"]
    Envelope().notify("default is a safe no-op")   # must not raise
