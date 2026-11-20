"""HTTP endpoint exposing the compiled knowledge agent graph."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from services.api.security import CurrentUser, get_current_user

from services.api.routes.knowledge import KnowledgeQueryRequest, KnowledgeQueryResponse
from services.api.services.knowledge_graph import run_knowledge_graph
from services.api.services.agent_memory import get_memory_service
from services.api.services.memory_classifier import MemoryClassifier, MemoryVerdict
from services.api.services.harness import pre_graph_guardrails, get_guardrail_stats
from mcps.nexova_mcp.request_context import api_bearer_token

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/guardrail-stats")
def guardrail_stats() -> dict:
    """Resumen de cuántas veces se activó cada guardrail durante la sesión."""
    return get_guardrail_stats()


@router.post("/query", response_model=KnowledgeQueryResponse)
def agent_query(
    payload: KnowledgeQueryRequest,
    current_user: CurrentUser,
) -> KnowledgeQueryResponse:
    """
    Invoke the compiled graph, handling pending memory proposals before
    graph execution.
    """
    from services.api.security import create_access_token

    # ── Phase 1: Handle any pending memory proposal ────────────────────────
    mem_svc = get_memory_service()
    proposal_obj = mem_svc.get_proposal()

    if proposal_obj is not None:
        _handle_proposal(mem_svc, payload.question, proposal_obj, current_user.id)
        # After handling, the proposal is cleared; proceed with normal query.

    # ── Phase 2: Pre-graph guardrails (jailbreak, chatbot personal, cross-client, etc.) ──
    # Ejecutar SIEMPRE, independientemente de si hay propuesta de memoria pendiente.
    guardrail_result = pre_graph_guardrails(payload.question)
    if guardrail_result["blocked"]:
        log_data = {
            "action": "blocked_by_guardrail",
            "reason": guardrail_result["block_reason"],
            "question": payload.question,
            "user_id": current_user.id,
        }
        logger.warning("GUARDRAIL_BLOCKED %s", log_data)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Lo siento, solo puedo ayudarte con consultas de soporte de Nexova. "
                "Si tienes alguna pregunta sobre tu ticket, incidencia o los servicios "
                "de soporte, estaré encantado de ayudarte."
            ),
        )
    if guardrail_result.get("redirected"):
        return KnowledgeQueryResponse(
            answer=(
                "¡Hola! Soy el asistente de soporte de Nexova. "
                "¿En qué puedo ayudarte hoy? Puedes consultarme sobre tickets, "
                "incidencias, tarifas, servicios o cualquier duda relacionada "
                "con tu soporte técnico."
            ),
            run_id="",
        )

    # ── Phase 3: Execute the knowledge graph ───────────────────────────────
    mcp_token = create_access_token(
        current_user.id,
        scopes=("incidents:read", "inventory:read"),
    )
    request_token = api_bearer_token.set(mcp_token)
    try:
        result = run_knowledge_graph(payload.question, mcp_token=mcp_token)
        if result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=result["error"],
            )
        return KnowledgeQueryResponse(answer=result["answer"], run_id=result["run_id"])
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Agent graph execution failed (%s)", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo completar la consulta del agente. Inténtalo de nuevo más tarde.",
        ) from error
    finally:
        api_bearer_token.reset(request_token)


def _handle_proposal(
    mem_svc,
    message: str,
    proposal_obj: dict,
    user_id: int,
) -> None:
    """
    Classify the *message* against the pending *proposal_obj* and act
    accordingly.

    Modifies the proposal lifecycle — never writes to Qdrant knowledge bases.
    """
    verdict, edited_content = MemoryClassifier.classify(message, proposal_obj)
    proposal_fact = (proposal_obj.get("fact") or proposal_obj)
    proposal_content = proposal_fact.get("content", "")

    if verdict == MemoryVerdict.APPROVED:
        fact_id = mem_svc.store_fact({
            **proposal_fact,
            "approved_by": user_id,
            "source_message": message,
        })
        mem_svc.clear_proposal()
        mem_svc.log_audit({
            "action": "approved",
            "user_id": user_id,
            "fact_id": fact_id,
            "detail": "Usuario aprobó propuesta de memoria.",
            "proposal_content": proposal_content,
        })
        logger.info("Memory proposal APPROVED by user %s → fact %s", user_id, fact_id)

    elif verdict == MemoryVerdict.REJECTED:
        mem_svc.clear_proposal()
        mem_svc.log_audit({
            "action": "rejected",
            "user_id": user_id,
            "fact_id": "",
            "detail": "Usuario rechazó propuesta de memoria.",
            "proposal_content": proposal_content,
        })
        logger.info("Memory proposal REJECTED by user %s", user_id)

    elif verdict == MemoryVerdict.EDITED and edited_content:
        corrected_fact = {**proposal_fact, "content": edited_content}
        fact_id = mem_svc.store_fact({
            **corrected_fact,
            "approved_by": user_id,
            "source_message": message,
        })
        mem_svc.clear_proposal()
        mem_svc.log_audit({
            "action": "edited",
            "user_id": user_id,
            "fact_id": fact_id,
            "detail": f"Usuario editó propuesta: {proposal_content!r} → {edited_content!r}",
            "proposal_content": proposal_content,
        })
        logger.info("Memory proposal EDITED by user %s → fact %s", user_id, fact_id)

    else:  # AMBIGUOUS
        mem_svc.clear_proposal()
        mem_svc.log_audit({
            "action": "discarded_ambiguous",
            "user_id": user_id,
            "fact_id": "",
            "detail": "Propuesta descartada por ambigüedad o cambio de tema.",
            "proposal_content": proposal_content,
        })
        logger.info("Memory proposal DISCARDED (ambiguous) by user %s", user_id)
