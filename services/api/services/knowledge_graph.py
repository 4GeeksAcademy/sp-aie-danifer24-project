"""Compiled, checkpointed LangGraph workflow for grounded knowledge answers."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, TypedDict, get_type_hints
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from data.pipelines.rag import generate_answer, retrieve

logger = logging.getLogger(__name__)

TRACE_DIR = Path(os.getenv("KNOWLEDGE_GRAPH_TRACE_DIR", "data/traces/knowledge_graph"))
_TRACE_LOCK = Lock()


class KnowledgeGraphState(TypedDict, total=False):
    """Minimal state passed between nodes; conversation history is not needed."""

    question: str
    run_id: str
    chunks: list[dict[str, Any]]
    answer: str
    error: str
    trace: list[str]


# Explicit graph manifest validated before compilation.
_NODE_NAMES = {"receive_question", "retrieve", "generate_answer", "no_context"}
_TRANSITIONS = {
    START: {"receive_question"},
    "receive_question": {"retrieve", END},
    "retrieve": {"generate_answer", "no_context"},
    "generate_answer": {END},
    "no_context": {END},
}
_EXPECTED_STATE_TYPES = {
    "question": str,
    "run_id": str,
    "chunks": list[dict[str, Any]],
    "answer": str,
    "error": str,
    "trace": list[str],
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

    def retrieve_context(state: KnowledgeGraphState) -> KnowledgeGraphState:
        chunks = retrieve_fn(state["question"])
        return {
            "chunks": chunks,
            "trace": _record(
                state,
                "retrieve",
                chunk_count=len(chunks),
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

    def generate_response(state: KnowledgeGraphState) -> KnowledgeGraphState:
        answer = generate_fn(state["question"], state["chunks"])
        return {
            "answer": answer,
            "trace": _record(
                state,
                "generate_answer",
                answer=answer,
                context_chunk_count=len(state["chunks"]),
            ),
        }

    def no_context(state: KnowledgeGraphState) -> KnowledgeGraphState:
        answer = "No tengo información suficiente en la base de conocimiento para responder esa pregunta."
        return {
            "answer": answer,
            "trace": _record(state, "no_context", answer=answer, chunk_count=0),
        }

    def route_after_question(state: KnowledgeGraphState) -> str:
        return "invalid" if state.get("error") else "retrieve"

    def route_after_retrieval(state: KnowledgeGraphState) -> str:
        return "generate" if state.get("chunks") else "no_context"

    builder = StateGraph(KnowledgeGraphState)
    builder.add_node("receive_question", receive_question)
    builder.add_node("retrieve", retrieve_context)
    builder.add_node("generate_answer", generate_response)
    builder.add_node("no_context", no_context)
    builder.add_edge(START, "receive_question")
    builder.add_conditional_edges(
        "receive_question",
        route_after_question,
        {"invalid": END, "retrieve": "retrieve"},
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
