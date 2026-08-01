"""Chapter 5 — The safety envelope: the gates every autonomous action passes through.

Four invariants, one small object. They read as paranoia until the first time an unattended
loop misbehaves; then they read as the minimum:

- **Ships disarmed.** ``armed=False`` is the constructor default. Autonomy is switched on
  per deployment by a human, after the agent has earned a track record in observe/propose
  mode — never on by virtue of the code existing.
- **Kill-switch.** A sentinel *file*, checked before anything runs. Files beat config flags
  here: an operator (or another watchdog) can stop the agent out-of-band with ``touch STOP``,
  with no deploy, no restart, no working control plane required.
- **Per-run breaker.** A hard cap on actions per run. Whatever goes wrong — a looping model,
  a pathological finding, a bug — the blast radius is N actions and then a halt, not an
  unbounded cascade.
- **Act-then-report.** Every action (including refusals and halts) goes through ``notify``.
  An autonomous agent whose actions can be silent is unauditable; silence must be
  *structurally impossible*, not a logging convention.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict


def _noop(_msg: str) -> None:
    return None


class Envelope(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    armed: bool = False
    kill_switch_path: Path | None = None
    max_actions_per_run: int = 1
    notify: Callable[[str], None] = _noop

    def blocked_reason(self) -> str | None:
        """Why NO action may run right now; ``None`` means clear to act."""
        if not self.armed:
            return "disarmed"
        if self.kill_switch_path is not None and self.kill_switch_path.exists():
            return "kill-switch"
        return None

    def breaker_tripped(self, executed: int) -> bool:
        """True once ``executed`` actions have already run this run — the next is refused."""
        return executed >= self.max_actions_per_run
