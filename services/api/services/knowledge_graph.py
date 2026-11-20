"""Compiled, checkpointed LangGraph workflow for grounded knowledge answers."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, NotRequired, TypedDict, get_type_hints
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from data.pipelines.rag import generate_answer, retrieve
from services.api.models import IncidentBranch, IncidentCategory, IncidentOrigin, IncidentStatus
from services.api.services.agent_memory import get_memory_service
from services.api.services.harness import post_generation_guardrails, post_rag_guardrails
from services.api.services.system_prompt import build_secure_prompt
from mcps.nexova_mcp.request_context import api_bearer_token

# ── Tool provider selection ──────────────────────────────────────────────
# When USE_MCP_BACKEND is truthy, the agent routes incident and inventory
# lookups through the MCP Server instead of hitting databases directly.
_USE_MCP_BACKEND = os.environ.get("USE_MCP_BACKEND", "").lower() in ("1", "true", "yes")

if _USE_MCP_BACKEND:
    from services.api.services.incident_tool import (
        IncidentLookupInput,
        IncidentLookupOutput,
        IncidentToolOutcome,
    )
    from services.api.services.inventory_tool import (
        InventoryLookupInput,
        InventoryLookupOutput,
        InventoryToolOutcome,
    )
    from services.api.services.mcp_agent_adapter import (
        lookup_incidents_mcp as lookup_incidents,
        lookup_inventory_mcp as lookup_inventory,
    )
else:
    from services.api.services.incident_tool import (
        IncidentLookupInput,
        IncidentLookupOutput,
        IncidentToolOutcome,
        lookup_incidents,
    )
    from services.api.services.inventory_tool import (
        InventoryLookupInput,
        InventoryLookupOutput,
        InventoryToolOutcome,
        lookup_inventory,
    )
# ─────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

TRACE_DIR = Path(os.getenv("KNOWLEDGE_GRAPH_TRACE_DIR", "data/traces/knowledge_graph"))
_TRACE_LOCK = Lock()


class KnowledgeGraphContext(TypedDict, total=False):
    """Execution-scoped secrets passed separately from checkpointed graph state."""

    mcp_token: str


class KnowledgeGraphState(TypedDict, total=False):
    """Minimal state passed between nodes; conversation history is not needed."""

    question: str
    run_id: str
    chunks: list[dict[str, Any]]
    trace: list[str]
    answer: NotRequired[str]
    partial_answer: NotRequired[str]
    error: NotRequired[str]
    incident_lookup: NotRequired[IncidentLookupInput | None]
    incident_result: NotRequired[IncidentLookupOutput]
    inventory_lookup: NotRequired[InventoryLookupInput | None]
    inventory_result: NotRequired[InventoryLookupOutput]
    route: NotRequired[str]
    active_tool: NotRequired[str | None]
    use_rag: NotRequired[bool]
    memory_proposal: NotRequired[dict[str, Any] | None]


# Explicit graph manifest validated before compilation.
_NODE_NAMES = {
    "receive_question", "route_request", "retrieve", "incident_lookup",
    "generate_answer", "no_context", "incident_response",
    "inventory_lookup", "inventory_response", "reject_inventory_write",
    "evaluate_memory",
}
_TRANSITIONS = {
    START: {"receive_question"},
    "receive_question": {"route_request", END},  # error → END directly
    "route_request": {"incident_lookup", "inventory_lookup", "reject_inventory_write", "retrieve"},
    "incident_lookup": {"incident_response"},
    "incident_response": {"retrieve", "evaluate_memory"},
    "inventory_lookup": {"inventory_response"},
    "inventory_response": {"retrieve", "evaluate_memory"},
    "reject_inventory_write": {"evaluate_memory"},
    "retrieve": {"generate_answer", "no_context"},
    "generate_answer": {"evaluate_memory"},
    "no_context": {"evaluate_memory"},
    "evaluate_memory": {END},
}
_EXPECTED_STATE_TYPES = {
    "question": str,
    "run_id": str,
    "chunks": list[dict[str, Any]],
    "trace": list[str],
    "answer": str,
    "partial_answer": str,
    "error": str,
    "route": str,
    "active_tool": str | None,
    "use_rag": bool,
    "incident_lookup": IncidentLookupInput | None,
    "incident_result": IncidentLookupOutput,
    "inventory_lookup": InventoryLookupInput | None,
    "inventory_result": InventoryLookupOutput,
    "memory_proposal": dict[str, Any] | None,
}


def _validate_graph_definition() -> None:
    hints = get_type_hints(KnowledgeGraphState)
    missing = _EXPECTED_STATE_TYPES.keys() - hints.keys()
    extra = hints.keys() - _EXPECTED_STATE_TYPES.keys()
    mistyped = {
        key: (hints[key], expected)
        for key, expected in _EXPECTED_STATE_TYPES.items()
        if key in hints and hints[key] != expected
    }
    if missing or extra or mistyped:
        raise ValueError(
            "Knowledge graph state schema mismatch; "
            f"missing={sorted(missing)}, unexpected={sorted(extra)}, "
            f"mistyped={mistyped}"
        )
    referenced = set().union(*_TRANSITIONS.values()) - {START, END}
    if referenced != _NODE_NAMES:
        raise ValueError(
            "Knowledge graph edge/node mismatch; "
            f"unreferenced nodes={sorted(_NODE_NAMES - referenced)}, "
            f"unknown targets={sorted(referenced - _NODE_NAMES)}"
        )
    for node, targets in _TRANSITIONS.items():
        if not targets:
            raise ValueError(f"Knowledge graph node {node!r} has no outgoing edge")

    reachable = {START}
    frontier = [START]
    while frontier:
        current = frontier.pop()
        if current in {START, END}:
            targets = _TRANSITIONS.get(current, set())
        else:
            targets = _TRANSITIONS[current]
        for target in targets:
            if target not in reachable:
                reachable.add(target)
                if target not in {START, END}:
                    frontier.append(target)
    unreachable = _NODE_NAMES - reachable
    if unreachable:
        raise ValueError(f"Unreachable knowledge graph nodes: {sorted(unreachable)}")


def _trace_path(run_id: str) -> Path:
    if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
        raise ValueError("Invalid knowledge graph run_id for trace storage")
    return TRACE_DIR / f"{run_id}.jsonl"


def _write_trace_event(state: KnowledgeGraphState, node: str, **details: Any) -> None:
    event = {
        "run_id": state["run_id"],
        "node": node,
        "sequence": len(state.get("trace", [])) + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **details,
    }
    line = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
    logger.info("knowledge_graph_trace %s", line)
    with _TRACE_LOCK:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        trace_path = _trace_path(state["run_id"])
        with trace_path.open("a", encoding="utf-8") as trace_file:
            trace_file.write(line + "\n")


def _record(state: KnowledgeGraphState, node: str, **details: Any) -> list[str]:
    _write_trace_event(state, node, **details)
    return [*state.get("trace", []), node]


def build_knowledge_graph(
    retrieve_fn: Callable[..., list[dict[str, Any]]] = retrieve,
    generate_fn: Callable[..., str] = generate_answer,
    *,
    incident_fn: Callable[[IncidentLookupInput], IncidentLookupOutput] = lookup_incidents,
    inventory_fn: Callable[[InventoryLookupInput], InventoryLookupOutput] = lookup_inventory,
    checkpointer: Any | None = None,
):
    """Validate and compile; structural errors fail before graph invocation."""
    _validate_graph_definition()

    def receive_question(state: KnowledgeGraphState) -> KnowledgeGraphState:
        question = state.get("question", "").strip()
        if not question:
            error = "La pregunta no puede estar vacía."
            return {
                "question": question,
                "error": error,
                "answer": "",
                "chunks": [],
                "trace": _record(state, "receive_question", valid=False, error=error),
            }
        return {
            "question": question,
            "chunks": [],
            "trace": _record(
                state, "receive_question", valid=True, question=question
            ),
        }

    def route_request(state: KnowledgeGraphState) -> KnowledgeGraphState:
        # Product stock/name/SKU queries route to live inventory; ticket lookups
        # route to incidents; business policy questions continue through RAG.
        question = state["question"]
        write_match = re.search(
            r"\b(crear|crea|creación|añadir|añade|agregar|agrega|actualizar|actualiza|modificar|modifica|cambiar|cambia|eliminar|elimina|borrar|borra|delete|create|update|modify|remove)\b",
            question,
            re.IGNORECASE,
        )
        inventory_context = re.search(
            r"\b(producto|inventario|stock|existencias|SKU|art[ií]culo)\b",
            question,
            re.IGNORECASE,
        )
        inventory_write = bool(write_match and inventory_context)
        inventory_match = re.search(
            r"\b(?:stock|inventario|existencias|disponibilidad)\b.*?\b(?:de|del|para)\s+(.+)$",
            question,
            re.IGNORECASE,
        )
        sku_match = re.search(r"\b(?:SKU\s*[:#]?\s*|(?:producto|art[ií]culo)\s+)([\w-]+)", question, re.IGNORECASE)
        product_match = re.search(r"\bproducto\s*#?\s*(\d+)\b", question, re.IGNORECASE)
        incident_match = re.search(
            r"\b(?:ticket|incidencia|incidente)\s*#?\s*(\d+)\b",
            question,
            re.IGNORECASE,
        )
        # Recognise natural formulations such as “qué incidente tiene el ID 1”.
        # Restrict this fallback to incident-related questions so unrelated IDs
        # are not routed to the Incidents Manager.
        if incident_match is None and re.search(
            r"\b(?:ticket|incidencia|incidente)s?\b", question, re.IGNORECASE
        ):
            incident_match = re.search(
                r"\b(?:id|identificador|n[uú]?mero)\s*#?\s*(\d+)\b",
                question,
                re.IGNORECASE,
            )
        incident_lookup = None
        inventory_lookup = None

        if inventory_write:
            route = "reject_inventory_write"
        elif inventory_match or sku_match or product_match:
            if product_match:
                inventory_lookup = InventoryLookupInput(product_id=int(product_match.group(1)))
            elif sku_match:
                inventory_lookup = InventoryLookupInput(sku=sku_match.group(1))
            else:
                product_name = inventory_match.group(1).strip(" ?.!\"'")
                # Do not pass the second, RAG-oriented clause as part of the
                # product name in mixed-source questions.
                product_name = re.split(
                    r"\s+(?:y|e)\s+(?=(?:cu[aá]l|cu[aá]nto|qu[eé]|c[oó]mo|por qu[eé])\b)",
                    product_name,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0].strip()
                product_name = re.sub(r"^(?:producto|artículo)\s+", "", product_name, flags=re.IGNORECASE)
                inventory_lookup = InventoryLookupInput(name=product_name)
            route = "inventory_lookup"
        elif incident_match:
            incident_lookup = IncidentLookupInput(ticket_id=int(incident_match.group(1)))
            route = "incident_lookup"
        elif re.search(r"\b(incidencias|incidentes|tickets)\b", question, re.IGNORECASE):
            question_lower = question.casefold()
            incident_lookup = IncidentLookupInput(
                status=next((value for value in IncidentStatus if value.value in question_lower), None),
                category=next((value for value in IncidentCategory if value.value in question_lower), None),
                origin=next((value for value in IncidentOrigin if value.value in question_lower), None),
                branch=next((value for value in IncidentBranch if value.value in question_lower), None),
            )
            route = "incident_lookup" if any((
                incident_lookup.status, incident_lookup.category,
                incident_lookup.origin, incident_lookup.branch,
            )) else "retrieve"
            if route == "retrieve":
                incident_lookup = None
        else:
            route = "retrieve"

        rag_intent = bool(re.search(
            r"\b(pol[ií]tica|procedimiento|contrato|documentaci[oó]n|seg[uú]n|c[oó]mo|por qu[eé]|requisito|tarifa|precio|condiciones)\b",
            question,
            re.IGNORECASE,
        ))
        active_tool = (
            "incident_lookup" if incident_lookup is not None
            else "inventory_lookup" if inventory_lookup is not None
            else "reject_inventory_write" if inventory_write
            else None
        )
        use_rag = route == "retrieve" or rag_intent
        sources = ([active_tool] if active_tool else []) + (["rag"] if use_rag else [])
        return {
            "incident_lookup": incident_lookup,
            "inventory_lookup": inventory_lookup,
            "active_tool": active_tool,
            "use_rag": use_rag,
            "route": route,
            "trace": _record(
                state,
                "route_request",
                route=route,
                sources=sources,
                execution_order=(
                    [active_tool, "rag"] if active_tool and use_rag
                    else sources
                ),
                ticket_id=incident_lookup.ticket_id if incident_lookup else None,
                product_id=inventory_lookup.product_id if inventory_lookup else None,
                sku=inventory_lookup.sku if inventory_lookup else None,
                product_name=inventory_lookup.name if inventory_lookup else None,
            ),
        }

    def lookup_incident_node(
        state: KnowledgeGraphState, runtime: Runtime[KnowledgeGraphContext]
    ) -> KnowledgeGraphState:
        mcp_token = (runtime.context or {}).get("mcp_token")
        token_context = api_bearer_token.set(mcp_token) if mcp_token else None
        try:
            outcome = incident_fn(state["incident_lookup"], token=mcp_token)
        finally:
            if token_context is not None:
                api_bearer_token.reset(token_context)
        records = [record.model_dump(mode="json") for record in outcome.incidents]
        return {
            "incident_result": outcome,
            "trace": _record(
                state, "incident_lookup", outcome=outcome.outcome.value,
                incident_count=len(records), incidents=records, message=outcome.message,
            ),
        }

    def reject_inventory_write_node(
        state: KnowledgeGraphState, runtime: Runtime[KnowledgeGraphContext]
    ) -> KnowledgeGraphState:
        from mcps.nexova_mcp.mcp_client import NexovaMCPClient

        mcp_token = (runtime.context or {}).get("mcp_token") or api_bearer_token.get()
        question = state["question"].casefold()
        operation = (
            "delete" if re.search(r"\b(elimina|eliminar|borra|borrar|quita|quitar|delete|remove)\b", question)
            else "update" if re.search(r"\b(actualiza|actualizar|modifica|modificar|cambia|cambiar|update|modify)\b", question)
            else "create"
        )
        result = NexovaMCPClient(server_url=os.environ.get("MCP_SERVER_URL", "http://mcp:8010/sse"), token=mcp_token).reject_inventory_write(
            operation=operation,
        )
        return {
            "answer": result.get(
                "message",
                "El inventario es de solo lectura; no se permiten operaciones de escritura.",
            ),
            "trace": _record(state, "reject_inventory_write", outcome=result.get("outcome"), error=result.get("error"), message=result.get("message")),
        }

    def incident_response(state: KnowledgeGraphState) -> KnowledgeGraphState:
        outcome = state["incident_result"]
        if outcome.outcome == IncidentToolOutcome.FOUND:
            lines = [
                f"Incidencia {record.id}: estado {record.status.value}, "
                f"categoría {record.category.value}, origen {record.origin.value}, "
                f"creada {record.created_at.isoformat()}, actualizada {record.updated_at.isoformat()}."
                for record in outcome.incidents
            ]
            answer = "\n".join(lines)
        else:
            answer = (
                "No pude confirmar el estado de ese ticket ahora mismo."
                if outcome.outcome == IncidentToolOutcome.ERROR
                else "No se encontró una incidencia que coincida con la consulta."
            )
        return {
            "answer": answer,
            "partial_answer": answer,
            "trace": _record(
                state,
                "incident_response",
                answer=answer,
                sources_used=["incident_lookup"],
            ),
        }

    def lookup_inventory_node(
        state: KnowledgeGraphState, runtime: Runtime[KnowledgeGraphContext]
    ) -> KnowledgeGraphState:
        mcp_token = (runtime.context or {}).get("mcp_token")
        token_context = api_bearer_token.set(mcp_token) if mcp_token else None
        try:
            outcome = inventory_fn(state["inventory_lookup"], token=mcp_token)
        finally:
            if token_context is not None:
                api_bearer_token.reset(token_context)
        products = [product.model_dump(mode="json") for product in outcome.products]
        return {
            "inventory_result": outcome,
            "trace": _record(
                state,
                "inventory_lookup",
                outcome=outcome.outcome.value,
                product_count=len(products),
                products=products,
                message=outcome.message,
            ),
        }

    def inventory_response(state: KnowledgeGraphState) -> KnowledgeGraphState:
        outcome = state["inventory_result"]
        if outcome.outcome == InventoryToolOutcome.FOUND:
            answer = "\n".join(
                f"{product.name} (SKU {product.sku}): {product.current_stock} unidades disponibles."
                for product in outcome.products
            )
        elif outcome.outcome == InventoryToolOutcome.NOT_FOUND:
            answer = "No encontré un producto que coincida con la consulta."
        else:
            answer = "No pude confirmar el stock del producto ahora mismo."
        return {
            "answer": answer,
            "partial_answer": answer,
            "trace": _record(
                state,
                "inventory_response",
                answer=answer,
                sources_used=["inventory_lookup"],
            ),
        }

    def retrieve_context(state: KnowledgeGraphState) -> KnowledgeGraphState:
        chunks = retrieve_fn(state["question"])

        # Guardrail: filtrar fragmentos RAG con instrucciones enmascaradas
        safe_chunks, rag_verdicts = post_rag_guardrails(chunks)
        filtered_count = len(chunks) - len(safe_chunks)
        if filtered_count:
            logger.warning(
                "GUARDRAIL_RAG_FILTER: removed %d/%d chunks with masked instructions",
                filtered_count, len(chunks),
            )

        return {
            "chunks": safe_chunks,
            "trace": _record(
                state,
                "retrieve",
                chunk_count=len(safe_chunks),
                filtered_count=filtered_count,
                rag_guardrails=rag_verdicts,
                sources_used=["rag"],
                sources=sorted({chunk.get("source_document", "unknown") for chunk in safe_chunks}),
                retrieved_chunks=[
                    {
                        "source_document": chunk.get("source_document"),
                        "section": chunk.get("section"),
                        "text": chunk.get("text"),
                    }
                    for chunk in safe_chunks
                ],
            ),
        }

    def _with_partial_answer(state: KnowledgeGraphState, rag_answer: str) -> str:
        partial = state.get("partial_answer")
        if not partial:
            return rag_answer
        if rag_answer.startswith("No tengo información suficiente"):
            return f"{partial}\n\n{rag_answer}"
        return f"{partial}\n\n{rag_answer}"

    def generate_response(state: KnowledgeGraphState) -> KnowledgeGraphState:
        # Usar system prompt seguro con separacion instrucciones/contexto/input
        secure_prompt = build_secure_prompt(state["question"], state["chunks"])
        rag_answer = generate_fn(secure_prompt, state["chunks"])
        answer = _with_partial_answer(state, rag_answer)

        # Guardrail post-generacion: detectar datos sensibles en la respuesta
        post_guardrail = post_generation_guardrails(answer, question=state.get("question", ""))
        safe_answer = post_guardrail["safe_answer"]

        return {
            "answer": safe_answer,
            "trace": _record(
                state,
                "generate_answer",
                answer=safe_answer,
                blocked=post_guardrail["blocked"],
                block_reason=post_guardrail.get("block_reason") or "",
                was_redirected=post_guardrail.get("was_redirected", False),
                rag_answer=rag_answer,
                guardrails=post_guardrail["verdicts"],
                sources_used=([state["active_tool"]] if state.get("active_tool") else []) + ["rag"],
                context_chunk_count=len(state["chunks"]),
            ),
        }

    _OUT_OF_DOMAIN_PATTERNS = re.compile(
        r"\b(?:clima|tiempo\s+(?:meterol|atmosf)|pron[oó]stico|"
        r"temperatura|lluvia|soleado|nublado|viento|"
        r"hora\s+(?:actual|es|exacta)|qu[eé]\s+hora\s+(?:es|tengo)|"
        r"fecha|d[ií]a\s+(?:de\s+hoy|actual|es)|qu[eé]\s+d[ií]a\s+es\s+hoy|"
        r"noticia|deporte|f[uú]tbol|b[eé]isbol|baloncesto|"
        r"receta|cocinar|pel[ií]cula|canci[oó]n|c[oó]mo\s+(?:est[áa]\s+el|est[aá]n|se\s+)|"
        r"qu[eé]\s+(?:significa|es)\s+)"
        r"(?!.*(?:ticket|incidencia|soporte|tarifa|procedimiento|contrato|pol[ií]tica|FAQ|reembolso))",
        re.IGNORECASE,
    )

    def no_context(state: KnowledgeGraphState) -> KnowledgeGraphState:
        question = state.get("question", "")
        # Si la pregunta es fuera de dominio (clima, hora, etc.), pasar por el LLM
        # para que el system prompt redirija al proposito de soporte.
        if _OUT_OF_DOMAIN_PATTERNS.search(question):
            secure_prompt = build_secure_prompt(question, [])
            rag_answer = generate_fn(secure_prompt, [])
        else:
            rag_answer = "No tengo información suficiente en la base de conocimiento para responder esa pregunta."
        answer = _with_partial_answer(state, rag_answer)
        return {
            "answer": answer,
            "trace": _record(
                state,
                "no_context",
                answer=answer,
                chunk_count=0,
                sources_used=([state["active_tool"]] if state.get("active_tool") else []) + ["rag"],
            ),
        }

    def route_after_tool(state: KnowledgeGraphState) -> str:
            return "retrieve" if state.get("use_rag") else "evaluate_memory"

    def route_after_question(state: KnowledgeGraphState) -> str:
        return "invalid" if state.get("error") else "route"

    def evaluate_memory_node(state: KnowledgeGraphState) -> KnowledgeGraphState:
        """
        After an answer is ready, evaluate whether the interaction contains
        memorizable content and, if so, create a pending proposal.

        Criteria (from CONTEXT.md):
        - Corrected escalation procedures
        - Recurrent client preferences
        - Known incident patterns

        Never creates a proposal if one is already pending.
        Never writes to Qdrant ``*_knowledge`` collections.
        """
        answer = state.get("answer", "")
        question = state.get("question", "")
        if not answer or not question:
            return {"trace": _record(state, "evaluate_memory", proposal_created=False, reason="no_content")}

        # ── Memorizability heuristics ──────────────────────────────────────
        answer_lower = answer.casefold()
        question_lower = question.casefold()

        # Check for escalation/correction patterns
        has_escalation = bool(re.search(
            r"\b(escalaci[óo]n|escalar|reasignaci[óo]n|reasignar|derivar|transferir|redirigir)\b",
            answer_lower,
        ))
        has_sla_change = bool(re.search(
            r"\b(SLA|acuerdo\s+de\s+nivel|tiempo\s+de\s+resoluci[óo]n|plazo)\b",
            answer_lower,
        ))
        has_preference = bool(re.search(
            r"\b(siempre\s+prefiere|preferencia|suele|habitualmente|normalmente)\b",
            answer_lower,
        ))
        has_pattern = bool(re.search(
            r"\b(suele[n]?\s+(?:ir|pasar|ocurrir|resolverse)|patr[oó]n|t[ií]pico|frecuente|recurrente)\b",
            answer_lower,
        ))
        has_client_ref = bool(re.search(
            r"\b(cliente|cuenta|contrato)\b", answer_lower,
        ))

        # Combined heuristic: at least two signals or one strong signal
        signals = sum([has_escalation, has_sla_change, has_preference, has_pattern, has_client_ref])
        strong_signal = has_escalation or has_sla_change or (has_preference and has_client_ref)

        if not (signals >= 2 or strong_signal):
            return {"trace": _record(
                state, "evaluate_memory",
                proposal_created=False,
                reason="not_valuable",
                signals=signals,
                strong_signal=strong_signal,
            )}

        # ── Build proposal fact ────────────────────────────────────────────
        # Extract entity if identifiable
        entity = _extract_entity(answer)
        fact_type = (
            "escalation" if has_escalation or has_sla_change
            else "preference" if has_preference
            else "pattern"
        )
        # Use the original answer as the fact content (will be reviewed)
        content = _extract_memorizable_content(answer)

        if not content:
            return {"trace": _record(
                state, "evaluate_memory",
                proposal_created=False, reason="content_empty",
            )}

        fact = {
            "type": fact_type,
            "content": content,
            "entity": entity,
        }

        # ── Check for existing proposal ── (singleton enforcement)
        try:
            mem_svc = get_memory_service()
            if mem_svc.has_proposal():
                return {"trace": _record(
                    state, "evaluate_memory",
                    proposal_created=False, reason="already_pending",
                )}
            mem_svc.set_proposal(fact, source_run_id=state.get("run_id", ""))
        except Exception as exc:
            logger.warning("AgentMemory set_proposal failed: %s", exc)
            return {"trace": _record(
                state, "evaluate_memory",
                proposal_created=False, reason="redis_error",
            )}

        # Append the proposal message to the answer
        proposal_suffix = (
            f"\n\n---\n*He registrado que {content}*"
            f"\n¿Quieres que lo recuerde para futuras conversaciones? "
            "(responde 'sí' para guardarlo, 'no' para descartarlo o corrígelo si no es exacto.)"
        )
        updated_answer = answer + proposal_suffix

        return {
            "answer": updated_answer,
            "memory_proposal": fact,
            "trace": _record(
                state, "evaluate_memory",
                proposal_created=True,
                fact_type=fact_type,
                entity=entity,
                content=content,
            ),
        }

    # ── Helper: extract a concise entity reference ─────────────────────
    def _extract_entity(text: str) -> str:
        """Try to extract a business entity (client name, ticket type, category)."""
        # Look for "cliente de <...>", "clientes <...>"
        client_match = re.search(
            r"\b(?:cliente[s]?\s+(?:de\s+)?|clientes\s+)(\w+(?:\s+\w+)?)",
            text, re.IGNORECASE,
        )
        if client_match:
            return client_match.group(1).strip().rstrip(".,;")

        # Look for "tickets de <...>"
        ticket_match = re.search(
            r"\b(?:tickets|incidencias|incidentes)\s+(?:de|para)\s+(\w+(?:\s+\w+)?)",
            text, re.IGNORECASE,
        )
        if ticket_match:
            return ticket_match.group(1).strip().rstrip(".,;")
        return ""

    def _extract_memorizable_content(text: str) -> str:
        """
        Extract the most relevant sentence(s) for the memory fact.
        Prefer sentences containing escalation, preference or pattern keywords.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        candidates = []
        for sentence in sentences:
            if re.search(
                r"\b(?:escalaci[oó]n|SLA|prefiere|siempre|suele|t[ií]pico|patr[oó]n|"
                r"cambi[oó]|nuevo|actualizado|directo|resuelve)\b",
                sentence, re.IGNORECASE,
            ):
                candidates.append(sentence.strip())
        if candidates:
            return " ".join(candidates[:2])
        # Fallback: first substantive sentence
        for s in sentences:
            cleaned = s.strip()
            if len(cleaned) > 20:
                return cleaned
        return text[:200]

    def route_after_retrieval(state: KnowledgeGraphState) -> str:
        return "generate" if state.get("chunks") else "no_context"

    builder = StateGraph(KnowledgeGraphState, context_schema=KnowledgeGraphContext)
    builder.add_node("receive_question", receive_question)
    builder.add_node("route_request", route_request)
    builder.add_node("incident_lookup", lookup_incident_node)
    builder.add_node("incident_response", incident_response)
    builder.add_node("inventory_lookup", lookup_inventory_node)
    builder.add_node("inventory_response", inventory_response)
    builder.add_node("reject_inventory_write", reject_inventory_write_node)
    builder.add_node("retrieve", retrieve_context)
    builder.add_node("generate_answer", generate_response)
    builder.add_node("no_context", no_context)
    builder.add_node("evaluate_memory", evaluate_memory_node)
    builder.add_edge(START, 'receive_question')
    builder.add_conditional_edges(
        "receive_question",
        route_after_question,
        {"invalid": END, "route": "route_request"},
    )
    builder.add_conditional_edges(
        "route_request",
        lambda state: state["route"],
        {
            "incident_lookup": "incident_lookup",
            "inventory_lookup": "inventory_lookup",
            "reject_inventory_write": "reject_inventory_write",
            "retrieve": "retrieve",
        },
    )
    builder.add_edge("incident_lookup", "incident_response")
    builder.add_conditional_edges(
        "incident_response", route_after_tool,
            {"retrieve": "retrieve", "evaluate_memory": "evaluate_memory"},
    )
    builder.add_edge("inventory_lookup", "inventory_response")
    builder.add_edge("reject_inventory_write", "evaluate_memory")
    builder.add_conditional_edges(
        "inventory_response", route_after_tool,
            {"retrieve": "retrieve", "evaluate_memory": "evaluate_memory"},
    )
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieval,
        {"generate": "generate_answer", "no_context": "no_context"},
    )
    builder.add_edge("generate_answer", "evaluate_memory")
    builder.add_edge("no_context", "evaluate_memory")
    builder.add_edge("evaluate_memory", END)
    try:
        return builder.compile(checkpointer=checkpointer or MemorySaver())
    except Exception as exc:
        raise RuntimeError(f"Failed to compile knowledge LangGraph: {exc}") from exc


# Compile at application import/startup, before accepting any request.
knowledge_graph = build_knowledge_graph()


def _config(run_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


def run_knowledge_graph(
    question: str, *, run_id: str | None = None, mcp_token: str | None = None
) -> KnowledgeGraphState:
    """Run with a per-node checkpoint; return answer, state and inspectable trace."""
    current_run_id = run_id or str(uuid4())
    logger.info("knowledge_graph_run_started %s", json.dumps({"run_id": current_run_id}))
    try:
        result = knowledge_graph.invoke(
            {"question": question, "run_id": current_run_id, "chunks": [], "trace": []},
            config=_config(current_run_id),
            context={"mcp_token": mcp_token} if mcp_token else {},
        )
    except Exception as exc:
        _write_trace_event(
            {"run_id": current_run_id, "trace": []},
            "run_error",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    logger.info(
        "knowledge_graph_run_completed %s",
        json.dumps({"run_id": current_run_id, "trace": result.get("trace", [])}),
    )
    return result


def read_knowledge_graph_trace(run_id: str) -> list[dict[str, Any]]:
    """Read the persisted, ordered JSONL trace for a completed or active run."""
    trace_path = _trace_path(run_id)
    if not trace_path.exists():
        return []
    with _TRACE_LOCK, trace_path.open("r", encoding="utf-8") as trace_file:
        return [json.loads(line) for line in trace_file if line.strip()]


def inspect_knowledge_graph_run(run_id: str) -> list[Any]:
    """Return saved checkpoint snapshots, newest first, for a graph run."""
    return list(knowledge_graph.get_state_history(_config(run_id)))


def resume_knowledge_graph(run_id: str) -> KnowledgeGraphState:
    """Resume pending graph execution from the latest checkpoint for its thread."""
    snapshots = inspect_knowledge_graph_run(run_id)
    if not snapshots:
        raise ValueError(f"No checkpoints found for knowledge graph run {run_id!r}")
    if not snapshots[0].next:
        raise ValueError(f"Knowledge graph run {run_id!r} has no pending work to resume")
    return knowledge_graph.invoke(None, config=_config(run_id))
