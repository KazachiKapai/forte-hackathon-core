import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.auth import get_current_user, get_current_user_optional
from app.config.config import AppConfig
from app.config.logging_config import configure_logging

load_dotenv()
configure_logging()

app = FastAPI(title="Your API with Clerk Auth")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv('FRONTEND_URL', '')],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public route (no authentication required)
@app.get("/")
async def root():
    return {"message": "Welcome to the API"}

# Protected route (authentication required)
@app.get("/protected")
async def protected_route(current_user: dict = Depends(get_current_user)):
    return {
        "message": "This is a protected route",
        "user_id": current_user["user_id"],
        "email": current_user["email"]
    }

# Optional authentication route
@app.get("/optional-auth")
async def optional_auth_route(current_user: dict = Depends(get_current_user_optional)):
    if current_user:
        return {
            "message": "You are authenticated",
            "user_id": current_user["user_id"]
        }
    else:
        return {"message": "You are not authenticated"}

# Example: Get user profile
@app.get("/me")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    return {
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "all_claims": current_user["claims"]
    }