from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_csrf_tokens
from app.db.session import get_db
from app.models.user import User, UserSession
from app.services.auth_service import get_valid_session

SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def get_current_session(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> UserSession:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado. Realize login para continuar.",
        )

    session = get_valid_session(db, raw_token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada. Realize login novamente.",
        )

    if request.method.upper() not in SAFE_HTTP_METHODS:
        header_csrf = request.headers.get("X-CSRF-Token")
        if not verify_csrf_tokens(session.csrf_token, header_csrf):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Falha na validação de proteção CSRF.",
            )

    return session


def get_current_user(
    session: Annotated[UserSession, Depends(get_current_session)],
) -> User:
    return session.user
