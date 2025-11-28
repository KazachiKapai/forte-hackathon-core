import os
from typing import Optional, Any
from fastapi import HTTPException, Request, Security
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

def verify_token(request: Request, credentials: HTTPAuthorizationCredentials = Security(security)) -> dict[str, Any]:
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
		# Get origin and referer from headers
		origin = request.headers.get("origin")
		referer = request.headers.get("referer")
		
		# Build the list of authorized parties
		authorized_parties = [frontend_url]
		if origin:
			authorized_parties.append(origin)
		if referer:
			authorized_parties.append(referer)
			
		# Create an httpx.Request object with the authorization header
		httpx_req = httpx.Request(
			method="GET",
			url=str(request.url),
			headers={"Authorization": f"Bearer {credentials.credentials}"}
		)
		
		# Authenticate the request
		options = AuthenticateRequestOptions(
			authorized_parties=authorized_parties
		)
		request_state = clerk_client.authenticate_request(httpx_req, options)
		
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


def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials = Security(security)) -> dict[str, Any]:
	"""
	Dependency to get current authenticated user.
	Use this in your route handlers.
	"""
	return verify_token(request, credentials)


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[dict[str, Any]]:
    """
    Optional authentication dependency.
    Returns user info if authenticated, None otherwise.
    """
    if credentials is None:
        return None
    
    try:
        return verify_token(request, credentials)
    except HTTPException:
        return None