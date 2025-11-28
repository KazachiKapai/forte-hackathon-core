import os
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from clerk_backend_api import Clerk

clerk = Clerk(bearer_auth=os.environ.get("CLERK_SECRET_KEY"))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_auth(request: Request):
    """
    FastAPI dependency to verify the Clerk JWT.
    """
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing authorization header")
        
        token = auth_header.split(" ")[1] if " " in auth_header else auth_header
        session_claims = clerk.verify_token(token)
        request.state.auth = session_claims
        return session_claims
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Unauthorized: {e}")
