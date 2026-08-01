"""The sentinel — a service-health watchdog you can leave alone.

The complete contract-bounded loop, end to end, in one file:

    probes (deterministic)  →  floor verdict  →  LLM coherence verdict (escalate-only)
    →  typed diagnosis      →  contract-bounded remediation (double-closed, enveloped)
    →  everything ledgered

Run it with NO API key (the LLM leaves use PydanticAI's TestModel, so you can study the
whole control flow offline):

    uv run python examples/sentinel/sentinel.py

Run it against a real model (set ANTHROPIC_API_KEY):

    uv run python examples/sentinel/sentinel.py --live

The simulated stack ships with one deliberately broken service, so every run exercises the
full path: floor catches it → leaf confirms → diagnosis names it → the contract book decides
what may be done about it → the envelope bounds the doing → the ledger remembers all of it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from bounded_agent import (
    ActionSet, ContractBook, Envelope, EvidenceLedger, Gate, LeafError, TypedLeaf,
    escalate_only,
)

HERE = Path(__file__).parent


# ── 1. Probes — deterministic sensors over the (simulated) stack ─────────────────────────

def run_probes() -> dict[str, dict]:
    """In a real sentinel these hit HTTP health endpoints, disk, queue depth, container
    states. Here they are simulated — with queue-worker deliberately unhealthy."""
    return {
        "checkout-api":  {"status": "ok",   "detail": "200 in 41ms"},
        "cache":         {"status": "ok",   "detail": "hit-rate 0.94"},
        "queue-worker":  {"status": "fail", "detail": "no heartbeat for 22 min; depth 14 302 and rising"},
        "payments-db":   {"status": "ok",   "detail": "replica lag 0.4s"},
    }


# ── 2. The deterministic floor — the LLM never gets to overrule this ─────────────────────

LEVELS = {"ok": 0, "cannot-assess": 1, "alert": 2}

def floor_verdict(probes: dict[str, dict]) -> str:
    statuses = {p["status"] for p in probes.values()}
    if "fail" in statuses:
        return "alert"
    if "unavailable" in statuses:      # missing evidence is never "ok"
        return "cannot-assess"
    return "ok"


# ── 3. Two typed leaves — the ONLY places a model runs ───────────────────────────────────

class Coherence(BaseModel):
    """Does the evidence cohere as a whole? The leaf may only ESCALATE the floor."""
    level: Literal["ok", "alert"]
    note: str

class Diagnosis(BaseModel):
    root_cause: str
    evidence: list[str]
    proposed_next_step: str
    confidence: Literal["high", "medium", "low"]


def build_leaves(live: bool) -> tuple[TypedLeaf, TypedLeaf]:
    if live:
        coherence = Agent("anthropic:claude-sonnet-4-6", output_type=Coherence,
                          system_prompt="You review service-health evidence for cross-signal "
                                        "contradictions the individual checks cannot see.")
        diagnosis = Agent("anthropic:claude-sonnet-4-6", output_type=Diagnosis,
                          system_prompt="Diagnose the most likely root cause from the "
                                        "evidence alone. One concrete next step. Be terse.")
    else:  # offline: scripted model outputs — the control flow is identical
        coherence = Agent(TestModel(custom_output_args={
            "level": "alert", "note": "queue depth rising while worker heartbeat silent"}),
            output_type=Coherence)
        diagnosis = Agent(TestModel(custom_output_args={
            "root_cause": "queue-worker process wedged after cache failover",
            "evidence": ["queue-worker heartbeat silent 22m", "depth 14302 rising"],
            "proposed_next_step": "restart queue-worker; page if depth not draining in 10m",
            "confidence": "high"}), output_type=Diagnosis)
    return TypedLeaf(coherence), TypedLeaf(diagnosis)


# ── 4. The run ───────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use a real model (needs API key)")
    ap.add_argument("--armed", action="store_true",
                    help="arm remediation (ships disarmed, like everything should)")
    args = ap.parse_args()

    today = dt.date.today()
    ledger = EvidenceLedger(HERE / "run_ledger")
    notify = lambda msg: print(f"  [notify] {msg}")          # stand-in for a pager/Slack hook

    # observe
    probes = run_probes()
    floor = floor_verdict(probes)
    print(f"floor verdict: {floor}")

    # reason (escalate-only: the leaf can raise the floor, never lower it)
    coherence_leaf, diagnosis_leaf = build_leaves(args.live)
    coh = coherence_leaf.run(json.dumps(probes))
    proposed = None if isinstance(coh, LeafError) else coh.level
    verdict = escalate_only(floor, proposed, rank=LEVELS.__getitem__)
    if isinstance(coh, LeafError):                            # leaf failure is a VALUE:
        verdict = escalate_only(verdict, "cannot-assess", rank=LEVELS.__getitem__)
    print(f"merged verdict: {verdict}" + (f"  ({coh.note})" if isinstance(coh, Coherence) else ""))
    ledger.append({"kind": "verdict", "floor": floor, "verdict": verdict}, period=today)

    if verdict == "ok":
        print("clean day — the sentinel goes back to sleep.")
        return 0

    # diagnose (typed, best-effort)
    diag = diagnosis_leaf.run(json.dumps(probes))
    if isinstance(diag, Diagnosis):
        print(f"diagnosis [{diag.confidence}]: {diag.root_cause}")
        print(f"  next step: {diag.proposed_next_step}")
        ledger.append({"kind": "diagnosis", **diag.model_dump()}, period=today)

    # act — only inside the book, only inside the envelope
    book = ContractBook.load(HERE / "contracts.yaml")
    granted = book.granted(Gate(required_scope="checkout-stack", required_tier="act"))
    failing = [name for name, p in probes.items() if p["status"] == "fail"]
    targets = [(n, granted[n]) for n in failing if n in granted]
    print(f"contract book grants ACT on: {sorted(granted)} → actionable now: "
          f"{[t[0] for t in targets] or 'nothing (alert-only)'}")

    acts = ActionSet()
    acts.register("restart_worker", lambda: (True, "worker restarted (simulated)"))
    env = Envelope(armed=args.armed, kill_switch_path=HERE / "STOP",
                   max_actions_per_run=1, notify=notify)
    outcome = acts.execute(targets, env, ledger=ledger, period=today)
    if outcome.blocked_reason:
        print(f"remediation blocked: {outcome.blocked_reason} "
              f"(run with --armed; `touch STOP` to kill-switch)")
    print(f"ledger: {HERE / 'run_ledger'}")
    return 1 if verdict != "ok" else 0


if __name__ == "__main__":
    sys.exit(main())
