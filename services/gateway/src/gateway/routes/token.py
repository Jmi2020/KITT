"""OAuth2 token endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from common.security import check_secret, create_access_token, get_admin_credentials

router = APIRouter(tags=["auth"])


@router.post("/token")
async def issue_token(form_data: OAuth2PasswordRequestForm = None):  # type: ignore[assignment]
    if not form_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid form data"
        )

    admins = get_admin_credentials()

    if admins:
        stored_secret = admins.get(form_data.username)
        if not stored_secret or not check_secret(form_data.password, stored_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        token = create_access_token(form_data.username, roles=["admin"])
        return {"access_token": token, "token_type": "bearer"}

    # Fallback development mode: accept any non-empty password.
    if not form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    token = create_access_token(form_data.username, roles=["user"])
    return {"access_token": token, "token_type": "bearer"}
