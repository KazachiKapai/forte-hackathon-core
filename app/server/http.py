import logging
import os

from fastapi import APIRouter, Depends, FastAPI, Header, Request, BackgroundTasks, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from ..auth.middleware import get_auth
from ..auth import router as auth_router
from .models import StatusResponse
from ..repos import router as repos_router
from ..tokens import router as tokens_router
from ..webhook import WebhookProcessor
from ..config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

def _validate_webhook_headers(processor: WebhookProcessor, x_gitlab_event: str | None,) -> bool:
    return ["Note Hook", "Merge Request Hook"].__contains__(x_gitlab_event)


def create_app(processor: WebhookProcessor) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("FRONTEND_URL", "http://localhost:3000"),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=StatusResponse, response_model_exclude_none=True)
    async def health() -> StatusResponse:
        return StatusResponse(status="ok")


    api_router = APIRouter(dependencies=[Depends(get_auth)])
    api_router.include_router(auth_router)
    api_router.include_router(tokens_router)
    api_router.include_router(repos_router)

    app.include_router(api_router, prefix="/api")

    class WebhookResponse(BaseModel):
        success: bool
        message: str

    @app.post("/gitlab/webhook", response_model=WebhookResponse, status_code=status.HTTP_202_ACCEPTED)
    async def gitlab_webhook(
            request: Request,
            background_tasks: BackgroundTasks,
            x_gitlab_event: str | None = Header(default=None, alias="X-Gitlab-Event"),
    ) -> WebhookResponse:
        if not _validate_webhook_headers(processor, x_gitlab_event):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook event type"
            )

        payload = await request.json()

        if "object_attributes" not in payload or "project" not in payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload structure"
            )

        attrs = payload["object_attributes"]
        project_info = payload["project"]
        project_id = int(project_info["id"])

        if payload["object_kind"] == "note":
            mr = payload["merge_request"]
            mr_iid = int(mr["iid"])
            background_tasks.add_task(
                processor.process_note_comment,
                project_id,
                mr_iid,
                payload
            )
            return WebhookResponse(success=True, message="Note processing queued")

        if not processor.handle_merge_request_event(payload):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Event not applicable for processing"
            )

        last_commit = attrs["last_commit"]["id"]
        mr_iid = int(attrs["iid"])
        title = attrs["title"]
        description = attrs["description"]

        background_tasks.add_task(
            processor.process_merge_request,
            project_id,
            mr_iid,
            title,
            description,
            last_commit
        )

        return WebhookResponse(success=True, message="Merge request processing queued")

    return app
