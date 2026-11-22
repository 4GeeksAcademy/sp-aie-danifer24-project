"""
RFP Intake Pipeline — Part 1: Classification, metadata extraction, readability score,
department routing & per-department key-aspect extraction.

Orchestration pattern:
  orchestrator (router) → worker(s) → synthesizer

This lives in services/ (same pattern as knowledge_graph.py) because data/pipelines/
is not part of the importable runtime; the data/pipelines/rfp_intake/ directory
exists as the documentary home for pipeline specs and config files.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, NotRequired, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, select

from services.api.database import engine
from services.api.models import (
    ApprovalStatus,
    DepartmentSection,
    RFPMetadata,
    Ticket,
    TicketStatus,
)

logger = logging.getLogger(__name__)

# ── State schema ────────────────────────────────────────────────────────


class RFPIntakeState(TypedDict, total=False):
    """State passed between RFP intake pipeline nodes."""

    ticket_id: str
    markdown: str
    is_valid_rfp: bool
    classification_reason: str
    metadata: dict[str, Any]
    worker_inputs: dict[str, Any]
    departments_needed: list[str]
    department_sections: dict[str, Any]
    sales_summary: str | None
    handoff_payload: dict[str, Any] | None
    rfp_id: str | None
    ticket_status: str | None
    error: str | None


# ── Constants ──────────────────────────────────────────────────────────

_DEPARTMENTS = {
    "seleccion": {
        "name": "Talent Selection Operations",
        "responsible": "Javier Almeida",
    },
    "capacitacion": {
        "name": "Corporate Training",
        "responsible": "Elena Vargas",
    },
    "soporte": {
        "name": "Customer Support (outsourcing)",
        "responsible": "Roberto Díaz",
    },
}

# Keywords that hint which department(s) a service request maps to
_SERVICE_DEPT_MAP: list[tuple[frozenset[str], str]] = [
    (frozenset({
        "headhunting", "executive search", "seleccion", "rol", "perfil",
        "ejecutivo", "mando", "directivo", "recruitment", "hiring",
        "vacante", "candidato", "talento", "staffing", "placement",
        "busqueda", "contratacion", "reclutamiento",
    }), "seleccion"),
    (frozenset({
        "training", "capacitacion", "formacion", "curso", "taller",
        "workshop", "entrenamiento", "leadership", "liderazgo",
        "mentoria", "coaching", "upskilling", "reskilling",
        "aprendizaje", "desarrollo profesional",
    }), "capacitacion"),
    (frozenset({
        "support", "soporte", "agente", "agentes", "call center",
        "mesa de ayuda", "helpdesk", "help desk", "atencion al cliente",
        "customer service", "outsourcing", "bpo", "24/7", "sla",
        "servicio al cliente", "contact center", "service desk",
    }), "soporte"),
]


def _new_id() -> str:
    return str(uuid4())


def _client_hq_currency(hq: str) -> str:
    """Map client headquarters to proposal currency (business rule §5)."""
    hq_lower = hq.lower().strip()
    if "miami" in hq_lower or "usa" in hq_lower or "eeuu" in hq_lower:
        return "USD"
    return "EUR"


def _detect_departments(services_requested: list[str]) -> list[str]:
    """Classify which departments are needed based on requested services."""
    needed: set[str] = set()
    text = " ".join(services_requested).lower()
    for keywords, dept in _SERVICE_DEPT_MAP:
        if any(kw in text for kw in keywords):
            needed.add(dept)
    return sorted(needed) if needed else ["seleccion"]


def _calculate_readability(text: str) -> dict[str, float | int]:
    """Calculate readability metrics if enough content exists."""
    try:
        import readability as _readability  # type: ignore[import-unidentified]
    except ImportError:
        logger.warning("py-readability-metrics not available; skipping readability")
        return {}
    words = text.split()
    word_count = len(words)
    try:
        r = _readability.Readability(text)
        flesch_score = r.flesch()
        fog_score = r.gunning_fog()
        return {
            "flesch": round(float(flesch_score.score), 2),
            "gunning_fog": round(float(fog_score.score), 2),
            "word_count": word_count,
        }
    except Exception as exc:
        logger.warning("Readability calculation failed: %s", exc)
        return {"word_count": word_count}


def _update_ticket_status(
    session: Session,
    ticket_id: str,
    status: TicketStatus,
    error_message: str | None = None,
) -> None:
    ticket = session.exec(
        select(Ticket).where(Ticket.ticket_id == ticket_id)
    ).first()
    if ticket:
        ticket.status = status
        ticket.updated_at = datetime.now(timezone.utc)
        if error_message:
            ticket.error_message = error_message
        session.commit()


# ── Pipeline nodes ─────────────────────────────────────


# This file contains ONLY the replacement text for step 2.
# It will be read and spliced into rfp_intake.py by step2_apply.py.

_DEPARTMENT_WORKER_PROMPTS = {
    "seleccion": (
        "Eres un agente de Talento y Seleccion de Nexova.\\n"
        "Revisa el extracto de la RFP del cliente y extrae ASPECTOS CLAVE.\\n\\n"
        "Cliente: {client_name}\\n"
        "Servicios solicitados: {services}\\n\\n"
        "Extrae SOLO informacion explicita. No inventes cifras.\\n\\n"
        "Devuelve JSON con: roles_to_cover, estimated_close_time,\\n"
        "consulting_hours, key_aspects, open_questions"
    ),
    "capacitacion": (
        "Eres un agente de Capacitacion Corporativa de Nexova.\\n"
        "Revisa el extracto de la RFP del cliente y extrae ASPECTOS CLAVE.\\n\\n"
        "Cliente: {client_name}\\n"
        "Servicios solicitados: {services}\\n\\n"
        "Extrae SOLO informacion explicita. No inventes cifras.\\n\\n"
        "Devuelve JSON con: applicable_programs, duration, modality,\\n"
        "key_aspects, open_questions"
    ),
    "soporte": (
        "Eres un agente de Soporte al Cliente de Nexova.\\n"
        "Revisa el extracto de la RFP del cliente y extrae ASPECTOS CLAVE.\\n\\n"
        "Cliente: {client_name}\\n"
        "Servicios solicitados: {services}\\n\\n"
        "Extrae SOLO informacion explicita. No inventes cifras.\\n\\n"
        "Devuelve JSON con: agent_count, shifts, sla_response,\\n"
        "key_aspects, open_questions"
    ),
}


def _llm_classify(text: str, client_name: str = "") -> dict[str, Any] | None:
    # Classify document via OpenAI LLM directly. Returns None if LLM is unavailable.
    try:
        from openai import OpenAI
        client = OpenAI()
    except (ImportError, Exception) as exc:
        logger.warning("LLM classify import failed: %s", exc)
        return None

    prompt = (
        "Eres un clasificador de documentos para Nexova, "
        "consultora espanola de RRHH y outsourcing.\n"
        "Determina si el siguiente documento es una RFP "
        "(Request for Proposal) valida\n"
        "de un cliente potencial.\n"
        "Reglas:\n"
        "- Una RFP valida es una SOLICITUD de servicios "
        "(seleccion, capacitacion, soporte).\n"
        "- NO es RFP si el documento es un pitch comercial "
        "(la empresa se ofrece a si misma).\n"
        "- NO es RFP si es solo informacion general sin "
        "solicitud de servicios.\n"
        "- La mera presencia de la palabra RFP no la hace valida.\n\n"
        f"Cliente (si se conoce): {client_name}\n\n"
        f"Documento:\n{text[:4000]}\n\n"
        "Responde en JSON EXACTO:\n"
        '{"is_valid_rfp": true/false, '
        '"reason": "explicacion breve"}'
    )
    try:
        raw = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        response_text = raw.choices[0].message.content or ""
        idx_start = response_text.find("{")
        idx_end = response_text.rfind("}")
        if idx_start >= 0 and idx_end > idx_start:
            result = json.loads(response_text[idx_start : idx_end + 1])
            return {
                "is_valid_rfp": result.get("is_valid_rfp", False),
                "classification_reason": result.get(
                    "reason", "Clasificado por LLM."
                ),
            }
    except Exception as exc:
        logger.warning("LLM classification failed: %s", exc)

    return None


def _heuristic_classify(text: str) -> dict[str, Any]:
    # Heuristic-only classification - fallback when LLM unavailable.
    if not text or len(text.strip()) < 50:
        return {
            "is_valid_rfp": False,
                "classification_reason": "No se detectan señales de RFP: documento demasiado corto o vacío.",
        }
    text_lower = text.lower()

    has_rfp_greeting = any(
        phrase in text_lower
        for phrase in [
            "rfp", "request for proposal", "solicitud de propuesta",
            "propuesta",
        ]
    )
    has_service_request = any(
        phrase in text_lower
        for phrase in [
            "necesitamos", "requerimos", "buscamos", "quisieramos",
            "nos gustaria", "we need", "we are looking for",
            "we require", "we would like",
        ]
    )
    has_vendor_pitch = any(
        phrase in text_lower
        for phrase in [
            "somos", "ofrecemos", "nuestro producto",
            "we offer", "our platform", "we specialize",
            "we are a leading", "our solution",
        ]
    )

    if has_vendor_pitch and not has_rfp_greeting and not has_service_request:
        return {
            "is_valid_rfp": False,
            "classification_reason": "Documento es un pitch de proveedor, "
            "no una RFP de cliente.",
        }

    if has_rfp_greeting or has_service_request:
        return {
            "is_valid_rfp": True,
            "classification_reason": "Documento clasificado como RFP de cliente.",
        }

    return {
        "is_valid_rfp": False,
        "classification_reason": "No se detectaron senales de RFP de cliente.",
    }


def classify_rfp(state: dict[str, Any]) -> dict[str, Any]:
    # Determine if the document is a valid RFP from a potential client.
    # LLM-first, falls back to heuristic when LLM is unavailable.
    # Returns dict with keys to merge into shared state.
    text = state.get("markdown", "")
    if not text or len(text.strip()) < 50:
        return {
            "is_valid_rfp": False,
            "classification_reason": "Documento demasiado corto o vacio.",
        }

    client_name = state.get("metadata", {}).get("client_name", "")
    llm_result = _llm_classify(text, client_name)

    if llm_result is not None:
        logger.info(
            "LLM classification: %s",
            llm_result.get("classification_reason"),
        )
        return llm_result

    logger.info("LLM unavailable, falling back to heuristic classification")
    return _heuristic_classify(text)


def extract_metadata(state: dict[str, Any]) -> dict[str, Any]:
    """Extract client info, services, scope, deadline, budget from markdown."""
    text = state.get("markdown", "")
    text_lower = text.lower()

    # Client name: prefer **Cliente:** or Cliente: pattern in markdown
    client_name = None
    client_match = re.search(
            r"\*{0,2}(?:Cliente|Client|Empresa|Organization|Company)\*{0,2}\s*:\s*(.+?)(?:\n|$)",
        text, re.IGNORECASE,
    )
    if client_match:
            client_name = client_match.group(1).strip().rstrip(".").lstrip("*").strip()
    if not client_name:
        # Fallback: first substantive line that isn't a header
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith(("rfp", "request", "solicitud", "fecha", "para:", "#")):
                continue
            if len(line) > 5 and len(line) < 80:
                if not any(c in line for c in ".?!"):
                    client_name = line.rstrip(".")
                    break
                if line.endswith(".") and len(line) < 40:
                    client_name = line.rstrip(".")
                    break
    if not client_name:
        client_name = "Cliente no identificado"

    # Client HQ
    client_hq = "España"
    if re.search(r"\bmiami\b", text_lower):
        client_hq = "Miami"
    if re.search(r"\busa\b|\bunited states\b|\beeuu\b", text_lower):
        client_hq = "Miami"

    # Services requested — first few lines after the greeting
    services: list[str] = []
    service_section = text
    for sep_re in [
        r"(?:servicios?\s+solicitados?|servicios?\s+requeridos|alcance|scope of work|objetivo)",
    ]:
        parts = re.split(sep_re, text_lower, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) > 1:
            service_section = parts[1]
            break
    preview = service_section[:500]
    for sep in ["\n", ".", ",", ";"]:
        for part in preview.split(sep):
            p = part.strip()
            if len(p) > 10 and len(p) < 300:
                services.append(p[:200])
        if services:
            break
    if not services:
        services = ["Servicio profesional — revisar RFP para detalles"]

    # Scope
    scope = text[:2000] if len(text) > 100 else text

    # Deadline
    deadline = None
    for pattern in [
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
        r"(\d{4})-(\d{2})-(\d{2})",
    ]:
        match = re.search(pattern, text)
        if match:
            try:
                g = match.groups()
                if int(g[0]) > 1000:  # YYYY-MM-DD
                    deadline = f"{g[0]}-{g[1]}-{g[2]}"
                else:  # DD-MM-YYYY or MM-DD-YYYY
                    deadline = f"{g[2]}-{g[1]}-{g[0]}"
                break
            except (ValueError, IndexError):
                continue

    # Budget
    budget_range = None
    budget_match = re.search(
        r"(?:presupuesto|budget|inversi[oó]n|rango)\s*(?::|de|:)?\s*[\$€]?\s*([\d.,]+)"
        r"(?:\s*-\s*[\$€]?\s*([\d.,]+))?\s*(€|usd|eur)?",
        text,
        re.IGNORECASE,
    )
    if budget_match:
        budget_range = budget_match.group(0).strip()[:256]

    departments_needed = _detect_departments(services)
    readability = _calculate_readability(text)

    return {
        "metadata": {
            "client_name": client_name,
            "client_hq": client_hq,
            "services_requested": services[:5],
            "scope": scope,
            "deadline": deadline,
            "budget_range": budget_range,
            "departments_needed": departments_needed,
            "readability_flesch": readability.get("flesch"),
            "readability_gunning_fog": readability.get("gunning_fog"),
            "word_count": readability.get("word_count", 0),
        }
    }


def route_to_departments(state: dict[str, Any]) -> dict[str, Any]:
    """
    Orchestrator: based on classified departments, prepare worker inputs.
    Each worker receives shared metadata + relevant extracts.
    """
    metadata = state.get("metadata", {})
    depts = metadata.get("departments_needed", ["seleccion"])
    text = state.get("markdown", "")

    worker_inputs = {}
    for dept_id in depts:
        dept_info = _DEPARTMENTS.get(dept_id, {})
        worker_inputs[dept_id] = {
            "department_id": dept_id,
            "department_name": dept_info.get("name", dept_id),
            "responsible": dept_info.get("responsible", ""),
            "client_name": metadata.get("client_name", ""),
            "client_hq": metadata.get("client_hq", ""),
            "services_requested": metadata.get("services_requested", []),
            "deadline": metadata.get("deadline"),
            "budget_range": metadata.get("budget_range"),
            "text_excerpt": text[:3000],
        }
    return {
        "worker_inputs": worker_inputs,
        "departments_needed": depts,
    }


def extract_department_aspects(state: dict[str, Any]) -> dict[str, Any]:
    """
    Worker/synthesizer: for each department, extract key_aspects
    relevant to their domain based on worker inputs.
    """
    worker_inputs = state.get("worker_inputs", {})
    sections: dict[str, dict[str, Any]] = {}
    metadata = state.get("metadata", {})
    full_text = state.get("markdown", "")

    for dept_id, inputs in worker_inputs.items():
        # Normalise: worker_inputs can be dict (from route_to_departments) or plain string (from tests)
        if isinstance(inputs, str):
            text_lower = inputs.lower()
            dept_name = _DEPARTMENTS.get(dept_id, {}).get("name", dept_id)
            responsible = _DEPARTMENTS.get(dept_id, {}).get("responsible", "")
        else:
            text_lower = (inputs.get("text_excerpt") or full_text or "").lower()
            dept_name = inputs.get("department_name", dept_id)
            responsible = inputs.get("responsible", "")
        aspects: dict[str, Any] = {
            "department_id": dept_id,
            "department_name": dept_name,
            "responsible": responsible,
        }

        if dept_id == "seleccion":
            volumes = re.findall(
                r"(\d+)\s*(?:roles?|perfiles?|posiciones?|puestos?|ejecutivos?|mandos?)",
                text_lower, re.IGNORECASE,
            )
            aspects["roles_to_cover"] = [v[0] for v in volumes[:5]] if volumes else ["No especificado"]
            aspects["estimated_close_time"] = "Por determinar (mín. 15 días hábiles)"
            aspects["consulting_hours"] = "Por determinar"
            aspects["open_questions"] = [
                "¿Cuántos roles exactos se necesitan cubrir?",
                "¿Hay un deadline específico para el cierre?",
            ]

        elif dept_id == "capacitacion":
            programs = re.findall(
                r"(?:programa|curso|taller|training|formaci[oó]n)\s*(?::|de|:)?\s*([^.\n]+)",
                text_lower, re.IGNORECASE,
            )
            aspects["applicable_programs"] = (
                [p.strip() for p in programs[:3]]
                if programs else ["Por determinar según necesidades del cliente"]
            )
            aspects["duration"] = "Por determinar"
            aspects["modality"] = "Por determinar (presencial/virtual/híbrido)"
            aspects["open_questions"] = [
                "¿Cuántos participantes?",
                "¿Modalidad preferida?",
                "¿Hay certificación requerida?",
            ]

        elif dept_id == "soporte":
            agents = re.findall(
                r"(\d+)\s*(?:agentes?|personas?|operadores?|staff|team)",
                text_lower, re.IGNORECASE,
            )
            aspects["agent_count"] = int(agents[0]) if agents else None
            aspects["shifts"] = "24/7 (según solicitud)"
            aspects["sla_response"] = "24 horas (requisito obligatorio)"
            aspects["open_questions"] = [
                "¿Volumen de tickets estimado?",
                "¿Horario de operación?",
                "¿Idiomas requeridos?",
            ]

        aspects["key_aspects"] = (
                    f"Aspectos clave para {dept_name} "
                    f"en propuesta para {metadata.get('client_name', 'cliente')}"
        )
        sections[dept_id] = aspects

    return {
        "department_sections": sections,
    }


# ── Synthesizer node ───────────────────────────────────────────────────


def synthesize_results(state: dict[str, Any]) -> dict[str, Any]:
    # Synthesizer: consolidates department analysis into a sales summary
    # and handoff payload for Part 2.
    sections = state.get("department_sections", {})
    metadata = state.get("metadata", {})
    client_name = metadata.get("client_name", "Cliente no identificado")

    if not sections:
        return {
            "sales_summary": "No hay secciones de departamento para sintetizar.",
        "handoff_payload": None,
        }

    dept_summaries = []
    for dept_id, section in sections.items():
        dept_info = _DEPARTMENTS.get(dept_id, {})
        aspects = section.get("key_aspects", "")
        dept_summaries.append(
            "- "
            + dept_info.get("name", dept_id)
            + " (resp: "
            + dept_info.get("responsible", "")
            + "):\\n"
            + "  "
            + str(aspects)[:500]
        )

    sales_summary = _llm_generate_summary(client_name, dept_summaries)

    handoff_payload = {
            "version": "1.0",
        "ticket_id": state.get("ticket_id"),
        "client_name": client_name,
            "workstreams": {
            k: {kk: vv for kk, vv in v.items() if kk != "text_excerpt"}
            for k, v in sections.items()
        },
        "sales_summary": sales_summary,
    }

    return {
        "sales_summary": sales_summary,
        "handoff_payload": handoff_payload,
    }


def _llm_generate_summary(
    client_name: str, dept_summaries: list[str]
) -> str:
    # Generate a consolidated sales summary via LLM, with fallback.
    try:
        from openai import OpenAI
        client = OpenAI()
    except (ImportError, Exception):
        parts = [str(d) for d in dept_summaries]
        return "Resumen para ventas - " + client_name + ":\n" + "\n".join(parts)

    prompt = (
        "Eres un sintetizador de propuestas para Nexova.\n"
        "Genera un resumen para el equipo de Ventas "
        "sobre que ofrecer a quien.\n\n"
        "Cliente: " + client_name + "\n"
        "Analisis por departamento:\n"
        + "\n".join(dept_summaries)
        + "\n\n"
        'Responde en JSON: {"recomendation": "que ofrecer a quien", '
        '"key_opportunities": ["op1", "op2"], '
        '"next_steps": ["paso1", "paso2"]}'
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        response = resp.choices[0].message.content or ""
        return response
    except Exception as exc:
        logger.warning("LLM summary failed: %s", exc)
        return "Resumen generado para " + client_name + "."


def _llm_extract_aspects(
    dept_id: str,
    client_name: str,
    extracto: str,
) -> dict[str, Any] | None:
    # Attempt LLM extraction of department aspects; returns None on failure (heuristic fallback).
    try:
        from openai import OpenAI
        client = OpenAI()
    except Exception:
        return None

    prompt = (
        "Extrae informacion estructurada de este extracto de RFP para el departamento "
        + dept_id
        + ".\nCliente: "
        + client_name
        + "\nExtracto: "
        + extracto
        + "\n"
        "Devuelve JSON con las claves relevantes para ese departamento. "
        "Si falta informacion, indica 'Por determinar'."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        response = resp.choices[0].message.content or ""
        idx_start = response.find("{")
        idx_end = response.rfind("}")
        if idx_start >= 0 and idx_end > idx_start:
            data = json.loads(response[idx_start : idx_end + 1])
            return data
    except Exception:
        return None
    return None


# ── Persistence nodes ──────────────────────────────────────────────────


def reject_document_node(state: dict[str, Any]) -> dict[str, Any]:
    """Mark ticket as discarded in the database."""
    ticket_id = state.get("ticket_id")
    reason = state.get("classification_reason", "Documento inválido.")
    if ticket_id:
        with Session(engine) as session:
            _update_ticket_status(
                session, ticket_id, TicketStatus.DESCARTADO, error_message=reason
            )
    return {
        "ticket_status": TicketStatus.DESCARTADO.value,
        "classification_reason": reason,
    }


def persist_results_node(state: dict[str, Any]) -> dict[str, Any]:
    """Persist ticket status, metadata, department sections and handoff payload to Supabase."""
    ticket_id = state.get("ticket_id")
    metadata = state.get("metadata", {})
    sections = state.get("department_sections", {})
    handoff_payload = state.get("handoff_payload")
    sales_summary = state.get("sales_summary")

    if not ticket_id:
        return {"error": "No ticket_id in state"}

    with Session(engine) as session:
        _update_ticket_status(session, ticket_id, TicketStatus.ANALISIS_COMPLETO)

        rfp_id = _new_id()
        deadline_val = None
        if metadata.get("deadline"):
            try:
                deadline_val = date.fromisoformat(metadata["deadline"])
            except (ValueError, TypeError):
                pass

        rfp_metadata = RFPMetadata(
            rfp_id=rfp_id,
            ticket_id=ticket_id,
            client_name=metadata.get("client_name", "Cliente no identificado"),
            client_hq=metadata.get("client_hq", "España"),
                    currency=_client_hq_currency(metadata.get("client_hq", "España")),
            services_requested=metadata.get("services_requested", []),
            scope=metadata.get("scope"),
            deadline=deadline_val,
            budget_range=metadata.get("budget_range"),
            departments_needed=metadata.get("departments_needed", []),
            readability_flesch=metadata.get("readability_flesch"),
            readability_gunning_fog=metadata.get("readability_gunning_fog"),
            word_count=metadata.get("word_count"),
        )
        session.add(rfp_metadata)
        session.flush()

        ticket_obj = session.exec(
            select(Ticket).where(Ticket.ticket_id == ticket_id)
        ).first()
        if ticket_obj:
            ticket_obj.rfp_id = rfp_id
            ticket_obj.is_valid_rfp = True
            ticket_obj.sales_summary = sales_summary
            if handoff_payload:
                ticket_obj.handoff_json = json.dumps(handoff_payload, ensure_ascii=False)

        for dept_id, section_data in sections.items():
            dept_section = DepartmentSection(
                ticket_id=ticket_id,
                department_id=dept_id,
                department_name=section_data.get("department_name"),
                key_aspects=json.dumps(section_data, ensure_ascii=False),
                approval_status=ApprovalStatus.PENDING.value,
            )
            session.add(dept_section)

        session.commit()

    return {
        "rfp_id": rfp_id,
        "ticket_status": TicketStatus.ANALISIS_COMPLETO.value,
        "sections_persisted": list(sections.keys()),
        "sales_summary": sales_summary,
        "handoff_payload": handoff_payload,
    }


# ── Graph construction ─────────────────────────────────────────────────


def build_rfp_intake_graph() -> StateGraph:
    """Compile and return the RFP intake LangGraph."""
    builder = StateGraph(RFPIntakeState)

    builder.add_node("classify_rfp", classify_rfp)
    builder.add_node("extract_metadata", extract_metadata)
    builder.add_node("route_to_departments", route_to_departments)
    builder.add_node("extract_department_aspects", extract_department_aspects)
    builder.add_node("synthesize_results", synthesize_results)
    builder.add_node("persist_results", persist_results_node)
    builder.add_node("reject_document", reject_document_node)

    builder.add_edge(START, "classify_rfp")
    builder.add_conditional_edges(
        "classify_rfp",
        _route_after_classification,
        {"valid": "extract_metadata", "reject": "reject_document"},
    )
    builder.add_edge("extract_metadata", "route_to_departments")
    builder.add_edge("route_to_departments", "extract_department_aspects")
    builder.add_edge("extract_department_aspects", "synthesize_results")
    builder.add_edge("synthesize_results", "persist_results")
    builder.add_edge("persist_results", END)
    builder.add_edge("reject_document", END)

    return builder.compile()


def _route_after_classification(state: dict[str, Any]) -> str:
    return "valid" if state.get("is_valid_rfp", False) else "reject"


def _validate_graph_definition(graph: StateGraph) -> None:
    """Verify all expected nodes and edges are present — fails fast on startup."""
    expected_nodes = {
        "classify_rfp", "extract_metadata", "route_to_departments",
        "extract_department_aspects", "synthesize_results", "persist_results", "reject_document",
    }
    actual_nodes = set(graph.nodes.keys()) if hasattr(graph, "nodes") else set()
    # LangGraph v1.2+ might not expose .nodes directly; skip validation if unavailable
    if actual_nodes:
        missing = expected_nodes - actual_nodes
        if missing:
            raise ValueError(f"Graph missing nodes: {missing}")


# Compile at import time so failures surface at startup
rfp_intake_graph = build_rfp_intake_graph()
_validate_graph_definition(rfp_intake_graph)


# ── Public entry point ──────────────────────────────────────────────────


def run_rfp_intake(
    ticket_id: str,
    markdown_text: str,
) -> dict[str, Any]:
    """
    Execute the full RFP intake pipeline for a given ticket and document.

    Returns the final graph state with ticket_status, rfp_id, metadata, etc.
    """
    initial_state: dict[str, Any] = {
        "ticket_id": ticket_id,
        "markdown": markdown_text,
        "is_valid_rfp": False,
        "classification_reason": "",
        "metadata": {},
        "worker_inputs": {},
        "departments_needed": [],
        "department_sections": {},
        "sales_summary": None,
        "handoff_payload": None,
        "rfp_id": None,
        "ticket_status": None,
        "error": None,
    }
    try:
        result = rfp_intake_graph.invoke(initial_state)
        return result
    except Exception as exc:
        logger.exception("RFP intake pipeline failed (ticket=%s)", ticket_id)
        with Session(engine) as session:
            _update_ticket_status(
                session,
                ticket_id,
                TicketStatus.DESCARTADO,
                error_message=f"Pipeline error: {exc}",
            )
        return {
            "ticket_id": ticket_id,
            "error": str(exc),
            "ticket_status": TicketStatus.DESCARTADO.value,
        }