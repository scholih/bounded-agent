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

**The manifesto:** [The Edge Is the Harness, Not the Model](https://medium.com/@scholih/the-edge-is-the-harness-not-the-model-a543abade391) — the argument this library implements, and the start of a series that takes each primitive in depth.

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

First, the book — autonomy starts with a human-edited file, so the quickstart does too.
`contracts.yaml`:

```yaml
contracts:
  - name: queue-worker
    status: active
    scope: checkout-stack
    tier: act                     # observe | propose | act
    allows: [restart_worker]
  - name: cache
    status: active
    scope: checkout-stack
    tier: propose                 # may draft fixes; a human executes them
    allows: [clear_cache]
  - name: payments-db
    status: proposed              # not signed off — grants NOTHING until active
    scope: checkout-stack
    tier: act
    allows: [failover_replica]
```

```python
import datetime as dt
from pathlib import Path

from bounded_agent import ActionSet, ContractBook, Envelope, EvidenceLedger, Gate

print("1. the book — who may do what, declared by a human:")
book = ContractBook.load("contracts.yaml")            # raises loudly if missing/malformed
for c in book.contracts:
    print(f"   {c.name}: status={c.status} scope={c.scope} tier={c.tier} allows={list(c.allows)}")

gate = Gate(required_scope="checkout-stack", required_tier="act")
granted = book.granted(gate)
print(f"\n2. the gate — scope={gate.required_scope!r} at tier '{gate.required_tier}' grants:")
print(f"   {granted or 'nothing — no active, in-scope contract at this tier'}")

actions = ActionSet()                                 # the implemented closed set:
actions.register("restart_worker", lambda: (True, "worker restarted"))

env = Envelope(armed=True,                            # ships disarmed; arming is explicit
               kill_switch_path=Path("STOP"),         # `touch STOP` halts everything
               max_actions_per_run=2,
               notify=lambda msg: print(f"   [report] {msg}"))
ks = "PRESENT" if env.kill_switch_path.exists() else "absent"
print(f"\n3. the envelope — armed={env.armed}, kill-switch {ks}, breaker {env.max_actions_per_run}/run")

print("\n4. executing (double-closed: contracted AND registered; every outcome reported):")
outcome = actions.execute(list(granted.items()), env,
                          ledger=EvidenceLedger(Path("ledger")),
                          period=dt.date.today())

print(f"\n5. outcome — {outcome.summary()}")
print(f"   ledger: ledger/{dt.date.today().isoformat()}.jsonl (append-only; every run adds lines)")
```

Run it and the output narrates the authorization chain — note the gate silently denying
`cache` (propose tier) and `payments-db` (not signed off):

```
1. the book — who may do what, declared by a human:
   queue-worker: status=active scope=checkout-stack tier=act allows=['restart_worker']
   cache: status=active scope=checkout-stack tier=propose allows=['clear_cache']
   payments-db: status=proposed scope=checkout-stack tier=act allows=['failover_replica']

2. the gate — scope='checkout-stack' at tier 'act' grants:
   {'queue-worker': ('restart_worker',)}

3. the envelope — armed=True, kill-switch absent, breaker 2/run

4. executing (double-closed: contracted AND registered; every outcome reported):
   [report] executed-ok: restart_worker on queue-worker (worker restarted)

5. outcome — 1 executed | queue-worker:restart_worker=executed-ok
   ledger: ledger/2026-08-01.jsonl (append-only; every run adds lines)
```

Then `touch STOP` and run again to watch the kill-switch refuse everything — and land in
the ledger anyway (the halt is on the record too; silence is impossible).

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
