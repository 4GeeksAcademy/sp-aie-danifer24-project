"""HTTP endpoint exposing the compiled knowledge agent graph."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from services.api.security import CurrentUser, get_current_user

from services.api.routes.knowledge import KnowledgeQueryRequest, KnowledgeQueryResponse
from services.api.services.knowledge_graph import run_knowledge_graph
from mcps.nexova_mcp.request_context import api_bearer_token

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/query", response_model=KnowledgeQueryResponse)
def agent_query(
    payload: KnowledgeQueryRequest,
    current_user: CurrentUser,
) -> KnowledgeQueryResponse:
    """Invoke the compiled graph and return a safe response, never raw exceptions."""
    from services.api.security import create_access_token

    # Derive a short-lived, read-only MCP token for the authenticated user.
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
