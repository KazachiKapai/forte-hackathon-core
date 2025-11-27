from app.config import AppConfig
from app.server.http import create_app
from main import build_services

# Construct FastAPI ASGI app for Vercel Python runtime.
_cfg = AppConfig()
_processor = build_services(_cfg)
app = create_app(_processor)


