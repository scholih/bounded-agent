"""Chapter 1 — contracts & gates: the declared book of who may do what.

The invariants under test:
- a gate grants only entries that are active, in scope, and at sufficient tier;
- tiers are ORDERED (act ⊇ propose ⊇ observe) — an 'act' contract clears a 'propose' gate;
- an unreadable or malformed book RAISES — absence of authorization is never a default;
- the lifecycle vocabulary belongs to the CALLER (active_status is configurable), because a
  library that hardcodes your workflow's status words will be wrong in someone's workflow.
"""
from __future__ import annotations

import pytest

from bounded_agent.contracts import Contract, ContractBook, Gate


def _c(**kw) -> Contract:
    base = dict(name="queue-worker", status="active", scope="checkout-stack",
                tier="act", allows=("restart_worker",))
    base.update(kw)
    return Contract(**base)


def test_gate_grants_active_in_scope_at_tier():
    assert Gate(required_scope="checkout-stack").permits(_c())


def test_gate_denies_wrong_scope():
    assert not Gate(required_scope="checkout-stack").permits(_c(scope="billing-stack"))


def test_gate_denies_inactive():
    assert not Gate(required_scope="checkout-stack").permits(_c(status="proposed"))


def test_gate_active_status_vocabulary_is_configurable():
    gate = Gate(required_scope="checkout-stack", active_status="LIVE")
    assert gate.permits(_c(status="LIVE"))
    assert not gate.permits(_c(status="active"))     # caller's vocabulary, strictly


def test_gate_none_scope_matches_any():
    assert Gate(required_scope=None).permits(_c(scope="anything"))


def test_tiers_are_ordered_act_clears_propose_gate():
    gate = Gate(required_scope="checkout-stack", required_tier="propose")
    assert gate.permits(_c(tier="act"))


def test_propose_contract_fails_an_act_gate():
    gate = Gate(required_scope="checkout-stack", required_tier="act")
    assert not gate.permits(_c(tier="propose"))


def test_observe_tier_never_grants_actions():
    gate = Gate(required_scope="checkout-stack", required_tier="propose")
    assert not gate.permits(_c(tier="observe"))


def test_contract_is_frozen():
    with pytest.raises(Exception):
        _c().name = "mutated"  # type: ignore[misc]


def test_book_load_raises_on_missing_file(tmp_path):
    with pytest.raises((FileNotFoundError, OSError)):
        ContractBook.load(tmp_path / "absent.yaml")


def test_book_load_raises_on_malformed(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("something_else: []\n")
    with pytest.raises(ValueError):
        ContractBook.load(p)


def test_book_granted_filters_to_gate(tmp_path):
    p = tmp_path / "book.yaml"
    p.write_text(
        "contracts:\n"
        "  - {name: a, status: active, scope: checkout-stack, tier: act, allows: [restart_a]}\n"
        "  - {name: b, status: active, scope: checkout-stack, tier: observe, allows: [restart_b]}\n"
        "  - {name: c, status: proposed, scope: checkout-stack, tier: act, allows: [restart_c]}\n"
        "  - {name: d, status: active, scope: billing-stack, tier: act, allows: [restart_d]}\n"
    )
    book = ContractBook.load(p)
    granted = book.granted(Gate(required_scope="checkout-stack", required_tier="act"))
    assert granted == {"a": ("restart_a",)}


def test_book_ignores_extra_yaml_fields(tmp_path):
    p = tmp_path / "book.yaml"
    p.write_text(
        "contracts:\n"
        "  - name: a\n    status: active\n    scope: s\n    tier: act\n"
        "    allows: [x]\n    owner: alice\n    sla_minutes: 30\n"
    )
    assert ContractBook.load(p).granted(Gate(required_scope="s")) == {"a": ("x",)}
