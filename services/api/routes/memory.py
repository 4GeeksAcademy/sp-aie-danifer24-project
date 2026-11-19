"""REST endpoints for agent-memory introspection and management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.api.security import CurrentUser, get_current_user
from services.api.services.agent_memory import get_memory_service

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/agent/memory",
    tags=["memory"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/facts")
def list_facts(
    current_user: CurrentUser,  # noqa: ARG001
    limit: int = Query(default=20, ge=1, le=100),
    fact_type: str | None = Query(default=None),
) -> dict[str, list[dict[str, Any]]]:
    """Return stored memory facts, newest first. Optionally filter by type."""
    mem_svc = get_memory_service()
    facts = mem_svc.get_facts(limit=limit, fact_type=fact_type)
    return {"facts": facts}


@router.get("/audit")
def list_audit_log(
    current_user: CurrentUser,  # noqa: ARG001
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, list[dict[str, Any]]]:
    """Return the audit log of memory proposals and decisions."""
    mem_svc = get_memory_service()
    entries = mem_svc.get_audit_log(limit=limit)
    return {"audit_entries": entries}


@router.post("/consolidate")
def trigger_consolidation(
    current_user: CurrentUser,  # noqa: ARG001
) -> dict[str, Any]:
    """Run consolidation policy: expiry, dedup, merge, cap. Returns a summary."""
    mem_svc = get_memory_service()
    report = mem_svc.consolidate()
    return {"consolidation": report}


@router.get("/proposal")
def get_pending_proposal(
    current_user: CurrentUser,  # noqa: ARG001
) -> dict[str, Any]:
    """Return the current pending memory proposal, or an empty response."""
    mem_svc = get_memory_service()
    proposal = mem_svc.get_proposal()
    if proposal is None:
        return {"proposal": None}
    return {"proposal": proposal}