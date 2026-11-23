"""HTTP endpoints for RFP intake pipeline (Part 1) and generation (Part 2)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlmodel import Session

from services.api.database import engine, get_db
from services.api.models import Ticket, TicketStatus
from services.api.security import CurrentUser, get_current_user
from services.api.services.rfp_intake import run_rfp_intake

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/rfp",
    tags=["rfp"],
    dependencies=[Depends(get_current_user)],
)

RAW_DIR = Path(os.getenv("RFP_RAW_DIR", "data/raw"))


class TicketResponse(BaseModel):
    ticket_id: str
    status: str
    error_message: str | None = None
    created_at: datetime | None = None
    rfp_id: str | None = None


class TicketListResponse(BaseModel):
    tickets: list[TicketResponse]


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_rfp(
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
) -> dict:
    """
    Upload an RFP PDF, create a ticket, and launch the intake pipeline
    in the background. Returns immediately with the ticket_id.
    """
    # Validate file extension
    filename = Path(file.filename or "").name
    if not filename or Path(filename).suffix.lower() not in {".pdf"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Solo se aceptan archivos PDF.",
        )

    # Read file contents
    try:
        contents = await file.read()
    except (OSError, RuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo leer el archivo cargado.",
        ) from error
    finally:
        await file.close()

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo PDF está vacío.",
        )

    ticket_id = str(uuid4())
    raw_path = RAW_DIR / ticket_id / filename

    try:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(contents)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo guardar el archivo en el servidor.",
        ) from error

    # Create ticket in DB
    with Session(engine) as session:  # type: ignore[union-attr]
        ticket = Ticket(
            ticket_id=ticket_id,
            status=TicketStatus.ANALIZANDO,
            raw_pdf_path=str(raw_path),
        )
        session.add(ticket)
        session.commit()

    # Launch pipeline in background thread
    Thread(
        target=_background_pipeline,
        args=(ticket_id, str(raw_path)),
        daemon=True,
    ).start()

    return {
        "ticket_id": ticket_id,
        "status": TicketStatus.ANALIZANDO.value,
        "message": "RFP recibida. El análisis está en progreso.",
    }


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket(
    ticket_id: str,
    current_user: CurrentUser = None,
    session: Session = Depends(get_db),
) -> TicketResponse:
    """Get ticket status and results."""
    ticket = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket no encontrado.",
        )
    return TicketResponse(
        ticket_id=ticket.ticket_id,
        status=ticket.status.value if hasattr(ticket.status, "value") else ticket.status,
        error_message=ticket.error_message,
        created_at=ticket.created_at,
        rfp_id=ticket.rfp_id,
    )


@router.get("/{ticket_id}/departments")
def get_ticket_departments(
    ticket_id: str,
    current_user: CurrentUser = None,
    session: Session = Depends(get_db),
) -> dict:
    """Return department-level key_aspects for a completed ticket."""
    from services.api.models import DepartmentSection

    sections = (
        session.query(DepartmentSection)
        .filter(DepartmentSection.ticket_id == ticket_id)
        .all()
    )
    if not sections:
        ticket = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        raise HTTPException(
            status_code=404,
            detail="No hay secciones de departamento para este ticket. "
            "Espera a que termine el análisis.",
        )

    return {
        "ticket_id": ticket_id,
        "departments": {
            s.department_id: {
                            "department_id": s.department_id,
                            "department_name": s.department_name,
                            "key_aspects": json.loads(s.key_aspects) if s.key_aspects else {},
                "approval_status": s.approval_status,
            }
            for s in sections
        },
    }


@router.get("/", response_model=TicketListResponse)
def list_tickets(
    current_user: CurrentUser = None,
    session: Session = Depends(get_db),
) -> TicketListResponse:
    """List all RFP tickets, newest first."""
    from services.api.models import Ticket as TicketModel

    tickets = (
        session.query(TicketModel)
        .order_by(TicketModel.created_at.desc())
        .limit(50)
        .all()
    )
    return TicketListResponse(
        tickets=[
            TicketResponse(
                ticket_id=t.ticket_id,
                status=t.status.value if hasattr(t.status, "value") else t.status,
                error_message=t.error_message,
                created_at=t.created_at,
                rfp_id=t.rfp_id,
            )
            for t in tickets
        ]
    )


# ── Background pipeline ────────────────────────────────────────────────


def _background_pipeline(ticket_id: str, pdf_path: str) -> None:
    """
    Convert PDF to markdown, then run the intake pipeline.
    Runs in a daemon thread so it doesn't block the HTTP response.
    """
    logger.info("RFP background pipeline starting (ticket=%s)", ticket_id)

    # 1. Convert PDF to markdown
    try:
        from markitdown import MarkItDown

        md_converter = MarkItDown()
        result = md_converter.convert(pdf_path)
        markdown_text = result.text_content
    except Exception as exc:
        logger.exception("PDF→Markdown conversion failed (ticket=%s)", ticket_id)
        with Session(engine) as session:
            _update_ticket_status(
                session, ticket_id, TicketStatus.DESCARTADO,
                error_message=f"Error al convertir PDF: {exc}",
            )
        return

    if not markdown_text or len(markdown_text.strip()) < 10:
        with Session(engine) as session:
            _update_ticket_status(
                session, ticket_id, TicketStatus.DESCARTADO,
                error_message="No se pudo extraer texto del PDF.",
            )
        return

    # 2. Run pipeline
    try:
        result = run_rfp_intake(ticket_id, markdown_text)
        logger.info(
            "RFP pipeline completed (ticket=%s, status=%s, rfp_id=%s)",
            ticket_id,
            result.get("ticket_status"),
            result.get("rfp_id"),
        )
    except Exception as exc:
        logger.exception("RFP pipeline runtime error (ticket=%s)", ticket_id)


def _update_ticket_status(
    session: Session, ticket_id: str, status: TicketStatus, error_message: str | None = None
) -> None:
    ticket = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if ticket:
        ticket.status = status
        ticket.updated_at = datetime.now(timezone.utc)
        if error_message:
            ticket.error_message = error_message
        session.commit()


# ── Part 2: Generation endpoints ───────────────────────────────────────


class GenerateResponse(BaseModel):
    ticket_id: str
    ticket_status: str
    departments: dict[str, Any]


class DepartmentDraftResponse(BaseModel):
    department_id: str
    department_name: str
    draft_content: str | None
    key_aspects: dict[str, Any] | None
    approval_status: str


@router.post("/{ticket_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_proposal(
    ticket_id: str,
    current_user: CurrentUser = None,
) -> dict:
    """
    Launch Part 2 generation pipeline for a completed ticket.
    Reads handoff from Part 1 (no re-ingestion of raw PDF).
    Returns immediately; generation runs in background.
    """
    # Verify ticket exists and is in analisis_completo
    with Session(engine) as session:
        ticket = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket no encontrado.",
            )
        if ticket.status != TicketStatus.ANALISIS_COMPLETO:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ticket no está en estado analisis_completo (actual: {ticket.status})",
            )

    # Launch in background thread
    Thread(
        target=_background_generation,
        args=(ticket_id,),
        daemon=True,
    ).start()

    return {
        "ticket_id": ticket_id,
        "status": "generating",
        "message": "Generación de borradores iniciada.",
    }


@router.get("/{ticket_id}/drafts")
def get_ticket_drafts(
    ticket_id: str,
    current_user: CurrentUser = None,
    session: Session = Depends(get_db),
) -> dict:
    """
    Return draft content for all departments of a ticket.
    Used by the frontend to display generated proposal sections.
    """
    from services.api.models import DepartmentSection

    sections = (
        session.query(DepartmentSection)
        .filter(DepartmentSection.ticket_id == ticket_id)
        .all()
    )
    if not sections:
        ticket = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        raise HTTPException(
            status_code=404,
            detail="No hay secciones de departamento para este ticket.",
        )

    return {
        "ticket_id": ticket_id,
        "departments": {
            s.department_id: {
                "department_id": s.department_id,
                "department_name": s.department_name,
                "draft_content": s.draft_content,
                "key_aspects": json.loads(s.key_aspects) if s.key_aspects else {},
                "approval_status": s.approval_status,
                "needs_human_review": s.needs_human_review,
                "iteration_count": s.iteration_count,
                "evaluation_result": json.loads(s.evaluation_result) if s.evaluation_result else None,
            }
            for s in sections
        },
    }


def _background_generation(ticket_id: str) -> None:
    """Run Part 2 generation in background thread."""
    from services.api.services.rfp_generation import run_rfp_generation

    logger.info("Background generation starting (ticket=%s)", ticket_id)
    try:
        result = run_rfp_generation(ticket_id)
        logger.info(
            "Background generation completed (ticket=%s, status=%s)",
            ticket_id,
            result.get("ticket_status"),
        )
    except Exception as exc:
        logger.exception("Background generation failed (ticket=%s)", ticket_id)