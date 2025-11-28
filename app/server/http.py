import logging
import os

from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware

from ..auth.middleware import get_auth
from ..auth import router as auth_router
from .models import StatusResponse
from ..repos import router as repos_router
from ..tokens import router as tokens_router
from ..webhook import WebhookProcessor
from ..config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

def _validate_webhook_headers(processor: WebhookProcessor, x_gitlab_event: str | None, x_gitlab_token: str | None) -> bool:
    return processor.validate_secret(x_gitlab_token) and x_gitlab_event in {"Merge Request Hook", "Note Hook"}


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

    @app.post("/gitlab/webhook", response_model=StatusResponse, response_model_exclude_none=True)
    async def gitlab_webhook(
            request: Request,
            x_gitlab_event: str | None = Header(default=None, alias="X-Gitlab-Event"),
            x_gitlab_token: str | None = Header(default=None, alias="X-Gitlab-Token"),
    ) -> StatusResponse:
        logger.debug(x_gitlab_event)

        if not _validate_webhook_headers(processor, x_gitlab_event, x_gitlab_token):
            return StatusResponse(status="ignored", reason="unsupported_event", code=400)

        payload = await request.json()
        logger.debug(payload)

        attrs = payload["object_attributes"]
        project_info = payload["project"]

        project_id = project_info["id"]

        if payload["object_kind"] == "note":
            mr = payload["merge_request"]
            mr_iid = mr["iid"]
            processor.process_note_comment(project_id, mr_iid, payload)
            return StatusResponse(status="ok", code=200)

        if not processor.handle_merge_request_event(payload):
            return StatusResponse(status="ignored", code=400)


        last_commit = attrs["last_commit"]["id"]
        mr_iid = attrs["iid"]

        project_id = int(project_id)
        mr_iid = int(mr_iid)
        title = attrs["title"]
        description = attrs["description"]
        processor.process_merge_request(project_id, mr_iid, title, description, last_commit)

        return StatusResponse(status="ok", code=200)

    return app
