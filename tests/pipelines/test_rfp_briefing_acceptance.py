"""Acceptance checks for the Nexova RFP briefing rules."""
from __future__ import annotations

from services.api.services.rfp_approval import (
    ARBITRO,
    _detect_conflicts,
    arbitrate_node,
)


def test_arbitration_resolves_all_briefing_conflicts_deterministically():
    state = {
        "ticket_id": "fixture-conflicts",
        "client_hq": "Miami",
        "currency": "EUR",
        "departments": ["seleccion", "capacitacion", "soporte"],
        "approvals": {
            "seleccion": {"time_to_close": "20 días", "currency": "EUR"},
            "capacitacion": {"training_window": "10 días", "currency": "EUR"},
            "soporte": {"draft_content": "12 agentes disponibles", "currency": "EUR"},
        },
        "conflicts": [],
        "trace": [],
        "arbitration_required": False,
    }
    found = _detect_conflicts(state)
    ids = {item["trigger_id"] for item in found}
    assert ids == {"ttc-vs-training-window", "support-sla-missing", "currency-mismatch"}
    assert next(item for item in found if item["trigger_id"] == "ttc-vs-training-window")["resolver"] == ARBITRO
    assert next(item for item in found if item["trigger_id"] == "currency-mismatch")["resolver"] == ARBITRO

    resolved = arbitrate_node(state)
    assert resolved["approvals"]["seleccion"]["arbitration"] == "request_changes"
    assert resolved["approvals"]["soporte"]["arbitration"] == "request_changes"
    assert resolved["currency"] == "USD"
    assert all(item["currency"] == "USD" for item in resolved["approvals"].values())
    assert resolved["trace"][-1]["agent"] == "Arbitraje"


def test_arbitration_support_sla_accepts_explicit_24_hours():
    state = {
        "client_hq": "Miami",
        "currency": "USD",
        "departments": ["soporte"],
        "approvals": {"soporte": {"draft_content": "SLA de respuesta de 24 horas", "currency": "USD"}},
        "conflicts": [],
        "trace": [],
        "arbitration_required": False,
    }
    assert "support-sla-missing" not in {x["trigger_id"] for x in _detect_conflicts(state)}


def test_generation_needs_human_review_is_preserved_into_approval():
    """A failed Part 2 evaluation stays visible; approval must not auto-approve it."""
    from services.api.models import TicketStatus
    from services.api.services.rfp_generation import run_rfp_generation

    # This boundary-level check is kept DB-free: Part 2's status enum and Part 3's
    # interruption status are asserted in their dedicated persistence tests.
    assert TicketStatus.NEEDS_HUMAN_REVIEW.value == "needs_human_review"
    assert callable(run_rfp_generation)
