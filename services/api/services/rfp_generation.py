"""
RFP Generation Pipeline — Part 2: Proposal draft generation per department.

Consumes the handoff from Part 1 (ticket_id -> handoff_json + key_aspects in DB).
Does NOT re-ingest the raw PDF.

Architecture:
  For each active department:
    1. Generator agent reads handoff data + key_aspects from Part 1
    2. Produces a proposal section draft (draft_content)
    3. Persists draft content to DepartmentSection
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from services.api.database import engine
from services.api.models import (
    DepartmentSection,
    RFPMetadata,
    Ticket,
    TicketStatus,
)
from services.api.services.rfp_evaluation import (
    EvaluationResult,
    evaluate_section,
)

logger = logging.getLogger(__name__)

# Max times the generator↔evaluator loop may iterate per section before
# the section (and ticket) is flagged needs_human_review.
MAX_ITERATIONS = 3

# ── Department generator prompts ───────────────────────────────────────

_DEPARTMENT_PROMPTS = {
    "seleccion": (
        "Eres un redactor de propuestas para Talent Selection Operations de Nexova.\n"
        "Redacta la sección de propuesta económica para un servicio de selección ejecutiva.\n"
        "Debes incluir:\n"
        "- Alcance del servicio (roles a cubrir, perfil solicitado)\n"
        "- Metodología de selección (headhunting, screening, assessment)\n"
        "- Cronograma estimado\n"
        "- Estructura de costos (honorarios de consultoría)\n"
        "- Tono profesional, directo, orientado a resultados\n\n"
        "Datos de entrada:\n"
    ),
    "capacitacion": (
        "Eres un redactor de propuestas para Corporate Training de Nexova.\n"
        "Redacta la sección de propuesta económica para un programa de formación corporativa.\n"
        "Debes incluir:\n"
        "- Programas de formación aplicables\n"
        "- Modalidad y duración\n"
        "- Metodología pedagógica y certificaciones\n"
        "- Estructura de costos por participante y por módulo\n"
        "- Tono formativo, pedagógico, orientado al desarrollo\n\n"
        "Datos de entrada:\n"
    ),
    "soporte": (
        "Eres un redactor de propuestas para Customer Support (outsourcing) de Nexova.\n"
        "Redacta la sección de propuesta económica para un servicio de soporte externalizado.\n"
        "Debes incluir:\n"
        "- Dotación de agentes y perfil del equipo\n"
        "- Turnos y cobertura horaria\n"
        "- Infraestructura y herramientas\n"
        "- Estructura de costos por agente y por turno\n"
        "- Tono de servicio, confiable, orientado a la operación\n\n"
        "Datos de entrada:\n"
    ),
}


def _generate_draft_llm(
    dept_id: str, prompt_data: str, feedback: str | None = None
) -> str | None:
    """Generate a proposal draft via LLM. Returns None on failure (fallback to template).

    Args:
        dept_id: department id.
        prompt_data: structured context from the Part 1 handoff (not raw PDF).
        feedback: optional feedback_for_generator from a failed evaluation;
            injected into the prompt so the model corrects the previous draft.
    """
    try:
        from openai import OpenAI
        client = OpenAI()
    except Exception:
        return None

    base_prompt = _DEPARTMENT_PROMPTS.get(dept_id, "Redacta una propuesta comercial.\n")
    full_prompt = base_prompt + prompt_data
    if feedback:
        full_prompt = (
            f"{full_prompt}\n\n-- FEEDBACK DE LA ÚLTIMA EVALUACIÓN (corrige esto) --\n"
            f"{feedback}\n"
        )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.4,
            max_tokens=1500,
        )
        result = resp.choices[0].message.content
        return result if result else None
    except Exception as exc:
        logger.warning("LLM generation failed for %s: %s", dept_id, exc)
        return None


def _generate_draft_template(
    dept_id: str, key_aspects: dict[str, Any], client_name: str, currency: str
) -> str:
    """Fallback template-based draft generation."""
    dept_names = {
        "seleccion": "Talent Selection Operations",
        "capacitacion": "Corporate Training",
        "soporte": "Customer Support (outsourcing)",
    }
    dept_name = dept_names.get(dept_id, dept_id)

    lines: list[str] = []
    lines.append(f"# Propuesta — {dept_name}")
    lines.append(f"**Cliente:** {client_name} | **Moneda:** {currency}")
    lines.append("")

    if dept_id == "seleccion":
        roles = key_aspects.get("roles_to_cover", ["—"])
        lines.append("## 1. Alcance del Servicio")
        lines.append(
            f"Proceso de selección ejecutiva para cubrir: "
            f"{', '.join(str(r) for r in roles)}."
        )
        lines.append("")
        lines.append("## 2. Metodología")
        lines.append(
            "Headhunting directo, screening curricular y assessment "
            "por competencias con shortlist en 15 días hábiles."
        )
        lines.append("")
        lines.append("## 3. Estructura de Costos")
        lines.append(
            "Honorarios: porcentaje del salario anual bruto del "
            "candidato seleccionado + 40 horas de consultoría por rol."
        )

    elif dept_id == "capacitacion":
        programs = key_aspects.get("applicable_programs", ["—"])
        lines.append("## 1. Programas de Formación")
        lines.append(f"Aplicables: {', '.join(str(p) for p in programs)}.")
        lines.append("")
        lines.append("## 2. Metodología")
        lines.append(
            "Sesiones teórico-prácticas con casos reales, "
            "evaluación continua y medición de impacto. "
            "Modalidad adaptable (presencial/virtual/híbrido)."
        )
        lines.append("")
        lines.append("## 3. Estructura de Costos")
        lines.append(
            "Por participante: materiales, plataforma virtual y certificación oficial Nexova."
        )

    elif dept_id == "soporte":
        agent_count = key_aspects.get("agent_count", "—")
        shifts = key_aspects.get("shifts", "—")
        lines.append("## 1. Dotación")
        lines.append(
            f"{agent_count} agentes bilingües con experiencia en soporte técnico."
        )
        lines.append("")
        lines.append("## 2. Cobertura")
        lines.append(f"Turnos: {shifts}. SLA: 24h consultas generales.")
        lines.append("")
        lines.append("## 3. Estructura de Costos")
        lines.append(
            "Costo mensual: salarios, herramientas de ticketing, "
            "telefonía IP y supervisión de calidad."
        )

    lines.append("")
    lines.append("---")
    lines.append(f"*Propuesta generada para {client_name} — {dept_name} — Nexova*")

    return "\n".join(lines)


def _apply_template_fix(
    dept_id: str, draft: str, client_name: str, currency: str,
    key_aspects: dict[str, Any] | None = None,
) -> str:
    """Apply deterministic fixes for known CONTEXT.md §5 compliance gaps.

    The template generator is deterministic, so the generator↔evaluator loop
    cannot converge on compliance by re-running it. This "fix pass" patches the
    draft for the well-known rules (guarantee, currency, SLA, anonymization)
    so the loop can actually pass, or reach a stable needs_human_review state.

    When key_aspects is provided, also patches known relevance gaps
    (e.g. open questions and estimated close time).
    """
    fixed = draft

    # Rule 1: 90-day guarantee (only if not present)
    low = fixed.lower()
    if "90" not in low or ("garant" not in low and "satisfacci" not in low):
        fixed = fixed.replace(
            "**Cliente:**", "**Garantía Nexova:** satisfacción asegurada a 90 días.\n\n**Cliente:**"
        )

    # Rule 2: currency — align with metadata currency
    marker = "**Moneda:**"
    if marker in fixed and currency:
        # Replace the currency token after the marker (avoid double EUR EUR)
        fixed = re.sub(
            rf"{re.escape(marker)}\s*\S+",
            f"{marker} {currency.upper()}",
            fixed,
        )

    # Rule 4: 24h SLA for soporte (if not present)
    if dept_id == "soporte":
        low = fixed.lower()
        if "24" not in low or ("sla" not in low and "respuesta" not in low):
            fixed = fixed.replace(
                "## 2. Cobertura", "SLA de respuesta en 24 horas.\n\n## 2. Cobertura"
            )

    # Rule 5: anonymize any real client reference (keep target client name)
    from services.api.services.rfp_evaluation import _CLIENT_REF_PATTERN

    target_tokens = {t.lower() for t in (client_name or "").split()}
    def _anon(match: re.Match) -> str:
        if match.group(0).lower() in target_tokens:
            return match.group(0)
        return "cliente del sector retail"
    fixed = _CLIENT_REF_PATTERN.sub(_anon, fixed)

    # ── Relevance gap patches ──────────────────────────────────────
    if key_aspects:
        # Acknowledge open questions at the end of the draft
        open_qs = key_aspects.get("open_questions", []) or []
        if open_qs:
            unresolved = []
            for q in open_qs:
                q_lower = str(q).lower()
                # Check if any word >3 chars from the question appears in the draft
                q_words = [w for w in q_lower.split() if len(w) > 3]
                if not any(w in fixed.lower() for w in q_words):
                    unresolved.append(str(q))
            if unresolved:
                footer = (
                    f"\n\n## Preguntas por Confirmar\n"
                    f"Estamos a la espera de su confirmación sobre: "
                    f"{'; '.join(unresolved)}.\n"
                    f"Quedamos atentos para ajustar la propuesta según "
                    f"sus necesidades específicas."
                )
                fixed += footer

        # Explicit mention of estimated_close_time if present
        if key_aspects.get("estimated_close_time"):
            low = fixed.lower()
            if not any(t in low for t in ["shortlist", "días hábiles", "dias habiles"]):
                fixed = fixed.replace(
                    "## 2. Metodología",
                    "## 2. Metodología\n"
                    "Plazo estimado de cierre: "
                    f"{key_aspects['estimated_close_time']} a confirmar con el cliente.\n",
                )

        # Explicit mention of duration for training/relevance
        if dept_id == "capacitacion" and key_aspects.get("duration"):
            low = fixed.lower()
            dur_terms = ["duraci", "duration", "trimestr", "plazo", "tiempo"]
            if not any(t in low for t in dur_terms):
                fixed += (
                    f"\n\n## Duración\n"
                    f"Duración estimada del programa: "
                    f"{key_aspects['duration']} a confirmar con el cliente."
                )

    return fixed


def _generate_draft_with_feedback(
    dept_id: str,
    key_aspects: dict[str, Any],
    client_name: str,
    currency: str,
    prompt_data: str,
    feedback: str | None = None,
    use_template: bool = False,
) -> str:
    """Generate a corrected draft, using LLM first (with feedback) or the template fix pass.

    - If LLM is available: re-run the generator with feedback injected.
    - Otherwise (or if template fallback): apply the deterministic fix pass.
    """
    if use_template or not _llm_available():
        return _apply_template_fix(
            dept_id,
            _generate_draft_template(
                dept_id, key_aspects, client_name, currency
            ),
            client_name,
            currency,
            key_aspects=key_aspects,
        )

    draft = _generate_draft_llm(dept_id, prompt_data, feedback)
    if not draft:
        return _apply_template_fix(
            dept_id,
            _generate_draft_template(
                dept_id, key_aspects, client_name, currency
            ),
            client_name,
            currency,
            key_aspects=key_aspects,
        )
    return draft


def _llm_available() -> bool:
    """Return True if an OpenAI client can be constructed (best-effort)."""
    try:
        from openai import OpenAI
        OpenAI()
        return True
    except Exception:
        return False


# ── Main pipeline ──────────────────────────────────────────────────────


def run_rfp_generation(ticket_id: str) -> dict[str, Any]:
    """
    Part 2 entry point.

    1. Read handoff + metadata from Part 1 (no re-ingestion of raw PDF)
    2. For each active department, generate a proposal draft
    3. Persist draft_content to DepartmentSection
    4. Update ticket status

    Args:
        ticket_id: UUID of the ticket from Part 1.

    Returns:
        Dict with generation results per department.
    """
    logger.info("RFP generation pipeline starting (ticket=%s)", ticket_id)

    with Session(engine) as session:
        ticket = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if not ticket:
            return {"error": f"Ticket {ticket_id} not found"}

        # Only proceed if Part 1 completed successfully
        if ticket.status != TicketStatus.ANALISIS_COMPLETO:
            return {
                "error": f"Ticket {ticket_id} not ready for generation "
                f"(status={ticket.status})"
            }

        # Read handoff payload from Part 1
        handoff = json.loads(ticket.handoff_json) if ticket.handoff_json else {}
        client_name = handoff.get("client_name", "Cliente no identificado")

        # Read metadata for currency and HQ
        rfp_meta = (
            session.query(RFPMetadata)
            .filter(RFPMetadata.ticket_id == ticket_id)
            .first()
        )
        client_hq = rfp_meta.client_hq if rfp_meta else "España"
        currency = rfp_meta.currency if rfp_meta else "EUR"

        # Get department sections
        sections = (
            session.query(DepartmentSection)
            .filter(DepartmentSection.ticket_id == ticket_id)
            .all()
        )

    if not sections:
        return {"error": f"No department sections for ticket {ticket_id}"}

    # Process each department
    results: dict[str, Any] = {}
    any_needs_human_review = False

    # Transition ticket to generando_borrador once processing starts
    with Session(engine) as session:
        ticket_db = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if ticket_db:
            ticket_db.status = TicketStatus.GENERANDO_BORRADOR
            ticket_db.updated_at = datetime.now(timezone.utc)
            session.commit()

    for section in sections:
        dept_id = section.department_id
        logger.info("Generating draft for %s (ticket=%s)", dept_id, ticket_id)

        key_aspects = json.loads(section.key_aspects) if section.key_aspects else {}
        dept_handoff = handoff.get("workstreams", {}).get(dept_id, {})

        # Build structured prompt data from Part 1 handoff (NOT from raw PDF)
        base_prompt_data = json.dumps(
            {
                "client_name": client_name,
                "client_hq": client_hq,
                "currency": currency,
                "key_aspects": key_aspects,
                "department_data": dept_handoff,
                "open_questions": key_aspects.get("open_questions", []),
            },
            ensure_ascii=False,
            indent=2,
        )

        # ── Generator ↔ evaluator loop with iteration limit ──
        draft: str | None = None
        evaluation: EvaluationResult | None = None
        final_feedback: str | None = None
        iterations = 0
        needs_human_review = False

        # Transition ticket to en_evaluacion before the first evaluation
        with Session(engine) as session:
            ticket_db = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
            if ticket_db and ticket_db.status != TicketStatus.EN_EVALUACION:
                ticket_db.status = TicketStatus.EN_EVALUACION
                ticket_db.updated_at = datetime.now(timezone.utc)
                session.commit()

        while iterations < MAX_ITERATIONS:
            iterations += 1
            logger.info(
                "  Iteration %d/%d for %s", iterations, MAX_ITERATIONS, dept_id
            )

            # Generate (LLM first with feedback, template fallback / fix pass)
            if iterations == 1:
                draft = _generate_draft_llm(dept_id, base_prompt_data)
                if not draft:
                    draft = _apply_template_fix(
                        dept_id,
                        _generate_draft_template(
                            dept_id, key_aspects, client_name, currency
                        ),
                        client_name,
                        currency,
                        key_aspects=key_aspects,
                    )
            else:
                draft = _generate_draft_with_feedback(
                    dept_id,
                    key_aspects,
                    client_name,
                    currency,
                    base_prompt_data,
                    feedback=final_feedback,
                    use_template=not _llm_available(),
                )

            # Persist the latest draft (kept even on final failure)
            with Session(engine) as session:
                db_section = (
                    session.query(DepartmentSection)
                    .filter(
                        DepartmentSection.ticket_id == ticket_id,
                        DepartmentSection.department_id == dept_id,
                    )
                    .first()
                )
                if db_section:
                    db_section.draft_content = draft
                    db_section.iteration_count = iterations
                    session.commit()

            # Parallel evaluation of this section
            evaluation = evaluate_section(
                department_id=dept_id,
                draft=draft,
                key_aspects=key_aspects,
                client_hq=client_hq,
                currency=currency,
                client_name=client_name,
            )
            final_feedback = evaluation.feedback_for_generator

            with Session(engine) as session:
                db_section = (
                    session.query(DepartmentSection)
                    .filter(
                        DepartmentSection.ticket_id == ticket_id,
                        DepartmentSection.department_id == dept_id,
                    )
                    .first()
                )
                if db_section:
                    db_section.evaluation_result = evaluation.to_json()
                    db_section.iteration_count = iterations
                    db_section.needs_human_review = not evaluation.overall_pass
                    session.commit()
                    logger.info(
                        "  Iteration %d evaluated for %s (overall_pass=%s)",
                        iterations, dept_id, evaluation.overall_pass,
                    )

            if evaluation.overall_pass:
                break

        # Loop ended. If it exhausted the limit without passing -> needs_human_review.
        # Keep the last draft + its EvaluationResult (already persisted above).
        needs_human_review = not evaluation.overall_pass if evaluation else True
        if needs_human_review:
            any_needs_human_review = True
            logger.warning(
                "Section %s exhausted %d iterations -> needs_human_review",
                dept_id, MAX_ITERATIONS,
            )

        results[dept_id] = {
            "department_name": section.department_name or dept_id,
            "draft_length": len(draft) if draft else 0,
            "generated": True,
            "needs_human_review": needs_human_review,
            "iterations": iterations,
            "evaluation": evaluation.to_dict() if evaluation else None,
        }

    # Generation is complete when all department drafts have been persisted.
    # A compliant draft is ready to enter Part 3; a failed evaluation remains
    # explicitly flagged for human review before approval starts.
    final_status = (
        TicketStatus.NEEDS_HUMAN_REVIEW
        if any_needs_human_review
        else TicketStatus.ESPERANDO_APROBACION
    )
    with Session(engine) as session:
        ticket = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if ticket:
            ticket.status = final_status
            ticket.updated_at = datetime.now(timezone.utc)
            session.commit()

    logger.info(
        "RFP generation completed (ticket=%s, status=%s, departments=%s)",
        ticket_id, final_status.value, list(results.keys()),
    )

    return {
        "ticket_id": ticket_id,
        "ticket_status": final_status.value,
        "needs_human_review": any_needs_human_review,
        "departments": results,
    }


def launch_generation(ticket_id: str) -> dict[str, Any]:
    """
    Launch Part 2 generation synchronously (to be called from background thread).
    """
    try:
        return run_rfp_generation(ticket_id)
    except Exception as exc:
        logger.exception("Generation pipeline failed (ticket=%s)", ticket_id)
        with Session(engine) as session:
            ticket = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
            if ticket:
                ticket.status = TicketStatus.DESCARTADO
                ticket.error_message = f"Generation error: {exc}"
                ticket.updated_at = datetime.now(timezone.utc)
                session.commit()
        return {"error": str(exc)}
