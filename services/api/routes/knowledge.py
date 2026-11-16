"""HTTP endpoint for querying Nexova's company knowledge base."""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from services.api.services.knowledge_graph import run_knowledge_graph


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class KnowledgeQueryResponse(BaseModel):
    answer: str
    run_id: str


@router.post("/query", response_model=KnowledgeQueryResponse)
def knowledge_query(request: KnowledgeQueryRequest) -> KnowledgeQueryResponse:
    """Return only the generated answer; retrieval details stay server-side."""
    try:
        result = run_knowledge_graph(request.question)
        if result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=result["error"],
            )
        answer = result["answer"]
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Knowledge query failed (%s)", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo consultar la base de conocimiento en este momento.",
        ) from error

    return KnowledgeQueryResponse(answer=answer, run_id=result["run_id"])
