from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from clerk_backend_api.clerk import Clerk
from app.config.settings import settings

clerk = Clerk(secret_key=settings.clerk_secret_key)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_auth(request: Request):
    """
    FastAPI dependency to verify the Clerk JWT.
    """
    try:
        # The Clerk SDK automatically extracts the token from the header
        session_claims = clerk.verify_token(request.headers.get("authorization").split(" ")[1])
        request.state.auth = session_claims
        return session_claims
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Unauthorized: {e}")
