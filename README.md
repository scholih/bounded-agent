# bounded-agent

**Contract-bounded autonomy for LLM agents: five small primitives that make an agent safe to
leave alone.**

The model is table stakes. The reliability of an autonomous agent lives in the **harness** —
the deterministic structure around the LLM that decides what it may see, what it may say, what
it may do, and what happens when it fails. This library is that harness, reduced to its five
load-bearing primitives, each ~50 lines, each independently testable, built on top of
[PydanticAI](https://ai.pydantic.dev) (which already solves the typed-LLM-call problem — we
don't rebuild it, we add the autonomy layer it deliberately leaves to you).

The design stance, in one sentence: **deterministic spine, agentic leaves** — code you can
test decides the flow; the LLM reasons inside well-fenced steps and never pilots the loop.

## The five primitives

| Module | Primitive | The failure it prevents |
|---|---|---|
| `contracts.py` | **Contracts & gates** — a declared book of who may do what, at which autonomy tier (observe / propose / act) | an agent quietly acquiring capabilities nobody signed off on |
| `leaf.py` | **The typed leaf & the escalate-only floor** — LLM output is a validated type or an error *value*; an LLM may raise an alarm, never silence one | a plausible-sounding model response lowering a deterministic alarm |
| `actions.py` | **The double-closed action set** — an action runs only if it is both *contracted* and *implemented*; everything else is refused and recorded | prompt-injected or hallucinated actions; silent capability creep |
| `ledgers.py` | **Evidence & idempotency ledgers** — append-only truth for every action and verdict; a finding alerts once per period, not forever | un-auditable agents; alert fatigue that trains humans to ignore the pager |
| `envelope.py` | **The safety envelope** — ships disarmed, kill-switch checked before anything runs, a hard per-run breaker, and act-then-report (silence is impossible) | the runaway loop; the agent that did things nobody heard about |

## Quickstart

```bash
uv add bounded-agent            # or: pip install bounded-agent
```

```python
from bounded_agent import ContractBook, Gate, ActionSet, Envelope, EvidenceLedger

book = ContractBook.load("contracts.yaml")            # raises loudly if missing/malformed
gate = Gate(required_scope="checkout-stack", required_tier="act")
granted = book.granted(gate)                          # {contract-name: (allowed actions,)}

actions = ActionSet()
actions.register("restart_worker", restart_worker)    # the implemented closed set

env = Envelope(armed=True, kill_switch_path=Path("STOP"),
               max_actions_per_run=2, notify=page_the_operator)
outcome = actions.execute(list(granted.items()), env,
                          ledger=EvidenceLedger(Path("ledger")), period=today)
```

An action fires only if it appears in **both** the contract's `allows` list **and** the
registered set — and only inside an armed envelope with no kill-switch present and breaker
budget remaining. Everything that happens (and everything refused) is one JSONL line.

For the LLM side, see `examples/sentinel/` — a complete service-health watchdog: deterministic
probes → an escalate-only LLM verdict → a typed diagnosis → contract-bounded remediation.
It runs **offline with no API key** (PydanticAI's `TestModel`) so you can study the whole loop
before connecting a real model.

## What this deliberately is NOT

Stating the non-goals is part of the teaching — most agent failures start with adopting more
machinery than the problem earns:

- **Not a planner.** No GOAP, no A*-search over preconditions. If you can hardcode the flow,
  hardcode the flow.
- **Not a durable-execution engine.** Design your steps idempotent and re-run from clean;
  reach for Temporal/DBOS only when a mid-run crash would genuinely corrupt or double-charge.
- **Not a graph framework.** Small fixed pipelines and explicit state machines in plain code
  beat a graph DSL until your control flow is genuinely graph-shaped.
- **Not a PydanticAI replacement.** The typed leaf is solved; this is the autonomy layer
  above it. If PydanticAI grows this layer, this library should shrink.

## Status

A **teaching artifact**, maintained best-effort. The patterns here are extracted from a
production system that runs unattended daily; the code is written fresh for clarity. Issues
and discussion welcome; roadmap promises are not made.

## License

MIT
