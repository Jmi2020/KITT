"""OAuth2 token endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from common.security import create_access_token

router = APIRouter(tags=["auth"])


@router.post("/token")
async def issue_token(form_data: OAuth2PasswordRequestForm = None):  # type: ignore[assignment]
    if not form_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid form data")

    # Placeholder authentication: accept any non-empty password.
    if not form_data.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(form_data.username)
    return {"access_token": token, "token_type": "bearer"}
