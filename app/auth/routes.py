from typing import Any
from fastapi import APIRouter, Depends
from .auth import get_current_user

router = APIRouter()

@router.get("/me", summary="Get Current User", description="Returns the currently authenticated user's details.")
async def get_me(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """
    Returns the current user's information extracted from the Clerk token.
    """
    return current_user
