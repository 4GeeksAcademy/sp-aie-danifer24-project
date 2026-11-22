#!/usr/bin/env python
"""End-to-end offline test of the RFP pipeline without a running server."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text as sa_text
from sqlmodel import SQLModel, Session

from services.api.database import engine
from services.api.models import (
    DepartmentSection,
    FinalDocument,
    RFPMetadata,
    Ticket,
    TicketStatus,
)
from services.api.services.rfp_intake import run_rfp_intake


def check(condition: bool, msg: str) -> None:
    if not condition:
        print(f"  FAIL: {msg}")
        sys.exit(1)
    print(f"  OK: {msg}")


def main() -> None:
    print("=== RFP Pipeline E2E Test ===\n")

    # 1. Create tables
    print("1. Tables")
    SQLModel.metadata.create_all(engine)
    check(True, "create_all idempotent")

    # 2. Insert a ticket
    ticket_id = f"test-{uuid4().hex[:8]}"
    with Session(engine) as session:
        ticket = Ticket(ticket_id=ticket_id, status=TicketStatus.ANALIZANDO)
        session.add(ticket)
        session.commit()
        db_id = ticket.id
    print(f"\n2. Ticket created: {ticket_id} (pk={db_id})")
    check(db_id is not None and db_id > 0, "ticket has auto-increment id")

    # 3. Run pipeline with a realistic RFP document
    markdown = """# Solicitud de Propuesta — Nexova AI Platform

**Cliente:** Nexova Corp
**HQ:** Madrid, Espana
**Fecha limite:** 2025-09-30
**Presupuesto:** 120,000 - 150,000 EUR

Nexova Corp solicita servicios de consultoria para implementar una plataforma de IA.
Se requiere analisis legal, auditoria financiera, y evaluacion de compliance.

**Servicios solicitados:**
1. Consultoria en IA
2. Auditoria financiera
3. Campana de marketing digital
4. Analisis de ciberseguridad
"""

    print(f"\n3. Running pipeline...")
    result = run_rfp_intake(ticket_id, markdown)

    error = result.get("error")
    status = result.get("ticket_status")
    is_valid = result.get("is_valid_rfp", False)
    rfp_id = result.get("rfp_id")
    meta = result.get("metadata", {})
    sections = result.get("department_sections", {})

    check(error is None, f"no error (got {error!r})")
    check(status == "analisis_completo", f"status = {status!r}")
    check(is_valid is True, f"is_valid_rfp = {is_valid}")
    check(rfp_id is not None, f"rfp_id = {rfp_id}")
    check(meta.get("client_name") == "Nexova Corp", f"client_name = {meta.get('client_name')!r}")
    print(f"   Departments: {meta.get('departments_needed')}")
    print(f"   Sections:    {list(sections.keys())}")

    # 4. Verify DB persistence
    print("\n4. DB persistence")
    with Session(engine) as session:
        # Ticket
        t = session.execute(
                    sa_text("SELECT status, is_valid_rfp, rfp_id, sales_summary FROM rfp_tickets WHERE ticket_id = :tid"),
            {"tid": ticket_id},
        ).fetchone()
        check(t is not None, "ticket row exists")
        check(t[0] == "analisis_completo", f"ticket status = {t[0]!r}")
        check(t[1] is True, f"ticket is_valid_rfp = {t[1]}")
        check(t[3] is not None and len(t[3]) > 0, f"ticket sales_summary present (len={len(t[3]) if t[3] else 0})")

    # Handoff payload
    ho_q = sa_text("SELECT handoff_json FROM rfp_tickets WHERE ticket_id = :tid")
    ho_row = session.execute(ho_q, {"tid": ticket_id}).fetchone()
    check(ho_row is not None and ho_row[0] is not None, "handoff_json present")
    if ho_row and ho_row[0]:
        ho = json.loads(ho_row[0])
        check(isinstance(ho, dict), "handoff_json is dict")
        check(ho.get("version") == "1.0", f"handoff version = {ho.get('version')}")
        check(ho.get("ticket_id") == ticket_id, f"handoff ticket_id = {ho.get('ticket_id')}")
        check(len(ho.get("workstreams", {})) >= 1, f"handoff workstreams count = {len(ho.get('workstreams', {}))}")
        check("seleccion" in ho.get("workstreams", {}), "handoff includes seleccion workstream")

        # Metadata
        m = session.execute(
            sa_text("SELECT client_name, departments_needed, currency FROM rfp_metadata WHERE ticket_id = :tid"),
            {"tid": ticket_id},
        ).fetchone()
        check(m is not None, "metadata row exists")
        check(m[0] == "Nexova Corp", f"metadata client = {m[0]!r}")
        check(m[1] is not None, f"departments_needed = {m[1]}")
        check(m[2] == "EUR", f"currency = {m[2]!r}")

        # Department sections
        d = session.execute(
            sa_text("SELECT department_id, department_name FROM rfp_department_sections WHERE ticket_id = :tid"),
            {"tid": ticket_id},
        ).all()
        check(len(d) > 0, f"{len(d)} department sections")
        check(d[0][1] == "Talent Selection Operations", f"dept name = {d[0][1]!r}")

    # 5. Cleanup
    with Session(engine) as session:
        session.execute(sa_text("DELETE FROM rfp_department_sections WHERE ticket_id = :tid"), {"tid": ticket_id})
        session.execute(sa_text("DELETE FROM rfp_metadata WHERE ticket_id = :tid"), {"tid": ticket_id})
        session.execute(sa_text("DELETE FROM rfp_final_documents WHERE ticket_id = :tid"), {"tid": ticket_id})
        session.execute(sa_text("DELETE FROM rfp_tickets WHERE ticket_id = :tid"), {"tid": ticket_id})
        session.commit()
    print(f"\n5. Cleaned up test ticket {ticket_id}")

    print("\n=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    main()