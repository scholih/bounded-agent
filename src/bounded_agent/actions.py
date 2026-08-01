"""Chapter 3 — The double-closed action set: agent actions safe by construction.

An autonomous agent's actions must clear TWO independent closed sets before running:

1. **Contracted** — the action name appears in a contract's ``allows`` list that a ``Gate``
   granted (chapter 1). A human put that name in the book.
2. **Registered** — the action name has an implementation registered here. An engineer wrote
   and reviewed that handler.

The intersection is the executable surface; everything else — a typo'd contract, a
hallucinated action name, a prompt-injected "please also run …" — is **refused and
recorded**, not an error path someone forgot. Capability creep now requires changing two
artifacts, in two reviews.

Execution runs inside the envelope (chapter 5) and journals to the evidence ledger
(chapter 4). Two details that earn their keep:

- **A raising handler is a recorded failure, not an escape.** After an action *starts*,
  every outcome — success, failure, crash — must become a record that is ledgered and
  notified. An exception unwinding through an unattended loop is an agent that stops
  watching mid-run and tells nobody.
- **Failed attempts spend breaker budget.** The breaker bounds *attempts*, not successes —
  a handler that crashes N times in a loop is exactly the runaway the breaker exists for.
"""
from __future__ import annotations

from typing import Callable, Literal, Sequence

from pydantic import BaseModel, ConfigDict

from bounded_agent.envelope import Envelope
from bounded_agent.ledgers import EvidenceLedger, Period

#: A handler does the work and reports (ok, detail). What "the work" is — a subprocess, an
#: API call, a container restart — is its business; the set only knows names and outcomes.
Handler = Callable[[], tuple[bool, str]]

#: (contract_name, the action names that contract allows) — straight from ContractBook.granted.
Target = tuple[str, Sequence[str]]

Status = Literal["executed-ok", "executed-failed", "refused", "halted"]


class ActionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract: str
    action: str
    status: Status
    detail: str = ""


class ExecOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    blocked_reason: str | None          # disarmed | kill-switch | None (ran)
    records: tuple[ActionRecord, ...] = ()
    executed: int = 0                   # attempts, successful or not

    def summary(self) -> str:
        """One human line for logs/pagers: what ran, what was refused, what halted."""
        if self.blocked_reason is not None:
            return f"blocked: {self.blocked_reason}"
        if not self.records:
            return "0 executed (nothing actionable)"
        parts = [f"{r.contract}:{r.action}={r.status}" for r in self.records]
        return f"{self.executed} executed | " + "; ".join(parts)


class ActionSet:
    """The registered half of the double-closed check, plus the execution loop."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, name: str, handler: Handler) -> None:
        self._handlers[name] = handler

    def execute(self, targets: Sequence[Target], envelope: Envelope, *,
                ledger: EvidenceLedger | None = None,
                period: Period | None = None) -> ExecOutcome:
        def emit(rec: ActionRecord) -> None:
            if ledger is not None and period is not None:
                ledger.append(rec, period=period)
            envelope.notify(f"{rec.status}: {rec.action} on {rec.contract}"
                            + (f" ({rec.detail})" if rec.detail else ""))

        blocked = envelope.blocked_reason()
        if blocked is not None:
            rec = ActionRecord(contract="*", action="*", status="halted", detail=blocked)
            emit(rec)
            return ExecOutcome(blocked_reason=blocked, records=(rec,))

        records: list[ActionRecord] = []
        executed = 0
        for contract, actions in targets:
            for action in actions:
                if envelope.breaker_tripped(executed):
                    rec = ActionRecord(contract=contract, action=action, status="halted",
                                       detail=f"breaker: {envelope.max_actions_per_run}/run")
                    records.append(rec); emit(rec)
                    return ExecOutcome(blocked_reason=None, records=tuple(records),
                                       executed=executed)
                handler = self._handlers.get(action)
                if handler is None:              # contracted but not implemented → refused
                    rec = ActionRecord(contract=contract, action=action, status="refused",
                                       detail="not registered (closed set)")
                    records.append(rec); emit(rec)
                    continue
                try:
                    ok, detail = handler()
                    status: Status = "executed-ok" if ok else "executed-failed"
                except Exception as e:  # noqa: BLE001 — a crash is a RECORD, never an escape
                    detail, status = f"{type(e).__name__}: {e}", "executed-failed"
                rec = ActionRecord(contract=contract, action=action, status=status,
                                   detail=detail)
                records.append(rec); emit(rec)
                executed += 1                    # attempts spend breaker budget
        return ExecOutcome(blocked_reason=None, records=tuple(records), executed=executed)
