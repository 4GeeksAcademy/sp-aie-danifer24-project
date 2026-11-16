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

from data.pipelines.rag import generate_answer, retrieve
from services.api.models import IncidentBranch, IncidentCategory, IncidentOrigin, IncidentStatus
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

logger = logging.getLogger(__name__)

TRACE_DIR = Path(os.getenv("KNOWLEDGE_GRAPH_TRACE_DIR", "data/traces/knowledge_graph"))
_TRACE_LOCK = Lock()


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


# Explicit graph manifest validated before compilation.
_NODE_NAMES = {
    "receive_question", "route_request", "retrieve", "incident_lookup",
    "generate_answer", "no_context", "incident_response",
    "inventory_lookup", "inventory_response",
}
_TRANSITIONS = {
    START: {"receive_question"},
    "receive_question": {"route_request", END},
    "route_request": {"incident_lookup", "inventory_lookup", "retrieve"},
    "incident_lookup": {"incident_response"},
    "incident_response": {"retrieve", END},
    "inventory_lookup": {"inventory_response"},
    "inventory_response": {"retrieve", END},
    "retrieve": {"generate_answer", "no_context"},
    "generate_answer": {END},
    "no_context": {END},
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
        inventory_match = re.search(
            r"\b(?:stock|inventario|existencias|disponibilidad)\b.*?\b(?:de|del|para)\s+(.+)$",
            question,
            re.IGNORECASE,
        )
        sku_match = re.search(r"\bSKU\s*[:#]?\s*([\w-]+)", question, re.IGNORECASE)
        product_match = re.search(r"\bproducto\s*#?\s*(\d+)\b", question, re.IGNORECASE)
        incident_match = re.search(r"\b(?:ticket|incidencia|incidente)\s*#?\s*(\d+)\b", question, re.IGNORECASE)
        incident_lookup = None
        inventory_lookup = None

        if inventory_match or sku_match or product_match:
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

    def lookup_incident_node(state: KnowledgeGraphState) -> KnowledgeGraphState:
        outcome = incident_fn(state["incident_lookup"])
        records = [record.model_dump(mode="json") for record in outcome.incidents]
        return {
            "incident_result": outcome,
            "trace": _record(
                state, "incident_lookup", outcome=outcome.outcome.value,
                incident_count=len(records), incidents=records, message=outcome.message,
            ),
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

    def lookup_inventory_node(state: KnowledgeGraphState) -> KnowledgeGraphState:
        outcome = inventory_fn(state["inventory_lookup"])
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
        return {
            "chunks": chunks,
            "trace": _record(
                state,
                "retrieve",
                chunk_count=len(chunks),
                sources_used=["rag"],
                sources=sorted({chunk.get("source_document", "unknown") for chunk in chunks}),
                retrieved_chunks=[
                    {
                        "source_document": chunk.get("source_document"),
                        "section": chunk.get("section"),
                        "text": chunk.get("text"),
                    }
                    for chunk in chunks
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
        rag_answer = generate_fn(state["question"], state["chunks"])
        answer = _with_partial_answer(state, rag_answer)
        return {
            "answer": answer,
            "trace": _record(
                state,
                "generate_answer",
                answer=answer,
                rag_answer=rag_answer,
                sources_used=([state["active_tool"]] if state.get("active_tool") else []) + ["rag"],
                context_chunk_count=len(state["chunks"]),
            ),
        }

    def no_context(state: KnowledgeGraphState) -> KnowledgeGraphState:
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
        return "retrieve" if state.get("use_rag") else "finish"

    def route_after_question(state: KnowledgeGraphState) -> str:
        return "invalid" if state.get("error") else "route"

    def route_after_retrieval(state: KnowledgeGraphState) -> str:
        return "generate" if state.get("chunks") else "no_context"

    builder = StateGraph(KnowledgeGraphState)
    builder.add_node("receive_question", receive_question)
    builder.add_node("route_request", route_request)
    builder.add_node("incident_lookup", lookup_incident_node)
    builder.add_node("incident_response", incident_response)
    builder.add_node("inventory_lookup", lookup_inventory_node)
    builder.add_node("inventory_response", inventory_response)
    builder.add_node("retrieve", retrieve_context)
    builder.add_node("generate_answer", generate_response)
    builder.add_node("no_context", no_context)
    builder.add_edge(START, "receive_question")
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
            "retrieve": "retrieve",
        },
    )
    builder.add_edge("incident_lookup", "incident_response")
    builder.add_conditional_edges(
        "incident_response", route_after_tool,
        {"retrieve": "retrieve", "finish": END},
    )
    builder.add_edge("inventory_lookup", "inventory_response")
    builder.add_conditional_edges(
        "inventory_response", route_after_tool,
        {"retrieve": "retrieve", "finish": END},
    )
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieval,
        {"generate": "generate_answer", "no_context": "no_context"},
    )
    builder.add_edge("generate_answer", END)
    builder.add_edge("no_context", END)
    try:
        return builder.compile(checkpointer=checkpointer or MemorySaver())
    except Exception as exc:
        raise RuntimeError(f"Failed to compile knowledge LangGraph: {exc}") from exc


# Compile at application import/startup, before accepting any request.
knowledge_graph = build_knowledge_graph()


def _config(run_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


def run_knowledge_graph(question: str, *, run_id: str | None = None) -> KnowledgeGraphState:
    """Run with a per-node checkpoint; return answer, state and inspectable trace."""
    current_run_id = run_id or str(uuid4())
    logger.info("knowledge_graph_run_started %s", json.dumps({"run_id": current_run_id}))
    try:
        result = knowledge_graph.invoke(
            {"question": question, "run_id": current_run_id, "chunks": [], "trace": []},
            config=_config(current_run_id),
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
