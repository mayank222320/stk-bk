import secrets

from fastapi import Header, HTTPException, status

from core.config import settings


async def require_token(x_api_token: str | None = Header(default=None)) -> None:
    api_token = settings().api_token
    if not api_token:                          # fail closed, never open
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API_TOKEN not configured")
    if not x_api_token or not secrets.compare_digest(x_api_token, api_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-API-Token")
