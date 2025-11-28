import os
from typing import Optional, Any
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
import httpx
from ..config.logging_config import configure_logging

_LOGGER = configure_logging()

# Initialize security scheme
security = HTTPBearer()

# Initialize Clerk SDK
clerk_client = Clerk(bearer_auth=os.getenv('CLERK_SECRET_KEY'))
frontend_url = os.getenv('FRONTEND_URL', '')
if not frontend_url:
    raise ValueError("FRONTEND_URL environment variable not set")

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict[str, Any]:
    """
    Verify the Clerk session token from the Authorization header.
    
    Returns:
        dict: Decoded token payload with user information
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    if not credentials:
        _LOGGER.warning("Missing authentication credentials")
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        # Create an httpx.Request object with the authorization header
        request = httpx.Request(
            method="GET",
            url="http://localhost",  # URL doesn't matter for token verification
            headers={"Authorization": f"Bearer {credentials.credentials}"}
        )
        
        # Authenticate the request
        options = AuthenticateRequestOptions(
            authorized_parties=[frontend_url]
        )
        request_state = clerk_client.authenticate_request(request, options)
        
        # Check if user is signed in
        if not request_state.is_signed_in or not request_state.payload:
            _LOGGER.warning(f"User not signed in or no payload. SignedIn: {request_state.is_signed_in}")
            raise HTTPException(
                status_code=401,
                detail="Not authenticated"
            )
        
        # Return the claims from the token
        return {
            "user_id": request_state.payload.get("sub"),
            "email": request_state.payload.get("email"),
            "claims": request_state.payload
        }
        
    except Exception as e:
        _LOGGER.error(f"Authentication failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=401,
            detail=f"Invalid authentication credentials: {str(e)}"
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict[str, Any]:
    """
    Dependency to get current authenticated user.
    Use this in your route handlers.
    """
    return verify_token(credentials)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[dict[str, Any]]:
    """
    Optional authentication dependency.
    Returns user info if authenticated, None otherwise.
    """
    if credentials is None:
        return None
    
    try:
        return verify_token(credentials)
    except HTTPException:
        return None