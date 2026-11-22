#!/usr/bin/env python
"""
CLI helper to reprocess an RFP PDF through the intake pipeline.

Usage:
    uv run python scripts/rfp_reprocess.py rfp-requests/nexova/nexova-request-1.pdf
    uv run python scripts/rfp_reprocess.py rfp-requests/nexova/nexova-request-1.pdf --verbose
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

# Ensure we can import from the project
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.api.database import engine
from services.api.models.rfp import Ticket, TicketStatus
from services.api.services.rfp_intake import run_rfp_intake
from sqlmodel import Session


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocess an RFP PDF through the intake pipeline.")
    parser.add_argument("pdf_path", type=str, help="Path to the PDF file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full pipeline state")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s | %(message)s",
    )
    logger = logging.getLogger(__name__)

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    if pdf_path.suffix.lower() != ".pdf":
        print(f"Error: Not a PDF file: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # 1. Convert PDF -> Markdown
    print(f"📄 Converting: {pdf_path.name}")
    print(f"   Size: {pdf_path.stat().st_size} bytes")

    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(str(pdf_path))
        markdown_text = result.text_content
    except ImportError:
        print("Error: markitdown not installed. Run: uv add markitdown[pdf]", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error converting PDF: {exc}", file=sys.stderr)
        sys.exit(1)

    if not markdown_text or len(markdown_text.strip()) < 10:
        print("Error: Could not extract text from PDF.", file=sys.stderr)
        sys.exit(1)

    print(f"\n📝 Markdown preview ({len(markdown_text)} chars):")
    print("─" * 60)
    print(markdown_text[:500].strip())
    print("─" * 60)
    print()

    # 2. Create a ticket in the DB
    ticket_id = str(uuid4())
    with Session(engine) as session:
        ticket = Ticket(
            ticket_id=ticket_id,
            status=TicketStatus.ANALIZANDO,
            raw_pdf_path=str(pdf_path),
        )
        session.add(ticket)
        session.commit()
    print(f"🎫 Ticket created: {ticket_id}")

    # 3. Run pipeline
    print("🔧 Running intake pipeline...")
    result = run_rfp_intake(ticket_id, markdown_text)

    status = result.get("ticket_status", "unknown")
    print(f"\n✅ Pipeline status: {status}")

    if result.get("error"):
        print(f"❌ Error: {result['error']}")
        sys.exit(1)

    if result.get("rfp_id"):
        print(f"📋 RFP ID: {result['rfp_id']}")

    if result.get("is_valid_rfp"):
        print(f"📊 Classification: {'VALID RFP' if result['is_valid_rfp'] else 'INVALID'}")

    metadata = result.get("metadata", {})
    if metadata:
        print(f"\n📋 Metadata:")
        print(f"   Client:       {metadata.get('client_name', '?')}")
        print(f"   HQ:           {metadata.get('client_hq', '?')}")
        print(f"   Departments:  {', '.join(metadata.get('departments_needed', []))}")
        print(f"   Word count:   {metadata.get('word_count', '?')}")
        flesch = metadata.get("readability_flesch")
        if flesch is not None:
            print(f"   Flesch:       {flesch}")
        fog = metadata.get("readability_gunning_fog")
        if fog is not None:
            print(f"   Gunning Fog:  {fog}")

    sections = result.get("department_sections", {})
    if sections:
        print(f"\n📊 Departments ({len(sections)}):")
        for dept_id, data in sections.items():
            print(f"   • {dept_id}: {data.get('department_name', '?')}")
            aspects = data.get("key_aspects", "")
            print(f"     {aspects[:120]}...")

    if args.verbose:
        print(f"\n📄 Full pipeline state:")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    print(f"\n✨ Done! Ticket: {ticket_id} (status: {status})")


if __name__ == "__main__":
    main()