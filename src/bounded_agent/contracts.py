"""Chapter 1 — Contracts & gates: deciding who may do what, before any agent runs.

The pattern: autonomy is granted by a **declared book of contracts**, never by code that
happens to be reachable. A human edits the book (and signs off on new entries); the machine
operates strictly inside it. Each contract names:

- a ``scope`` — the blast-radius label ("checkout-stack", "reporting-db") the grant is
  confined to;
- a ``tier`` — how much autonomy: ``observe`` (read and report), ``propose`` (draft a fix a
  human executes), ``act`` (execute its own ``allows`` list). Tiers are ORDERED: an ``act``
  contract clears a ``propose`` gate, never the reverse;
- an ``allows`` list — the CLOSED set of action names the contract permits (see
  ``actions.py`` for the second half of the double-closed check).

Two hard rules encoded here:

1. **Absence is never authorization.** A missing or malformed book RAISES; an entry that is
   not active, out of scope, or under-tiered grants nothing. There is no default-allow path.
2. **The lifecycle vocabulary belongs to the caller.** Your workflow might call live entries
   "active", "LIVE", or "ratified" — the gate's ``active_status`` is configurable rather than
   baked into a type, because a library that hardcodes your status words will be wrong in
   somebody's workflow.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

Tier = Literal["observe", "propose", "act"]

#: The ordering that makes tiers meaningful: a gate requiring tier T grants any contract
#: whose tier ranks >= T.
_TIER_RANK: dict[str, int] = {"observe": 0, "propose": 1, "act": 2}


class Contract(BaseModel):
    """One declared grant. Extra YAML fields (owners, SLAs, notes) are ignored — the book
    can carry your operational metadata without this library needing to model it."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    status: str = "active"
    scope: str
    tier: Tier = "observe"
    allows: tuple[str, ...] = ()


class Gate(BaseModel):
    """A composable authorization predicate — the question "may this contract act here?"
    asked the same way every time, instead of scattered ``if`` statements."""
    model_config = ConfigDict(frozen=True)

    required_scope: str | None = None       # None = any scope (rare; prefer naming one)
    required_tier: Tier = "act"
    active_status: str = "active"           # the caller's word for "live", verbatim

    def permits(self, contract: Contract) -> bool:
        if contract.status != self.active_status:
            return False
        if self.required_scope is not None and contract.scope != self.required_scope:
            return False
        return _TIER_RANK[contract.tier] >= _TIER_RANK[self.required_tier]


class ContractBook(BaseModel):
    """The parsed book. ``granted(gate)`` answers the only question the executor may ask:
    which contracts may act, and what exactly does each allow."""
    model_config = ConfigDict(frozen=True)

    contracts: tuple[Contract, ...] = ()

    @classmethod
    def load(cls, path: Path | str) -> "ContractBook":
        """Parse a ``contracts:`` YAML file. Raises on absence or malformation — the caller
        decides whether that halts startup or degrades to observe-only, but it is never
        silently treated as an empty (or worse, permissive) book."""
        doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "contracts" not in doc:
            raise ValueError(f"{path}: expected a top-level 'contracts' list")
        return cls(contracts=tuple(Contract(**e) for e in doc["contracts"]))

    def granted(self, gate: Gate) -> dict[str, tuple[str, ...]]:
        return {c.name: c.allows for c in self.contracts if gate.permits(c)}
