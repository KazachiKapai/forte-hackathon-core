import os
import httpx
from fastapi import HTTPException, Request
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
import logging

logger = logging.getLogger(__name__)

clerk = Clerk(bearer_auth=os.environ.get("CLERK_SECRET_KEY"))
frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')

logger.info(f"Clerk middleware initialized with FRONTEND_URL={frontend_url}")

async def get_auth(request: Request):
    """
    FastAPI dependency to verify the Clerk JWT using authenticate_request.
    """
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            logger.warning("Missing authorization header")
            raise HTTPException(status_code=401, detail="Missing authorization header")
        
        logger.debug(f"Authorization header present: {auth_header[:50]}...")
        
        # Create an httpx.Request object with the authorization header
        httpx_request = httpx.Request(
            method="GET",
            url="http://localhost",  # URL doesn't matter for token verification
            headers={"Authorization": auth_header}
        )
        
        # Authenticate the request using Clerk's authenticate_request
        # Get origin and referer from headers
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        
        # Build the list of authorized parties
        authorized_parties = [frontend_url]
        if origin:
            authorized_parties.append(origin)
        if referer:
            authorized_parties.append(referer)
            
        options = AuthenticateRequestOptions(
            authorized_parties=authorized_parties
        )
        logger.debug(f"Authenticating with authorized_parties={[frontend_url]}")
        request_state = clerk.authenticate_request(httpx_request, options)
        
        logger.debug(f"Request state: is_signed_in={request_state.is_signed_in}, has_payload={request_state.payload is not None}")
        
        # Check if user is signed in
        if not request_state.is_signed_in or not request_state.payload:
            logger.warning(f"Authentication failed: is_signed_in={request_state.is_signed_in}, payload={request_state.payload}")
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # Return the claims from the token
        session_claims = {
            "user_id": request_state.payload.get("sub"),
            "email": request_state.payload.get("email"),
            "claims": request_state.payload
        }
        logger.info(f"Authentication successful for user_id={session_claims['user_id']}")
        request.state.auth = session_claims
        return session_claims
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail=f"Unauthorized: {e}")
