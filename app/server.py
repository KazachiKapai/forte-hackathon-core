from typing import Dict, Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .webhook_processor import WebhookProcessor


def create_app(processor: WebhookProcessor) -> FastAPI:
	app = FastAPI()

	@app.get("/health")
	async def health() -> Dict[str, str]:
		return {"status": "ok"}

	@app.post("/gitlab/webhook")
	async def gitlab_webhook(
		request: Request,
		x_gitlab_event: Optional[str] = Header(default=None, alias="X-Gitlab-Event"),
		x_gitlab_token: Optional[str] = Header(default=None, alias="X-Gitlab-Token"),
	) -> JSONResponse:
		try:
			processor.validate_secret(x_gitlab_token)
		except PermissionError:
			raise HTTPException(status_code=401, detail="Invalid webhook token")
		if x_gitlab_event != "Merge Request Hook":
			return JSONResponse({"status": "ignored", "reason": "unsupported_event"}, status_code=202)

		payload = await request.json()
		result = processor.handle_merge_request_event(payload)
		if result.get("status") == "error":
			code = result.get("code", 500)
			raise HTTPException(status_code=code, detail=result.get("message"))
		return JSONResponse(result)

	return app


