"""bounded-agent — contract-bounded autonomy for LLM agents.

Five primitives that make an agent safe to leave alone. Deterministic spine, agentic
leaves: code you can test decides the flow; the LLM reasons inside well-fenced steps and
never pilots the loop. See README.md for the full argument; each module's docstring is a
chapter.
"""
from __future__ import annotations

from bounded_agent.actions import ActionRecord, ActionSet, ExecOutcome
from bounded_agent.contracts import Contract, ContractBook, Gate
from bounded_agent.envelope import Envelope
from bounded_agent.leaf import LeafError, TypedLeaf, escalate_only
from bounded_agent.ledgers import EvidenceLedger, IdempotencyLedger

__all__ = [
    "Contract", "ContractBook", "Gate",
    "TypedLeaf", "LeafError", "escalate_only",
    "ActionSet", "ActionRecord", "ExecOutcome",
    "EvidenceLedger", "IdempotencyLedger",
    "Envelope",
]
