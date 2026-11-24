"""
RFP Approval Pipeline — Part 3: Human-in-the-loop approval by department.

Architecture (StateGraph with PostgresCheckpointer):

    ┌──────────────────────────────────────────┐
    │            arbitrate_node                 │
    │  Detects conflicts (CONTEXT.md §7):      │
    │   - ttc-vs-training-window               │
    │   - support-sla-missing                   │
    │   - currency-mismatch                     │
    │  Resolves deterministically or flags      │
    └─────────────┬────────────────────────────┘
                  │
     ┌────────────┼────────────┐
     ▼            ▼            ▼
  seleccion    capacitacion   soporte
   interrupt    interrupt     interrupt
  (Javier)     (Elena)       (Roberto)
     │            │            │
     ▼            ▼            ▼
  wait_approval wait_approval wait_approval
     │            │            │
     ▼            ▼            ▼
  check_aprv    check_aprv   check_aprv
     │            │            │
     └────────────┼────────────┘
                  ▼
         assemble_document (cierre)
                  ▼
              done

Each department branch runs independently via fan-out/fan-in.
The checkpointer (PostgreSQL) persists state before each interrupt
so the graph is resumable.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, Send, interrupt as lg_interrupt
from sqlmodel import Session

from services.api.database import DATABASE_URL, engine
from services.api.models import (
    ApprovalStatus,
    DepartmentSection,
    FinalDocument,
    RFPApprovalTrace,
    Ticket,
    TicketStatus,
)
from services.api.services.rfp_evaluation import evaluate_compliance

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

MAX_APPROVAL_ITERATIONS = 3

DEPARTMENT_APPROVERS: dict[str, str] = {
    "seleccion": "Javier Almeida",
    "capacitacion": "Elena Vargas",
    "soporte": "Roberto Díaz",
}

ARBITRO = "Marcos Ibáñez (Director de Ventas)"


# ── Conflict triggers (CONTEXT.md §7) ────────────────────────────────


class ConflictTrigger:
    """A detectable conflict in structured state."""

    def __init__(
        self,
        trigger_id: str,
        description: str,
        resolver: str = ARBITRO,
    ):
        self.trigger_id = trigger_id
        self.description = description
        self.resolver = resolver


CONFLICT_TRIGGERS: list[ConflictTrigger] = [
    ConflictTrigger(
        "ttc-vs-training-window",
        "El time-to-close de seleccion se solapa o contradice la ventana de entrega de capacitacion",
    ),
    ConflictTrigger(
        "support-sla-missing",
        "La seccion de soporte omite el SLA obligatorio de respuesta 24h",
    ),
    ConflictTrigger(
        "currency-mismatch",
        "Las secciones discrepan en moneda o la moneda no coincide con client_hq",
    ),
]


# ── Graph State ───────────────────────────────────────────────────────


class ApprovalState(dict):
    """Mutable state dict for the approval graph.

    Persisted via PostgresCheckpointer so the graph is resumable.
    """
    ticket_id: str
    department_id: str
    client_name: str
    client_hq: str
    currency: str
    departments: list[str]  # active departments for this ticket

    # Per-department approval results
    approvals: dict[str, dict[str, Any]]  # {dept_id: {status, feedback, iteration, ...}}

    # Arbitration
    conflicts: list[dict[str, Any]]
    arbitration_required: bool

    # Traceability: every node execution logs agent, input, output, timestamp
    trace: list[dict[str, Any]]

    # Documento final
    final_document: str | None
    generated_at: str | None


# ── Checkpointer (PostgreSQL) ─────────────────────────────────────────


def _get_connection_string() -> str:
    """Return DATABASE_URL, ensuring it's a valid postgres connection."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be set for Part 3 checkpointer")
    return DATABASE_URL


_checkpointer: PostgresSaver | None = None


def get_checkpointer() -> PostgresSaver:
    """Return a PostgresSaver checkpointer connected to the database.

    Creates a direct connection and wraps it in a PostgresSaver.
    Uses a module-level cache so multiple graph invocations reuse the connection.
    """
    global _checkpointer
    if _checkpointer is None:
        from psycopg import Connection
        conn_string = _get_connection_string()
        # Supabase's pooler may use transaction pooling, where server-side prepared
        # statements are not guaranteed to exist on the next backend connection.
        # Disable psycopg auto-prepare for this long-lived checkpointer connection.
        conn = Connection.connect(
            conn_string,
            autocommit=True,
            prepare_threshold=None,
        )
        _checkpointer = PostgresSaver(conn=conn)  # type: ignore[arg-type]
        _checkpointer.setup()
    return _checkpointer


# ── Helper: db operations ─────────────────────────────────────────────


def _get_ticket(ticket_id: str) -> Ticket | None:
    with Session(engine) as session:
        return session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()


def _get_sections(ticket_id: str) -> list[DepartmentSection]:
    with Session(engine) as session:
        return (
            session.query(DepartmentSection)
            .filter(DepartmentSection.ticket_id == ticket_id)
            .all()
        )


def _update_section_approval(
    ticket_id: str,
    department_id: str,
    status: ApprovalStatus,
    approved_by: str | None = None,
) -> None:
    with Session(engine) as session:
        section = (
            session.query(DepartmentSection)
            .filter(
                DepartmentSection.ticket_id == ticket_id,
                DepartmentSection.department_id == department_id,
            )
            .first()
        )
        if section:
            section.approval_status = status
            section.approved_by = approved_by
            section.approved_at = datetime.now(timezone.utc) if status == ApprovalStatus.APPROVED else section.approved_at
            session.add(section)
            session.commit()


def _update_ticket_status(ticket_id: str, status: TicketStatus) -> None:
    with Session(engine) as session:
        ticket = (
            session.query(Ticket)
            .filter(Ticket.ticket_id == ticket_id)
            .first()
        )
        if ticket:
            ticket.status = status
            session.add(ticket)
            session.commit()


def _get_final_document(ticket_id: str) -> FinalDocument | None:
    with Session(engine) as session:
        return (
            session.query(FinalDocument)
            .filter(FinalDocument.ticket_id == ticket_id)
            .first()
        )


def _save_final_document(
    ticket_id: str,
    content: str,
    document_type: str = "propuesta_economica",
) -> FinalDocument:
    with Session(engine) as session:
        existing = (
            session.query(FinalDocument)
            .filter(FinalDocument.ticket_id == ticket_id)
            .first()
        )
        if existing:
            existing.content = content
            existing.document_type = document_type
            session.add(existing)
        else:
            doc = FinalDocument(
                ticket_id=ticket_id,
                document_type=document_type,
                content=content,
            )
            session.add(doc)
        session.commit()
        return existing or doc


# ── Node: arbitration ─────────────────────────────────────────────────


def _detect_conflicts(state: ApprovalState) -> list[dict[str, Any]]:
    """Detect conflicts from structured state (CONTEXT.md §7).

    Returns a list of conflict dicts with trigger_id, description, resolver.
    """
    conflicts: list[dict[str, Any]] = []
    approvals = state.get("approvals", {})

    sel = approvals.get("seleccion", {})
    cap = approvals.get("capacitacion", {})
    sop = approvals.get("soporte", {})

    # Trigger 1: ttc-vs-training-window
    if "seleccion" in state.get("departments", []) and "capacitacion" in state.get("departments", []):
        sel_ttc = sel.get("time_to_close", "")
        cap_window = cap.get("training_window", "")
        if sel_ttc and cap_window:
            # Extract numbers to detect overlap
            ttc_nums = re.findall(r"\d+", str(sel_ttc))
            win_nums = re.findall(r"\d+", str(cap_window))
            if ttc_nums and win_nums:
                ttc_val = int(ttc_nums[0])
                win_val = int(win_nums[0])
                if ttc_val > win_val:
                    conflicts.append({
                        "trigger_id": "ttc-vs-training-window",
                        "description": (
                            f"Time-to-close de seleccion ({ttc_val}d) excede la ventana "
                            f"de capacitacion ({win_val}d). Secuenciar entregas."
                        ),
                        "resolver": ARBITRO,
                    })

    # Trigger 2: support-sla-missing
    if "soporte" in state.get("departments", []):
        # Use compliance evaluator to check if SLA is present
        draft = sop.get("draft_content", "")
        if draft:
            from services.api.services.rfp_evaluation import COMPLIANCE_RULES
            for rule in COMPLIANCE_RULES:
                if rule.rule_id == "support-sla-24h":
                    violation = rule.check(draft, state.get("client_hq", ""), state.get("currency", ""), "soporte")
                    if violation:
                        conflicts.append({
                            "trigger_id": "support-sla-missing",
                            "description": violation,
                            "resolver": "Roberto Díaz (soporte); Marcos si conflicto con staffing",
                        })
                    break

    # Trigger 3: currency-mismatch
    expected_currency = "USD" if "miami" in (state.get("client_hq", "") or "").lower() else "EUR"
    for dept_id in state.get("departments", []):
        dept_approval = approvals.get(dept_id, {})
        dept_currency = dept_approval.get("currency", state.get("currency", ""))
        if dept_currency and dept_currency.upper() != expected_currency:
            conflicts.append({
                "trigger_id": "currency-mismatch",
                "description": (
                    f"{dept_id} tiene moneda {dept_currency} pero la sede "
                    f"({state.get('client_hq', 'desconocida')}) requiere {expected_currency}."
                ),
                "resolver": ARBITRO,
            })

    return conflicts


def arbitrate_node(state: ApprovalState) -> dict[str, Any]:
    """Arbitraje explícito: detecta conflictos estructurados y los resuelve.

    Este es un nodo determinista (no LLM). Dispara ante triggers del CONTEXT.md §7
    y aplica la regla de resolución del árbitro fijo.
    """
    trace_entry = {
        "agent": "Arbitraje",
        "department_id": None,
        "input": {k: v for k, v in state.items() if k in ("ticket_id", "departments", "approvals")},
        "output": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        conflicts = _detect_conflicts(state)
        trace_entry["output"] = {"conflicts_detected": len(conflicts)}

        # Resolve deterministically
        for conflict in conflicts:
            tid = conflict["trigger_id"]
            if tid == "ttc-vs-training-window":
                # Rule: secuenciar entregas; forzar request_changes para que formación
                # no empiece antes de un cierre realista (>=15 días hábiles)
                if "seleccion" in state.get("approvals", {}):
                    state.setdefault("approvals", {})["seleccion"]["arbitration"] = "request_changes"
                logger.info("Arbitraje: %s — se fuerza request_changes en seleccion", tid)

            elif tid == "support-sla-missing":
                # Rule: bloquear aprobación hasta que SLA 24h sea explícito
                if "soporte" in state.get("approvals", {}):
                    state.setdefault("approvals", {})["soporte"]["arbitration"] = "request_changes"
                logger.info("Arbitraje: %s — se bloquea soporte hasta SLA explícito", tid)

            elif tid == "currency-mismatch":
                # Rule: reescribir a la moneda de la sede
                expected_currency = "USD" if "miami" in (state.get("client_hq", "") or "").lower() else "EUR"
                state["currency"] = expected_currency
                for dept_id in state.get("departments", []):
                    if dept_id in state.get("approvals", {}):
                        state["approvals"][dept_id]["currency"] = expected_currency
                logger.info("Arbitraje: %s — moneda unificada a %s", tid, expected_currency)

        state["conflicts"] = state.get("conflicts", []) + conflicts
        state["arbitration_required"] = len(conflicts) > 0
        trace_entry["output"]["resolved"] = len(conflicts)

    except Exception as exc:
        logger.error("Arbitraje error: %s", exc)
        trace_entry["output"]["error"] = str(exc)

    state.setdefault("trace", []).append(trace_entry)
    return state


# ── Node: department interrupt (fan-out) ──────────────────────────────


def _department_approval_node(state: ApprovalState, dept_id: str) -> dict[str, Any]:
    """Combined wait + check node for one department.

    Uses langgraph's `interrupt()` function to pause execution.
    When resumed via Command(resume=...), the node re-executes and
    `interrupt()` returns the resume value, which is then processed
    to update the department's approval status.
    """
    trace_entry = {
        "agent": f"Approval:{dept_id}",
        "department_id": dept_id,
        "input": {"department_id": dept_id},
        "output": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    dept_name = DEPARTMENT_APPROVERS.get(dept_id, dept_id)
    approver = DEPARTMENT_APPROVERS.get(dept_id, "Unknown")

    # Load the current draft from DB to show the approver
    sections = _get_sections(state["ticket_id"])
    section = next((s for s in sections if s.department_id == dept_id), None)
    draft = section.draft_content if section else ""

    approvals = state.setdefault("approvals", {})
    dept_approval = approvals.setdefault(dept_id, {})
    iteration = dept_approval.get("iteration", 0)

    # Call interrupt() — on first execution this pauses the graph.
    # On resume, it returns the value passed via Command(resume=...).
    resume_value = lg_interrupt(
        {
            "type": "department_approval",
            "department_id": dept_id,
            "department_name": dept_name,
            "approver": approver,
            "client_name": state.get("client_name", "—"),
            "currency": state.get("currency", "—"),
            "draft_preview": draft[:500] if draft else "(vacio)",
            "current_status": dept_approval.get("status", "pending"),
            "iteration": iteration,
            "max_iterations": MAX_APPROVAL_ITERATIONS,
            "actions_available": ["approve", "reject", "request_changes"],
        }
    )

    # If we get here, execution was resumed — process the resume value
    trace_entry["output"] = {"resume_value_received": True}

    # Parse the resume value
    # The resume data comes nested as {dept_id: {action, feedback, timestamp}}
    if isinstance(resume_value, dict):
        # Try direct fields first (for simple resume strings)
        action = resume_value.get("action", "").strip().lower()
        feedback = resume_value.get("feedback", "")
        # If action is not at top level, try nested by department_id
        if not action and dept_id in resume_value:
            nested = resume_value[dept_id]
            if isinstance(nested, dict):
                action = nested.get("action", "").strip().lower()
                feedback = nested.get("feedback", "")
    elif isinstance(resume_value, str):
        action = resume_value.strip().lower()
        feedback = ""
    else:
        action = ""
        feedback = ""

    if action in ("approve", "aprobar"):
        dept_approval["status"] = "approved"
        dept_approval["feedback"] = feedback or "Aprobado por responsable."
        _update_section_approval(
            state["ticket_id"], dept_id,
            ApprovalStatus.APPROVED,
            approved_by=DEPARTMENT_APPROVERS.get(dept_id),
        )
        trace_entry["output"]["action"] = "approved"
        logger.info("Departamento %s aprobado por %s", dept_id, DEPARTMENT_APPROVERS.get(dept_id))

    elif action in ("reject", "rechazar"):
        dept_approval["status"] = "rejected"
        dept_approval["feedback"] = feedback or "Rechazado por responsable."
        iteration += 1
        dept_approval["iteration"] = iteration

        if iteration >= MAX_APPROVAL_ITERATIONS:
            dept_approval["status"] = "needs_human_review"
            dept_approval["max_iterations_reached"] = True
            trace_entry["output"]["action"] = "max_iterations_reached"
            logger.warning(
                "Departamento %s agotó límite de iteraciones (%d)",
                dept_id, MAX_APPROVAL_ITERATIONS,
            )
            _update_section_approval(
                state["ticket_id"], dept_id,
                ApprovalStatus.PENDING,
            )
        else:
            _update_section_approval(
                state["ticket_id"], dept_id,
                ApprovalStatus.REJECTED,
                approved_by=DEPARTMENT_APPROVERS.get(dept_id),
            )
            trace_entry["output"]["action"] = "rejected"
            trace_entry["output"]["iteration"] = iteration
            logger.info("Departamento %s rechazado (iteración %d/%d)", dept_id, iteration, MAX_APPROVAL_ITERATIONS)

    elif action in ("request_changes", "cambios"):
        dept_approval["status"] = "request_changes"
        dept_approval["feedback"] = feedback or "Cambios solicitados."
        iteration += 1
        dept_approval["iteration"] = iteration

        if iteration >= MAX_APPROVAL_ITERATIONS:
            dept_approval["status"] = "needs_human_review"
            dept_approval["max_iterations_reached"] = True
            trace_entry["output"]["action"] = "max_iterations_reached"
            _update_section_approval(
                state["ticket_id"], dept_id,
                ApprovalStatus.PENDING,
            )
        else:
            _update_section_approval(
                state["ticket_id"], dept_id,
                ApprovalStatus.REQUEST_CHANGES,
                approved_by=DEPARTMENT_APPROVERS.get(dept_id),
            )
            trace_entry["output"]["action"] = "request_changes"
            trace_entry["output"]["iteration"] = iteration
            logger.info("Departamento %s solicita cambios (iteración %d/%d)", dept_id, iteration, MAX_APPROVAL_ITERATIONS)
    else:
        dept_approval["status"] = "pending"
        trace_entry["output"]["action"] = "unknown_action"
        trace_entry["output"]["received"] = action

    state.setdefault("trace", []).append(trace_entry)
    return state

def approval_node_seleccion(state: ApprovalState) -> dict[str, Any]:
    return _department_approval_node(state, "seleccion")

def approval_node_capacitacion(state: ApprovalState) -> dict[str, Any]:
    return _department_approval_node(state, "capacitacion")

def approval_node_soporte(state: ApprovalState) -> dict[str, Any]:
    return _department_approval_node(state, "soporte")


# ── Node: assemble document ───────────────────────────────────────────


def assemble_document_node(state: ApprovalState) -> dict[str, Any]:
    """FAN-IN: called when all departments have approved.

    Consolidates approved sections into the final document.
    """
    trace_entry = {
        "agent": "AssembleDocument",
        "input": {"ticket_id": state.get("ticket_id")},
        "output": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        sections = _get_sections(state["ticket_id"])
        active_sections = [s for s in sections if s.draft_content]
        approved_sections = [
            s for s in active_sections
            if s.approval_status == ApprovalStatus.APPROVED
        ]

        # Never publish a partial proposal or mark the ticket complete while
        # any department with an active draft is still awaiting a decision.
        if not active_sections or len(approved_sections) != len(active_sections):
            pending = [
                s.department_id for s in active_sections
                if s.approval_status != ApprovalStatus.APPROVED
            ]
            logger.warning(
                "Documento final bloqueado para ticket %s; pendientes=%s",
                state.get("ticket_id"), pending,
            )
            trace_entry["output"] = {"error": "Departments not all approved", "pending": pending}
            state.setdefault("trace", []).append(trace_entry)
            return state

        # Build final document
        parts: list[str] = []
        parts.append(f"# Propuesta Económica — {state.get('client_name', 'Cliente')}")
        parts.append("")
        parts.append(f"**Moneda:** {state.get('currency', 'EUR')}")
        parts.append(f"**Generado:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        parts.append("")
        parts.append("---")
        parts.append("")

        for sec in approved_sections:
            dept_name = sec.department_name or sec.department_id
            parts.append(f"## Sección: {dept_name}")
            parts.append(f"**Aprobado por:** {sec.approved_by or '—'}")
            parts.append(f"**Aprobado el:** {sec.approved_at.isoformat() if sec.approved_at else '—'}")
            parts.append("")
            if sec.draft_content:
                parts.append(sec.draft_content)
            else:
                parts.append("_(sin contenido)_")
            parts.append("")
            parts.append("---")
            parts.append("")

        parts.append("*Documento generado automáticamente por Nexova AI Pipeline*")

        content = "\n".join(parts)
        _save_final_document(state["ticket_id"], content)

        state["final_document"] = content
        state["generated_at"] = datetime.now(timezone.utc).isoformat()

        # Update ticket status to terminado
        _update_ticket_status(state["ticket_id"], TicketStatus.TERMINADO)

        trace_entry["output"] = {
            "sections_count": len(approved_sections),
            "document_length": len(content),
        }
        logger.info("Documento final generado para ticket %s (%d secciones)", state["ticket_id"], len(approved_sections))

    except Exception as exc:
        logger.error("Error generando documento final: %s", exc)
        trace_entry["output"] = {"error": str(exc)}

    state.setdefault("trace", []).append(trace_entry)
    return state


# ── Edge conditions ───────────────────────────────────────────────────


def _all_approved(state: ApprovalState) -> bool:
    """Check if all active departments have approved."""
    approvals = state.get("approvals", {})
    for dept_id in state.get("departments", []):
        dept = approvals.get(dept_id, {})
        if dept.get("status") != "approved":
            return False
    return True


def _persist_trace(ticket_id: str, trace: list[dict[str, Any]]) -> None:
    """Persist newly emitted pipeline trace entries as durable audit events."""
    if not trace:
        return
    try:
        with Session(engine) as session:
            for entry in trace:
                session.add(RFPApprovalTrace(
                    ticket_id=ticket_id,
                    department_id=entry.get("department_id"),
                    agent=str(entry.get("agent", "unknown")),
                    input_data=entry.get("input", {}),
                    output_data=entry.get("output", {}),
                    created_at=datetime.fromisoformat(entry["timestamp"]),
                ))
            session.commit()
    except Exception:
        logger.exception("No se pudo persistir la traza RFP para %s", ticket_id)


def _finalize_if_all_sections_approved(
    ticket_id: str, state: dict[str, Any]
) -> dict[str, Any] | None:
    """Finalize based on persisted active sections, not graph-only nodes."""
    active_sections = [section for section in _get_sections(ticket_id) if section.draft_content]
    if not active_sections or any(
        section.approval_status != ApprovalStatus.APPROVED
        for section in active_sections
    ):
        return None

    state = dict(state)
    state["ticket_id"] = ticket_id
    state["departments"] = [section.department_id for section in active_sections]
    state.setdefault("approvals", {})
    for section in active_sections:
        state["approvals"].setdefault(section.department_id, {"status": "approved"})
    completed_state = assemble_document_node(state)
    _persist_trace(ticket_id, completed_state.get("trace", []))
    return {
        "status": "completed",
        "ticket_id": ticket_id,
        "approvals": completed_state.get("approvals", {}),
        "final_document": completed_state.get("final_document"),
        "trace": completed_state.get("trace", []),
    }


def _any_needs_human_review(state: ApprovalState) -> bool:
    """Check if any active department exhausted iterations."""
    approvals = state.get("approvals", {})
    for dept_id in state.get("departments", []):
        dept = approvals.get(dept_id, {})
        if dept.get("max_iterations_reached"):
            return True
    return False


# ── Routing functions ─────────────────────────────────────────────────


def route_after_arbitration(state: ApprovalState) -> Literal["fan_out", "done"]:
    """After arbitration: fan out to department branches."""
    depts = state.get("departments", [])
    if not depts:
        return "done"
    return "fan_out"


def route_after_fan_out(state: ApprovalState) -> Literal["fan_in", "wait"]:
    """After fan-out: check if ready to assemble."""
    if _all_approved(state) or _any_needs_human_review(state):
        return "fan_in"
    return "wait"


def route_after_fan_in(state: ApprovalState) -> Literal["done", "fan_out"]:
    """After assembling: done, or back to fan_out if not all approved."""
    if _all_approved(state):
        return "done"
    if _any_needs_human_review(state):
        # All active departments have exhausted iterations or approved
        return "done"
    return "fan_out"


# ── Fan-out / fan-in helpers ──────────────────────────────────────────


def _fan_out_departments(state: ApprovalState) -> list[Send]:
    """Send a department_interrupt_node message for each active department."""
    depts = state.get("departments", [])
    return [Send("department_interrupt_node", {"department_id": d}) for d in depts]


# ── Resume handler ────────────────────────────────────────────────────


def resume_approval(
    ticket_id: str,
    department_id: str,
    action: str,
    feedback: str = "",
) -> dict[str, Any]:
    """Resume an interrupted approval for a specific department.

    This is the explicit entry point for the human response.
    Validates the action before passing it to the graph.

    Args:
        ticket_id: The ticket ID to resume.
        department_id: The department ID to resume.
        action: One of 'approve', 'reject', 'request_changes'.
        feedback: Optional feedback text.

    Returns:
        The updated approval state.
    """
    valid_actions = {"approve", "aprobar", "reject", "rechazar", "request_changes", "cambios"}
    action_clean = action.strip().lower()
    if action_clean not in valid_actions:
        raise ValueError(
            f"Acción inválida: '{action}'. "
            f"Válidas: {', '.join(valid_actions)}"
        )

    # Validate feedback for rejections and change requests
    if action_clean in ("reject", "rechazar", "request_changes", "cambios") and not feedback.strip():
        raise ValueError(
            "Debes proporcionar feedback (razón del rechazo o cambios solicitados)."
        )

    # Build the resume data
    thread_id = f"rfp-{ticket_id}"
    resume_data = {
        department_id: {
            "action": action_clean,
            "feedback": feedback.strip(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }

    # Update ticket status to esperando_aprobacion on first resume
    _update_ticket_status(ticket_id, TicketStatus.ESPERANDO_APROBACION)

    return {
        "thread_id": thread_id,
        "department_id": department_id,
        "resume_data": resume_data,
    }


# ── Build the graph ───────────────────────────────────────────────────


def build_approval_graph(*, checkpointer=None) -> StateGraph:
    """Build the Part 3 approval StateGraph.

    Args:
        checkpointer: Optional checkpointer to use. Defaults to PostgresSaver.
            Pass MemorySaver() for unit tests that have no Postgres DB.
    """
    if checkpointer is None:
        checkpointer = get_checkpointer()
    builder = StateGraph(ApprovalState)

    # Nodes
    builder.add_node("arbitrate_node", arbitrate_node)
    builder.add_node("approval_seleccion", approval_node_seleccion)
    builder.add_node("approval_capacitacion", approval_node_capacitacion)
    builder.add_node("approval_soporte", approval_node_soporte)
    builder.add_node("assemble_document_node", assemble_document_node)

    # Entry point
    builder.set_entry_point("arbitrate_node")

    # Edges: arbitration -> chained department approvals
    builder.add_conditional_edges(
        "arbitrate_node",
        route_after_arbitration,
        {
            "fan_out": "approval_seleccion",
            "done": END,
        },
    )

    # Department approvals are sequential in the current graph topology.
    # Keep the transition explicit and route non-active departments through
    # their nodes as no-ops; the selected department is resumed via its interrupt.
    builder.add_edge("approval_seleccion", "approval_capacitacion")
    builder.add_edge("approval_capacitacion", "approval_soporte")

    builder.add_conditional_edges(
        "approval_soporte",
        route_after_fan_out,
        {
            "fan_in": "assemble_document_node",
            "wait": END,
        },
    )

    builder.add_conditional_edges(
        "assemble_document_node",
        route_after_fan_in,
        {
            "done": END,
            "fan_out": "approval_seleccion",
        },
    )

    return builder.compile(checkpointer=checkpointer)


# ── Convenience: run / resume helpers ─────────────────────────────────


def _department_thread_id(ticket_id: str, department_id: str) -> str:
    return f"rfp-{ticket_id}-{department_id}"


def _department_branch_node(state: ApprovalState) -> dict[str, Any]:
    department_id = state.get("department_id", "")
    node = {
        "seleccion": approval_node_seleccion,
        "capacitacion": approval_node_capacitacion,
        "soporte": approval_node_soporte,
    }.get(department_id)
    if node is None:
        raise ValueError(f"Departamento inválido: {department_id}")
    return node(state)


def _route_department_repeat(state: ApprovalState) -> Literal["repeat", "done"]:
    dept = state.get("approvals", {}).get(state.get("department_id", ""), {})
    if dept.get("status") in {"approved", "needs_human_review"}:
        return "done"
    if dept.get("iteration", 0) >= MAX_APPROVAL_ITERATIONS:
        return "done"
    return "repeat"


def build_department_approval_graph(*, checkpointer=None):
    """Compile one independently checkpointed HITL branch per department."""
    if checkpointer is None:
        checkpointer = get_checkpointer()
    builder = StateGraph(ApprovalState)
    builder.add_node("department_approval", _department_branch_node)
    builder.set_entry_point("department_approval")
    builder.add_conditional_edges(
        "department_approval", _route_department_repeat,
        {"repeat": "department_approval", "done": END},
    )
    return builder.compile(checkpointer=checkpointer)


def run_approval_pipeline(
    ticket_id: str,
    client_name: str = "",
    client_hq: str = "",
    currency: str = "EUR",
    checkpointer=None,
) -> dict[str, Any]:
    """Start the approval pipeline for a ticket.

    Loads department sections from the DB, sets up the initial state,
    and runs the graph up to the first interrupt.

    Args:
        ticket_id: The ticket to start approval for.
        client_name: Optional client name.
        client_hq: Optional client HQ location.
        currency: Optional currency (default: EUR).
        checkpointer: Optional checkpointer override. Pass MemorySaver()
            for unit tests without a Postgres DB.

    Returns:
        Dict with status, ticket_id, approvals, etc.
    """
    sections = _get_sections(ticket_id)
    active_departments = sorted({s.department_id for s in sections if s.draft_content})

    if not active_departments:
        logger.warning("Ticket %s no tiene borradores para aprobar", ticket_id)
        return {"status": "no_drafts", "ticket_id": ticket_id}

    # Update ticket status
    _update_ticket_status(ticket_id, TicketStatus.ESPERANDO_APROBACION)

    # Build initial state
    initial_state: ApprovalState = {
        "ticket_id": ticket_id,
        "client_name": client_name,
        "client_hq": client_hq,
        "currency": currency,
        "departments": active_departments,
        "approvals": {},
        "conflicts": [],
        "arbitration_required": False,
        "trace": [],
        "final_document": None,
        "generated_at": None,
    }

    graph = build_department_approval_graph(checkpointer=checkpointer)
    arbitration_state = dict(initial_state)
    arbitration_state["approvals"] = {
        s.department_id: {
            "draft_content": s.draft_content or "",
            "currency": currency,
        }
        for s in sections if s.draft_content
    }
    arbitration_state = arbitrate_node(ApprovalState(arbitration_state))
    _persist_trace(ticket_id, arbitration_state.get("trace", []))

    try:
        for department_id in active_departments:
            thread_id = _department_thread_id(ticket_id, department_id)
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint_state = graph.get_state(config)
            if checkpoint_state.values:
                continue
            branch_state = dict(initial_state)
            branch_state["department_id"] = department_id
            branch_state["approvals"] = {
                department_id: arbitration_state.get("approvals", {}).get(department_id, {})
            }
            result = graph.invoke(branch_state, config)
            _persist_trace(ticket_id, result.get("trace", []))
            if result.get("__interrupt__"):
                logger.info("Approval paused: ticket=%s department=%s", ticket_id, department_id)
        return {
            "status": "waiting_approval",
            "ticket_id": ticket_id,
            "thread_ids": {
                dept: _department_thread_id(ticket_id, dept) for dept in active_departments
            },
            "departments": active_departments,
        }
    except Exception as exc:
        logger.error("Pipeline error for ticket %s: %s", ticket_id, exc)
        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": str(exc),
        }


def resume_approval_pipeline(
    ticket_id: str,
    department_id: str,
    action: str,
    feedback: str = "",
    checkpointer=None,
) -> dict[str, Any]:
    """Resume an interrupted approval pipeline.

    Args:
        ticket_id: The ticket to resume.
        department_id: The department to respond to.
        action: approve / reject / request_changes.
        feedback: Required for reject/request_changes.
        checkpointer: Optional checkpointer override. Pass MemorySaver()
            for unit tests without a Postgres DB.

    Returns:
        The updated graph state after resume.
    """
    # Validate
    valid_actions = {"approve", "aprobar", "reject", "rechazar", "request_changes", "cambios"}
    action_clean = action.strip().lower()
    if action_clean not in valid_actions:
        raise ValueError(f"Acción inválida: '{action}'")

    if action_clean in ("reject", "rechazar", "request_changes", "cambios") and not feedback.strip():
        raise ValueError("Debes proporcionar feedback con la acción.")

    if department_id not in DEPARTMENT_APPROVERS:
        raise ValueError(f"Departamento inválido: {department_id}")

    thread_id = _department_thread_id(ticket_id, department_id)
    resume_data = {
        "action": action_clean,
        "feedback": feedback.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    graph = build_department_approval_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}

    try:
        checkpoint_state = graph.get_state(config)
        if not checkpoint_state.next:
            # Older tickets can be left in esperando_aprobacion after a process
            # restart or an incomplete legacy fan-out. Recreate only this
            # department's branch, then resume it with the user's decision.
            sections = _get_sections(ticket_id)
            section = next(
                (item for item in sections if item.department_id == department_id),
                None,
            )
            if section is None or not section.draft_content:
                raise RuntimeError(
                    f"No hay borrador de {department_id} para el ticket {ticket_id}; "
                    "no se puede iniciar su aprobación."
                )
            thread_id = _department_thread_id(ticket_id, department_id)
            config = {"configurable": {"thread_id": thread_id}}
            branch_state: ApprovalState = {
                "ticket_id": ticket_id,
                "client_name": "",
                "client_hq": "",
                "currency": "EUR",
                "departments": [department_id],
                "department_id": department_id,
                "approvals": {
                    department_id: {
                        "draft_content": section.draft_content,
                        "currency": "EUR",
                    }
                },
                "conflicts": [],
                "arbitration_required": False,
                "trace": [],
                "final_document": None,
                "generated_at": None,
            }
            started = graph.invoke(branch_state, config)
            checkpoint_state = graph.get_state(config)
            if not checkpoint_state.next:
                raise RuntimeError(
                    f"No se pudo crear la interrupción pendiente para {department_id} "
                    f"en el ticket {ticket_id}."
                )
        result = graph.invoke(Command(resume=resume_data), config)
        _persist_trace(ticket_id, result.get("trace", []))
        # A graph may interrupt on a department that has no draft for this ticket.
        # Reconcile the real persisted sections so a fully approved ticket finishes.
        if action_clean in {"approve", "aprobar"}:
            _update_section_approval(
                ticket_id, department_id, ApprovalStatus.APPROVED,
                approved_by=DEPARTMENT_APPROVERS.get(department_id),
            )
        elif action_clean in {"reject", "rechazar"}:
            _update_section_approval(ticket_id, department_id, ApprovalStatus.REJECTED)
        else:
            _update_section_approval(ticket_id, department_id, ApprovalStatus.REQUEST_CHANGES)

        finalized = _finalize_if_all_sections_approved(ticket_id, result)
        if finalized is not None:
            logger.info("All active sections approved; finalized ticket=%s", ticket_id)
            return finalized

        # Check if re-interrupted
        if result.get("__interrupt__"):
            logger.info("Pipeline re-paused for approval: ticket=%s, thread=%s", ticket_id, thread_id)
            return {
                "status": "waiting_approval",
                "ticket_id": ticket_id,
                "thread_id": thread_id,
                "approvals": result.get("approvals", {}),
            }
        return {
            "status": "completed" if result.get("final_document") else "waiting_approval",
            "ticket_id": ticket_id,
            "department_id": department_id,
            "approvals": result.get("approvals", {}),
            "final_document": result.get("final_document"),
            "trace": result.get("trace", []),
        }
    except Exception as exc:
        logger.error("Resume error for ticket %s: %s", ticket_id, exc)
        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": str(exc),
        }
