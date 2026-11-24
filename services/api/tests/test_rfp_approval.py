from datetime import datetime, timezone

from langgraph.checkpoint.memory import MemorySaver

from services.api.models import ApprovalStatus
from services.api.services import rfp_approval as approval


def test_department_branches_have_independent_interrupts(monkeypatch):
    monkeypatch.setattr(approval, "_get_sections", lambda _ticket: [
        type("Section", (), {
            "department_id": "seleccion", "draft_content": "draft A",
            "approval_status": ApprovalStatus.PENDING,
        })(),
        type("Section", (), {
            "department_id": "capacitacion", "draft_content": "draft B",
            "approval_status": ApprovalStatus.PENDING,
        })(),
    ])
    monkeypatch.setattr(approval, "_update_ticket_status", lambda *_args: None)
    monkeypatch.setattr(approval, "_update_section_approval", lambda *_args, **_kwargs: None)

    saver = MemorySaver()
    result = approval.run_approval_pipeline("ticket-1", checkpointer=saver)
    assert result["status"] == "waiting_approval"
    assert result["thread_ids"]["seleccion"] != result["thread_ids"]["capacitacion"]

    graph = approval.build_department_approval_graph(checkpointer=saver)
    state_a = graph.get_state({"configurable": {"thread_id": approval._department_thread_id("ticket-1", "seleccion")}})
    state_b = graph.get_state({"configurable": {"thread_id": approval._department_thread_id("ticket-1", "capacitacion")}})
    assert state_a.next == ("department_approval",)
    assert state_b.next == ("department_approval",)

    resumed_b = approval.resume_approval_pipeline(
        "ticket-1", "capacitacion", "approve", checkpointer=saver
    )
    assert resumed_b["status"] == "waiting_approval"
    # Resuming B must leave A's checkpoint paused and untouched.
    state_a_after = graph.get_state({"configurable": {"thread_id": approval._department_thread_id("ticket-1", "seleccion")}})
    assert state_a_after.next == ("department_approval",)


def test_e2e_independent_approvals_finalize_only_after_all_departments(monkeypatch):
    """Exercise start, independent HITL resumes, persisted states, and final assembly."""
    sections = [
        type("Section", (), {
            "department_id": dept,
            "department_name": name,
            "draft_content": f"Borrador {name}",
            "approval_status": ApprovalStatus.PENDING,
            "approved_by": None,
            "approved_at": None,
        })()
        for dept, name in (("seleccion", "Selección"), ("capacitacion", "Capacitación"))
    ]
    ticket_statuses = []
    documents = []

    monkeypatch.setattr(approval, "_get_sections", lambda _ticket: sections)

    def update_section(_ticket, department_id, status, approved_by=None):
        section = next(item for item in sections if item.department_id == department_id)
        section.approval_status = status
        section.approved_by = approved_by

    monkeypatch.setattr(approval, "_update_section_approval", update_section)
    monkeypatch.setattr(approval, "_update_ticket_status", lambda _ticket, status: ticket_statuses.append(status))
    monkeypatch.setattr(approval, "_save_final_document", lambda _ticket, content: documents.append(content))

    saver = MemorySaver()
    started = approval.run_approval_pipeline("e2e-ticket", checkpointer=saver)
    assert started["status"] == "waiting_approval"
    assert ticket_statuses[-1] == approval.TicketStatus.ESPERANDO_APROBACION

    # Approve the second department first. The first department must remain paused.
    second = approval.resume_approval_pipeline(
        "e2e-ticket", "capacitacion", "approve", checkpointer=saver
    )
    assert second["status"] == "waiting_approval"
    assert sections[0].approval_status == ApprovalStatus.PENDING
    assert sections[1].approval_status == ApprovalStatus.APPROVED
    assert documents == []
    graph = approval.build_department_approval_graph(checkpointer=saver)
    first_config = {"configurable": {"thread_id": approval._department_thread_id("e2e-ticket", "seleccion")}}
    assert graph.get_state(first_config).next == ("department_approval",)

    completed = approval.resume_approval_pipeline(
        "e2e-ticket", "seleccion", "approve", checkpointer=saver
    )
    assert completed["status"] == "completed"
    assert all(section.approval_status == ApprovalStatus.APPROVED for section in sections)
    assert len(documents) == 1
    assert "Borrador Selección" in documents[0]
    assert "Borrador Capacitación" in documents[0]
    assert ticket_statuses[-1] == approval.TicketStatus.TERMINADO


def test_persist_trace_inserts_all_events_without_count_based_skips(monkeypatch):
    class FakeSession:
        added = []

        def __init__(self, _engine):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def add(self, event):
            self.added.append(event)

        def commit(self):
            pass

    monkeypatch.setattr(approval, "Session", FakeSession)
    monkeypatch.setattr(approval, "engine", object())
    events = [
        {"agent": "Arbitraje", "timestamp": datetime.now(timezone.utc).isoformat(), "input": {}, "output": {}},
        {"agent": "Approval:soporte", "department_id": "soporte", "timestamp": datetime.now(timezone.utc).isoformat(), "input": {}, "output": {"action": "approved"}},
    ]

    approval._persist_trace("ticket-trace", events)

    assert len(FakeSession.added) == 2
    assert [event.agent for event in FakeSession.added] == ["Arbitraje", "Approval:soporte"]
    assert FakeSession.added[1].department_id == "soporte"


def test_approval_iteration_limit_is_three():
    assert approval.MAX_APPROVAL_ITERATIONS == 3
    assert approval._route_department_repeat({
        "department_id": "seleccion",
        "approvals": {"seleccion": {"status": "request_changes", "iteration": 3}},
    }) == "done"


def test_third_request_for_changes_escalates_to_human_review(monkeypatch):
    monkeypatch.setattr(approval, "_get_sections", lambda _ticket: [
        type("Section", (), {"department_id": "seleccion", "draft_content": "draft"})()
    ])
    updates = []
    monkeypatch.setattr(
        approval, "_update_section_approval",
        lambda *args, **kwargs: updates.append((args, kwargs)),
    )
    monkeypatch.setattr(approval, "lg_interrupt", lambda _payload: {
        "action": "request_changes", "feedback": "aclarar alcance",
    })
    state = approval.ApprovalState({
        "ticket_id": "ticket-limit",
        "approvals": {"seleccion": {"iteration": approval.MAX_APPROVAL_ITERATIONS - 1}},
        "trace": [],
    })

    result = approval._department_approval_node(state, "seleccion")

    assert result["approvals"]["seleccion"]["iteration"] == approval.MAX_APPROVAL_ITERATIONS
    assert result["approvals"]["seleccion"]["status"] == "needs_human_review"
    assert result["approvals"]["seleccion"]["max_iterations_reached"] is True
    assert updates[-1][0][2] == ApprovalStatus.PENDING
    assert result["trace"][-1]["output"]["action"] == "max_iterations_reached"


def test_legacy_pending_decision_recreates_missing_checkpoint(monkeypatch):
    """A missing legacy branch is recreated and then resumed, not rejected."""
    sections = [type("Section", (), {
        "department_id": "seleccion", "draft_content": "draft", "approval_status": ApprovalStatus.PENDING,
    })()]
    monkeypatch.setattr(approval, "_get_sections", lambda _ticket: sections)
    monkeypatch.setattr(approval, "_update_section_approval", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(approval, "_finalize_if_all_sections_approved", lambda _ticket, result: {
        "status": "completed", "ticket_id": _ticket, "trace": result.get("trace", []),
    })
    saver = MemorySaver()

    result = approval.resume_approval_pipeline(
        "legacy-ticket", "seleccion", "approve", checkpointer=saver,
    )

    assert result["status"] == "completed"
    config = {"configurable": {"thread_id": approval._department_thread_id("legacy-ticket", "seleccion")}}
    state = approval.build_department_approval_graph(checkpointer=saver).get_state(config)
    assert state.values["approvals"]["seleccion"]["status"] == "approved"


def test_each_conflict_trigger_is_detected_and_resolved_deterministically():
    ttc_state = approval.ApprovalState({
        "ticket_id": "ticket-arbitration",
        "departments": ["seleccion", "capacitacion"],
        "client_hq": "Valencia",
        "currency": "EUR",
        "approvals": {
            "seleccion": {"time_to_close": "20 días hábiles", "currency": "EUR"},
            "capacitacion": {"training_window": "10 días", "currency": "EUR"},
        },
        "trace": [],
    })
    ttc_conflicts = approval._detect_conflicts(ttc_state)
    assert [c["trigger_id"] for c in ttc_conflicts] == ["ttc-vs-training-window"]
    ttc_result = approval.arbitrate_node(ttc_state)
    assert ttc_result["approvals"]["seleccion"]["arbitration"] == "request_changes"
    assert ttc_result["conflicts"][0]["resolver"] == approval.ARBITRO

    support_state = approval.ApprovalState({
        "ticket_id": "ticket-arbitration",
        "departments": ["soporte"],
        "client_hq": "Valencia",
        "currency": "EUR",
        "approvals": {"soporte": {"draft_content": "Atención bajo demanda", "currency": "EUR"}},
        "trace": [],
    })
    support_conflicts = approval._detect_conflicts(support_state)
    assert [c["trigger_id"] for c in support_conflicts] == ["support-sla-missing"]
    support_result = approval.arbitrate_node(support_state)
    assert support_result["approvals"]["soporte"]["arbitration"] == "request_changes"

    currency_state = approval.ApprovalState({
        "ticket_id": "ticket-arbitration",
        "departments": ["seleccion"],
        "client_hq": "Miami",
        "currency": "EUR",
        "approvals": {"seleccion": {"currency": "EUR"}},
        "trace": [],
    })
    currency_conflicts = approval._detect_conflicts(currency_state)
    assert [c["trigger_id"] for c in currency_conflicts] == ["currency-mismatch"]
    currency_result = approval.arbitrate_node(currency_state)
    assert currency_result["currency"] == "USD"
    assert currency_result["approvals"]["seleccion"]["currency"] == "USD"


def test_arbitration_uses_fixed_deterministic_rule(monkeypatch):
    monkeypatch.setattr(approval, "_detect_conflicts", lambda _state: [{
        "trigger_id": "ttc-vs-training-window", "resolver": approval.ARBITRO,
    }])
    state = approval.ApprovalState({
        "ticket_id": "ticket-1", "departments": ["seleccion", "capacitacion"],
        "approvals": {"seleccion": {}, "capacitacion": {}}, "trace": [],
    })
    result = approval.arbitrate_node(state)
    assert result["approvals"]["seleccion"]["arbitration"] == "request_changes"
    assert result["conflicts"][0]["resolver"] == approval.ARBITRO
    assert result["trace"][0]["agent"] == "Arbitraje"
    datetime.fromisoformat(result["trace"][0]["timestamp"])


def test_assembly_refuses_partial_approval(monkeypatch):
    sections = [
        type("Section", (), {
            "department_id": "seleccion", "department_name": "Selección",
            "draft_content": "A", "approval_status": ApprovalStatus.APPROVED,
            "approved_by": "Javier", "approved_at": None,
        })(),
        type("Section", (), {
            "department_id": "capacitacion", "department_name": "Formación",
            "draft_content": "B", "approval_status": ApprovalStatus.PENDING,
            "approved_by": None, "approved_at": None,
        })(),
    ]
    monkeypatch.setattr(approval, "_get_sections", lambda _ticket: sections)
    saved = []
    monkeypatch.setattr(approval, "_save_final_document", lambda *_args: saved.append(True))
    monkeypatch.setattr(approval, "_update_ticket_status", lambda *_args: saved.append(True))
    result = approval.assemble_document_node(approval.ApprovalState({
        "ticket_id": "ticket-1", "trace": [],
    }))
    assert saved == []
    assert result["trace"][0]["output"]["pending"] == ["capacitacion"]
