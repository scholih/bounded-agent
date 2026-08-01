"""Chapter 2 — the typed leaf & the escalate-only floor.

The invariants under test:
- a leaf returns a validated typed output OR a LeafError VALUE — a model/API failure never
  escapes as an exception into the control loop;
- escalate_only lets a leaf RAISE a deterministic floor but never lower it — the single most
  important safety property of putting an LLM inside an autonomous loop.
"""
from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from bounded_agent.leaf import LeafError, TypedLeaf, escalate_only


class Verdict(BaseModel):
    level: str
    note: str = ""


class _ExplodingAgent:
    def run_sync(self, prompt, *, deps=None):  # noqa: ANN001
        raise RuntimeError("provider outage")


def test_leaf_returns_typed_output():
    agent = Agent(TestModel(custom_output_args={"level": "warning", "note": "queue depth"}),
                  output_type=Verdict)
    out = TypedLeaf(agent).run("evidence...")
    assert isinstance(out, Verdict) and out.level == "warning"


def test_leaf_failure_is_a_value():
    out = TypedLeaf(_ExplodingAgent()).run("x")
    assert isinstance(out, LeafError)
    assert out.kind == "RuntimeError" and "provider outage" in out.detail


RANK = {"ok": 0, "cannot-assess": 1, "alert": 2}.__getitem__


def test_escalate_only_none_keeps_floor():
    assert escalate_only("ok", None, rank=RANK) == "ok"
    assert escalate_only("alert", None, rank=RANK) == "alert"


def test_escalate_only_raises_floor():
    assert escalate_only("ok", "alert", rank=RANK) == "alert"


def test_escalate_only_never_lowers_floor():
    # The LLM says everything is fine; the deterministic floor already said alert. Floor wins.
    assert escalate_only("alert", "ok", rank=RANK) == "alert"


def test_escalate_only_equal_keeps_floor():
    assert escalate_only("cannot-assess", "cannot-assess", rank=RANK) == "cannot-assess"
