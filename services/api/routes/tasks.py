"""Authenticated Celery task status endpoint."""

from fastapi import APIRouter, Depends

from services.api.security import get_current_user
from services.celery_app import celery_app
from services.reporting.schemas import TaskStatusResponse

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str):
    """Return normalized Celery state and result, when one is available."""
    task_result = celery_app.AsyncResult(task_id)
    celery_state = task_result.state.upper()

    if celery_state in {"PENDING", "RECEIVED", "RETRY"}:
        normalized_state = "pending"
    elif celery_state in {"STARTED", "PROGRESS"}:
        normalized_state = "started"
    elif celery_state == "SUCCESS":
        normalized_state = "success"
    else:
        normalized_state = "failure"

    result = None
    if celery_state == "SUCCESS":
        result = task_result.result
    elif celery_state == "FAILURE":
        result = str(task_result.result)

    return {"task_id": task_id, "status": normalized_state, "result": result}
