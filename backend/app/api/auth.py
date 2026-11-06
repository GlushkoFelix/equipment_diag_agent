"""认证端点（ARCH §5.4.1）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app import security
from app.schemas.api import AuthResponse, LoginRequest, RegisterRequest

router = APIRouter(tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=security.COOKIE_NAME,
        value=token,
        max_age=86400,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(body: RegisterRequest, request: Request, response: Response):
    user, token = security.register_user(request.app.state.db, body.username, body.password)
    _set_cookie(response, token)
    return {"user": user}


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response):
    user, token = security.login_user(
        request.app.state.db, body.username, body.password, request.app.state.settings
    )
    _set_cookie(response, token)
    return {"user": user}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, user: dict = Depends(security.current_user)):
    token = request.cookies.get(security.COOKIE_NAME)
    if token:
        security.logout(request.app.state.db, token)
    response.delete_cookie(security.COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=AuthResponse)
def me(request: Request, user: dict = Depends(security.current_user)):
    row = request.app.state.db.connection().execute(
        "SELECT * FROM users WHERE user_id=?", (user["user_id"],)
    ).fetchone()
    return {"user": security.public_user(row)}
