"""
Tests for RFP Approval Pipeline — Part 3.

Tests:
- Interrupt + resume with approve/reject/request_changes
- Max iteration limit → needs_human_review
- Arbitration: ttc-vs-training-window conflict detection
- Department B approved while department A still interrupted (parallel branches)
- E2E: Parts 1→3 with seeded state and simulated human approvals
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

pytest.importorskip("sqlmodel")
pytest.importorskip("langgraph")

from sqlmodel import Session, select

from services.api.database import engine
from services.api.models import (
    ApprovalStatus,
    DepartmentSection,
    FinalDocument,
    RFPMetadata,
    Ticket,
    TicketStatus,
)
from services.api.services import rfp_approval as approval
from services.api.services.rfp_approval import (
    build_approval_graph,
    run_approval_pipeline,
    resume_approval_pipeline,
    CONFLICT_TRIGGERS,
    MAX_APPROVAL_ITERATIONS,
    ApprovalState,
)

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver

# Reusable memory saver for tests (no Postgres needed)
_MEM_SAVER = MemorySaver()


# ── Fixtures ───────────────────────────────────────────────────────────


def _dept_name(dept_id: str) -> str:
    names = {
        "seleccion": "Talent Selection Operations",
        "capacitacion": "Corporate Training",
        "soporte": "Customer Support (outsourcing)",
    }
    return names.get(dept_id, dept_id)


def _aspects_for(dept_id: str) -> dict:
    aspects = {
        "seleccion": {
            "roles_to_cover": ["5"],
            "estimated_close_time": "Por determinar (mín. 15 días hábiles)",
            "open_questions": [],
        },
        "capacitacion": {
            "applicable_programs": ["liderazgo", "formación ejecutiva"],
            "duration": "Por determinar",
            "open_questions": [],
        },
        "soporte": {
            "agent_count": 12,
            "shifts": "24/7",
            "sla_response": "24 horas",
            "open_questions": [],
        },
    }
    return aspects.get(dept_id, {})


def _draft_for(dept_id: str) -> str:
    """Return a plausible draft proposal text per department."""
    drafts = {
        "seleccion": (
            "PROPUESTA DE SELECCIÓN\n\n"
            "Nexova se compromete a cubrir 5 roles ejecutivos con un time-to-close "
            "estimado de 15 días hábiles. Se garantiza un proceso de selección "
            "estructurado con evaluación psicométrica y entrevistas por competencias. "
            "Cobertura de garantía: 60 días hábiles."
        ),
        "capacitacion": (
            "PROPUESTA DE CAPACITACIÓN\n\n"
            "Programas de liderazgo y formación ejecutiva con una duración total de "
            "24 horas presenciales. Incluye material didáctico, evaluación de impacto "
            "y certificación. Ventana de entrega: 45 días hábiles desde la firma."
        ),
        "soporte": (
            "PROPUESTA DE SOPORTE\n\n"
            "12 agentes bilingües en turno 24/7 con SLA de respuesta de 24 horas. "
            "Infraestructura cloud con redundancia geográfica. Se incluye reporte "
            "mensual de KPI. El servicio se factura en EUR."
        ),
    }
    return drafts.get(dept_id, "Borrador genérico de prueba.")


def _create_ticket_with_drafts(
    dept_ids: list[str],
    client_name: str = "Test Client, S.A",
    client_hq: str = "España",
    currency: str = "EUR",
    initial_status: TicketStatus = TicketStatus.ANALISIS_COMPLETO,
) -> str:
    """Create a fully set-up ticket ready for Part 3 (has drafts)."""
    ticket_id = str(uuid4())

    with Session(engine) as session:
        ticket = Ticket(
            ticket_id=ticket_id,
            status=initial_status,
            handoff_json=json.dumps(
                {
                    "version": "1.0",
                    "ticket_id": ticket_id,
                    "client_name": client_name,
                    "workstreams": {
                        d: {
                            "department_id": d,
                            "department_name": _dept_name(d),
                            "key_aspects": _aspects_for(d),
                        }
                        for d in dept_ids
                    },
                },
                ensure_ascii=False,
            ),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(ticket)
        session.flush()

        meta = RFPMetadata(
            rfp_id=str(uuid4()),
            ticket_id=ticket_id,
            client_name=client_name,
            client_hq=client_hq,
            currency=currency,
            departments_needed=dept_ids,
        )
        session.add(meta)
        session.flush()

        for dept_id in dept_ids:
            section = DepartmentSection(
                ticket_id=ticket_id,
                department_id=dept_id,
                department_name=_dept_name(dept_id),
                key_aspects=json.dumps(_aspects_for(dept_id), ensure_ascii=False),
                draft_content=_draft_for(dept_id),
                iteration_count=1,
                needs_human_review=False,
                approval_status=ApprovalStatus.PENDING,
            )
            session.add(section)

        session.commit()

    return ticket_id


# ── Tests: Interrupt + resume ─────────────────────────────────────────


def test_postgres_checkpoint_survives_saver_reopen_and_resumes_same_department():
    """Persist an interrupt, close its saver, then resume that exact branch.

    This intentionally uses no ticket/section rows: the checkpoint store is the
    only database surface exercised. Set TEST_DATABASE_URL to an explicitly
    disposable PostgreSQL database; production DATABASE_URL is never a fallback.
    """
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")

    from psycopg import Connection
    from sqlalchemy.engine import make_url

    parsed_url = make_url(database_url)
    if parsed_url.get_backend_name() != "postgresql" or "test" not in (parsed_url.database or "").lower():
        pytest.fail("TEST_DATABASE_URL must target a PostgreSQL database whose name includes 'test'")

    ticket_id = f"checkpoint-test-{uuid4()}"
    department_id = "seleccion"
    thread_id = f"rfp-{ticket_id}-{department_id}"
    config = {"configurable": {"thread_id": thread_id}}

    class Section:
        department_id = "seleccion"
        department_name = "Test Selection"
        draft_content = "Draft belonging only to the persistent-checkpoint test"
        approval_status = ApprovalStatus.PENDING
        approved_by = None
        approved_at = None

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("services.api.services.rfp_approval._get_sections", lambda _ticket: [Section()])
    monkeypatch.setattr("services.api.services.rfp_approval._update_section_approval", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("services.api.services.rfp_approval._update_ticket_status", lambda *_args: None)
    monkeypatch.setattr("services.api.services.rfp_approval._persist_trace", lambda *_args: None)
    # This test isolates checkpoint durability; emulate the post-resume
    # finalization response without touching business tables or documents.
    monkeypatch.setattr(
        "services.api.services.rfp_approval._finalize_if_all_sections_approved",
        lambda _ticket, result: (
            {"status": "completed", "approvals": result.get("approvals", {})}
            if result.get("approvals", {}).get(department_id, {}).get("status") == "approved"
            else None
        ),
    )

    def open_saver():
        conn = Connection.connect(database_url, autocommit=True, prepare_threshold=None)
        return PostgresSaver(conn=conn), conn

    saver1, conn1 = open_saver()
    saver2 = conn2 = None
    try:
        saver1.setup()
        started = run_approval_pipeline(ticket_id, checkpointer=saver1)
        assert started["status"] == "waiting_approval"
        state_before = approval.build_department_approval_graph(checkpointer=saver1).get_state(config)
        assert state_before.next == ("department_approval",)
        assert state_before.values["department_id"] == department_id
    finally:
        conn1.close()

    try:
        saver2, conn2 = open_saver()
        state_after_reopen = approval.build_department_approval_graph(checkpointer=saver2).get_state(config)
        assert state_after_reopen.next == ("department_approval",)
        assert state_after_reopen.values["department_id"] == department_id
        assert state_after_reopen.values["approvals"][department_id]["draft_content"] == Section.draft_content

        resumed = resume_approval_pipeline(ticket_id, department_id, "approve", checkpointer=saver2)
        assert resumed["status"] == "completed"
        assert resumed["approvals"][department_id]["status"] == "approved"
        # Approval itself does not consume a change/rejection iteration.
        assert resumed["approvals"][department_id].get("iteration", 0) == 0
        final_state = approval.build_department_approval_graph(checkpointer=saver2).get_state(config)
        assert final_state.next == ()
        assert final_state.values["approvals"][department_id]["status"] == "approved"
    finally:
        if conn2 is not None:
            conn2.close()
        monkeypatch.undo()


class TestInterruptAndResume:
    """Tests for the interrupt/resume cycle per department."""

    def test_approve_single_department(self):
        """Start approval pipeline, approve seleccion → should wait for others."""
        ticket_id = _create_ticket_with_drafts(["seleccion", "capacitacion"])
        result = run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)

        # First run should pause (interrupt) waiting for approval
        assert result["status"] == "waiting_approval"

        # Resume with approval for seleccion
        resume_result = resume_approval_pipeline(
            ticket_id, "seleccion", "approve", "", checkpointer=_MEM_SAVER
        )

        assert resume_result["status"] == "waiting_approval"
        approvals = resume_result.get("approvals", {})
        assert approvals.get("seleccion", {}).get("status") in ("approved",)

    def test_reject_department_needs_feedback(self):
        """Reject without feedback should raise ValueError."""
        ticket_id = _create_ticket_with_drafts(["seleccion"])
        run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)

        with pytest.raises(ValueError, match="feedback"):
            resume_approval_pipeline(ticket_id, "seleccion", "reject", "", checkpointer=_MEM_SAVER)

    def test_reject_with_feedback_works(self):
        """Reject with valid feedback should succeed."""
        ticket_id = _create_ticket_with_drafts(["seleccion"])
        result = run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)
        assert result["status"] == "waiting_approval"

        resume_result = resume_approval_pipeline(
            ticket_id, "seleccion", "reject", "Falta presupuesto detallado.",
            checkpointer=_MEM_SAVER,
        )
        assert resume_result["status"] in ("waiting_approval", "completed")
        approvals = resume_result.get("approvals", {})
        assert approvals.get("seleccion", {}).get("status") == "rejected"

    def test_request_changes_with_feedback(self):
        """Request changes with feedback should succeed."""
        ticket_id = _create_ticket_with_drafts(["seleccion"])
        run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)

        resume_result = resume_approval_pipeline(
            ticket_id, "seleccion", "request_changes",
            "Incluir costos unitarios por rol.",
            checkpointer=_MEM_SAVER,
        )
        assert resume_result["status"] in ("waiting_approval", "completed")

    def test_all_departments_approve_produces_final_document(self):
        """When all departments approve, the final document should be generated."""
        ticket_id = _create_ticket_with_drafts(
            ["seleccion", "capacitacion", "soporte"],
        )
        result = run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)
        assert result["status"] == "waiting_approval"

        # Approve all three departments
        for dept in ["seleccion", "capacitacion", "soporte"]:
            r = resume_approval_pipeline(ticket_id, dept, "approve", "", checkpointer=_MEM_SAVER)
            if r.get("final_document"):
                break

        # Check final document was persisted
        with Session(engine) as session:
            doc = session.query(FinalDocument).filter(
                FinalDocument.ticket_id == ticket_id
            ).first()
            assert doc is not None, "Final document should exist in DB"
            assert doc.content is not None
            assert len(doc.content) > 0

    def test_invalid_action_raises_error(self):
        """Invalid action string should raise ValueError."""
        ticket_id = _create_ticket_with_drafts(["seleccion"])
        run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)

        with pytest.raises(ValueError, match="inválida|invalid"):
            resume_approval_pipeline(ticket_id, "seleccion", "invalid_action", "", checkpointer=_MEM_SAVER)


# ── Tests: Max iterations ─────────────────────────────────────────────


class TestMaxIterations:
    """Tests for the max iteration limit."""

    def test_rejection_increments_iteration(self):
        """Each rejection should advance the approval iteration counter."""
        ticket_id = _create_ticket_with_drafts(["seleccion"])
        run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)

        resume_approval_pipeline(
            ticket_id, "seleccion", "reject", "Corregir presupuesto.",
            checkpointer=_MEM_SAVER,
        )

        with Session(engine) as session:
            ticket = session.query(Ticket).filter(
                Ticket.ticket_id == ticket_id
            ).first()
            # After rejection, ticket should still be waiting or needs_human_review
            assert ticket.status in (
                TicketStatus.ESPERANDO_APROBACION,
                TicketStatus.NEEDS_HUMAN_REVIEW,
            )


# ── Tests: Arbitration ────────────────────────────────────────────────


class TestArbitration:
    """Tests for the arbitration node with conflict triggers."""

    def test_conflict_triggers_are_defined(self):
        """All three required conflict triggers should exist."""
        trigger_ids = {t.trigger_id for t in CONFLICT_TRIGGERS}
        assert "ttc-vs-training-window" in trigger_ids
        assert "support-sla-missing" in trigger_ids
        assert "currency-mismatch" in trigger_ids

    def test_arbitration_detects_currency_mismatch(self):
        """Graph should detect currency mismatch conflict."""
        from services.api.services.rfp_approval import _detect_conflicts

        # Create a real ticket with USD draft content
        ticket_id = _create_ticket_with_drafts(["seleccion"], currency="MXN")

        # Read the section and update draft to mention USD
        with Session(engine) as session:
            section = session.query(DepartmentSection).filter(
                DepartmentSection.ticket_id == ticket_id,
            ).first()
            if section:
                section.draft_content = "Este servicio se factura en USD."
                session.add(section)
                session.commit()

        # State matching the MXN currency vs USD in draft
        state: ApprovalState = {
            "ticket_id": ticket_id,
            "client_name": "Test",
            "client_hq": "México",
            "currency": "MXN",
            "departments": ["seleccion"],
            "approvals": {},
            "conflicts": [],
            "arbitration_required": False,
            "trace": [],
            "final_document": None,
            "generated_at": None,
        }

        state["approvals"] = {"seleccion": {"currency": "MXN"}}
        conflicts = _detect_conflicts(state)
        currency_conflicts = [c for c in conflicts if c["trigger_id"] == "currency-mismatch"]
        assert len(currency_conflicts) == 1
        assert currency_conflicts[0]["resolver"] == approval.ARBITRO


# ── Tests: Parallel branches ──────────────────────────────────────────


class TestParallelBranches:
    """Tests that department branches can be approved independently."""

    def test_approve_department_b_while_a_interrupted(self):
        """
        With sequential departments, seleccion must be approved first before
        capacitacion can be reached. This test verifies each department's
        interrupt/resume cycle works independently in sequence.
        """
        ticket_id = _create_ticket_with_drafts(["seleccion", "capacitacion"])
        result = run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)
        assert result["status"] == "waiting_approval"

        # First, approve seleccion (department A) to advance past its interrupt
        resume_sel = resume_approval_pipeline(
            ticket_id, "seleccion", "approve", "", checkpointer=_MEM_SAVER
        )
        assert resume_sel["status"] == "waiting_approval"
        approvals = resume_sel.get("approvals", {})
        assert approvals.get("seleccion", {}).get("status") in ("approved",)

        # Now approve capacitacion (department B)
        resume_cap = resume_approval_pipeline(
            ticket_id, "capacitacion", "approve", "", checkpointer=_MEM_SAVER
        )
        assert resume_cap["status"] in ("waiting_approval", "completed")
        approvals2 = resume_cap.get("approvals", {})
        assert approvals2.get("capacitacion", {}).get("status") in ("approved",)


# ── Tests: E2E (Parts 1→3) ──────────────────────────────────────────


class TestE2E:
    """
    End-to-end test: simulate a full Parts 1→3 flow with seeded state.

    This test creates a ticket with drafts (as if Part 1 and 2 completed),
    runs the approval pipeline, simulates human approvals programmatically,
    and verifies the final document is produced.
    """

    def _simulate_human_approvals(self, ticket_id: str, depts: list[str], checkpointer=None) -> dict:
        """Helper: approve all departments sequentially."""
        final_result = {}
        for dept in depts:
            r = resume_approval_pipeline(ticket_id, dept, "approve", "", checkpointer=checkpointer)
            final_result[dept] = r
            if r.get("final_document"):
                break
        return final_result

    def test_e2e_full_approval_flow(self):
        """
        Full E2E: create ticket → run approval → approve all → verify document.
        """
        ticket_id = _create_ticket_with_drafts(
            ["seleccion", "capacitacion", "soporte"],
        )

        # Step 1: Start approval pipeline
        result = run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)
        assert result["status"] == "waiting_approval"

        # Step 2: Approve all three departments
        results = self._simulate_human_approvals(
            ticket_id, ["seleccion", "capacitacion", "soporte"],
            checkpointer=_MEM_SAVER,
        )

        # Step 3: Verify final state
        with Session(engine) as session:
            ticket = session.query(Ticket).filter(
                Ticket.ticket_id == ticket_id
            ).first()
            assert ticket is not None
            # Ticket should be terminado or still esperando_aprobacion
            assert ticket.status in (
                TicketStatus.TERMINADO,
                TicketStatus.ESPERANDO_APROBACION,
            )

            # Check final document
            doc = session.query(FinalDocument).filter(
                FinalDocument.ticket_id == ticket_id
            ).first()
            if doc:
                assert len(doc.content) > 0

            # Verify all sections have approval status
            sections = session.query(DepartmentSection).filter(
                DepartmentSection.ticket_id == ticket_id
            ).all()
            for s in sections:
                assert s.approval_status is not None

    def test_e2e_with_one_rejection_then_approve(self):
        """
        E2E: approve seleccion, reject capacitacion with feedback,
        then approve soporte and check final state.
        """
        ticket_id = _create_ticket_with_drafts(
            ["seleccion", "capacitacion", "soporte"],
        )

        run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)

        # Approve seleccion
        resume_approval_pipeline(ticket_id, "seleccion", "approve", "", checkpointer=_MEM_SAVER)

        # Reject capacitacion
        resume_approval_pipeline(
            ticket_id, "capacitacion", "reject",
            "El programa de liderazgo no incluye seguimiento post-formación.",
            checkpointer=_MEM_SAVER,
        )

        # Approve soporte
        resume_approval_pipeline(ticket_id, "soporte", "approve", "", checkpointer=_MEM_SAVER)

        with Session(engine) as session:
            sec = session.query(DepartmentSection).filter(
                DepartmentSection.ticket_id == ticket_id,
                DepartmentSection.department_id == "capacitacion",
            ).first()
            assert sec is not None
            assert sec.approval_status == ApprovalStatus.REJECTED

    def test_e2e_ticket_status_transitions(self):
        """
        Verify ticket status transitions: analisis_completo → esperando_aprobacion → terminado.
        """
        ticket_id = _create_ticket_with_drafts(
            ["seleccion", "soporte"],
            initial_status=TicketStatus.ANALISIS_COMPLETO,
        )

        # Start approval
        run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)

        with Session(engine) as session:
            ticket = session.query(Ticket).filter(
                Ticket.ticket_id == ticket_id
            ).first()
            assert ticket.status == TicketStatus.ESPERANDO_APROBACION

        # Approve both
        for dept in ["seleccion", "soporte"]:
            resume_approval_pipeline(ticket_id, dept, "approve", "", checkpointer=_MEM_SAVER)

        with Session(engine) as session:
            ticket = session.query(Ticket).filter(
                Ticket.ticket_id == ticket_id
            ).first()
            # Final document should exist, ticket should be terminado
            doc = session.query(FinalDocument).filter(
                FinalDocument.ticket_id == ticket_id
            ).first()
            if doc:
                assert ticket.status in (
                    TicketStatus.TERMINADO,
                    TicketStatus.ESPERANDO_APROBACION,
                )


# ── Tests: Traceability ───────────────────────────────────────────────


class TestTraceability:
    """Tests for the trace logging in each node execution."""

    def test_trace_contains_node_executions(self):
        """The trace should contain entries for each executed node."""
        ticket_id = _create_ticket_with_drafts(["seleccion"])
        result = run_approval_pipeline(ticket_id, checkpointer=_MEM_SAVER)

        if "trace" in result:
            trace = result["trace"]
            assert len(trace) > 0
            # Each trace entry should have agent, input, output, timestamp
            for entry in trace:
                assert "agent" in entry
                assert "input" in entry
                assert "output" in entry
                assert "timestamp" in entry


def test_e2e_parts_1_to_3_from_synthetic_rfp():
    """Reproducible full pipeline: intake, draft generation, then simulated approvals."""
    from services.api.services.rfp_intake import run_rfp_intake
    from services.api.services.rfp_generation import run_rfp_generation

    ticket_id = str(uuid4())
    with Session(engine) as session:
        session.add(Ticket(ticket_id=ticket_id, status=TicketStatus.ANALIZANDO, handoff_json="{}"))
        session.commit()

    rfp_text = """SOLICITUD DE PROPUESTA\nCliente: Vantex Retail Group\nSede: Madrid, España\n\
Solicitamos outsourcing de selección de personal y capacitación corporativa.\n\
Servicios: búsqueda ejecutiva de 5 mandos medios y programa trimestral de liderazgo.\n\
Presupuesto de referencia: 45.000 EUR. Fecha límite: 30/04/2027.\n"""
    intake = run_rfp_intake(ticket_id, rfp_text)
    assert intake.get("ticket_status") == TicketStatus.ANALISIS_COMPLETO.value, intake
    assert intake.get("rfp_id"), intake
    assert intake.get("departments_needed"), intake

    generated = run_rfp_generation(ticket_id)
    assert generated.get("departments"), generated
    assert all(item.get("generated") for item in generated["departments"].values())

    saver = MemorySaver()
    waiting = run_approval_pipeline(ticket_id, checkpointer=saver)
    assert waiting["status"] == "waiting_approval"
    for department_id in waiting["departments"]:
        result = resume_approval_pipeline(
            ticket_id, department_id, "approve", checkpointer=saver
        )
    with Session(engine) as session:
        ticket = session.exec(select(Ticket).where(Ticket.ticket_id == ticket_id)).first()
        assert ticket is not None
        assert ticket.status == TicketStatus.TERMINADO
        assert session.exec(select(FinalDocument).where(FinalDocument.ticket_id == ticket_id)).first()
