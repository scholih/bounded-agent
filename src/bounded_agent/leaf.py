"""Chapter 2 — The typed leaf & the escalate-only floor.

This is the ONLY place the library touches an LLM, and the design point is what it does
*around* the call, not the call itself:

- **The leaf wraps a** ``pydantic_ai.Agent``, which already guarantees the model's output is
  a validated instance of your type (or a typed failure). We do not rebuild that — the typed
  call is a solved problem.
- **Error-as-value.** ``TypedLeaf.run`` returns your output type OR a ``LeafError`` — an API
  outage, timeout, or refusal becomes a *value* the control loop folds into its verdict
  (typically "cannot assess"), never an exception ripping through an unattended process.
  An autonomous agent that crashes on a provider hiccup is an agent that silently stops
  watching.
- **The escalate-only floor.** When an LLM shares a verdict with deterministic checks, the
  merge rule must be asymmetric: the model may *raise* the alarm level (it noticed something
  the checks cannot see), but it may never *lower* one (a plausible-sounding "all fine" must
  not silence a failing probe). ``escalate_only`` is that rule as a function — write it once,
  test it once, and every leaf in the system inherits the property.
"""
from __future__ import annotations

from typing import Any, Callable, Generic, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

OutputT = TypeVar("OutputT")
T = TypeVar("T")


class LeafError(BaseModel):
    """A failed leaf run, as a value. The caller decides its verdict weight — the safe
    default is 'at least cannot-assess', never 'ignore'."""
    model_config = ConfigDict(frozen=True)

    kind: str        # exception type name
    detail: str


class _Runnable(Protocol):
    """Structurally, all we need from a pydantic_ai.Agent."""
    def run_sync(self, prompt: str, *, deps: Any = ...) -> Any: ...


class TypedLeaf(Generic[OutputT]):
    """Wraps an ``Agent[..., OutputT]``; ``run`` returns ``OutputT | LeafError``."""

    def __init__(self, agent: _Runnable) -> None:
        self._agent = agent

    def run(self, prompt: str, *, deps: Any = None) -> OutputT | LeafError:
        try:
            return self._agent.run_sync(prompt, deps=deps).output
        except Exception as e:  # noqa: BLE001 — the whole point: failure is a value
            return LeafError(kind=type(e).__name__, detail=str(e))


def escalate_only(floor: T, proposed: T | None, *, rank: Callable[[T], int]) -> T:
    """Merge a deterministic ``floor`` with a leaf's ``proposed`` verdict so the result can
    only ever be AS BAD OR WORSE than the floor. ``None`` (the leaf declined or errored)
    keeps the floor. The caller supplies the domain's severity order via ``rank``."""
    if proposed is None:
        return floor
    return proposed if rank(proposed) > rank(floor) else floor
