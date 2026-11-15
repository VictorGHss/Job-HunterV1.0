from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_session
from app.core.config import settings
from app.core.security import extract_trusted_client_ip
from app.db.session import get_db
from app.models.user import UserSession
from app.schemas.auth import AuthSessionResponse, LoginRequest, UserResponse
from app.services.auth_service import (
    authenticate_user,
    check_login_rate_limit,
    create_user_session,
    record_login_failure,
    reset_login_rate_limit_on_success,
    revoke_session,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    summary="Autentica um usuário e inicia uma sessão segura com cookie HttpOnly",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthSessionResponse:
    client_ip = extract_trusted_client_ip(request)

    retry_after = check_login_rate_limit(db, client_ip, payload.email)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de autenticação. Aguarde antes de tentar novamente.",
            headers={"Retry-After": str(retry_after)},
        )

    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        record_login_failure(db, client_ip, payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas ou conta indisponível.",
        )

    reset_login_rate_limit_on_success(db, client_ip, payload.email)

    user_agent = request.headers.get("user-agent")
    session, raw_token = create_user_session(
        db,
        user=user,
        user_agent=user_agent,
        ip_address=client_ip,
    )

    max_age_seconds = settings.session_expire_hours * 3600

    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=max_age_seconds,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=session.csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=max_age_seconds,
        path="/",
    )

    return AuthSessionResponse(
        authenticated=True,
        user=UserResponse.model_validate(user),
        csrf_token=session.csrf_token,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoga a sessão atual no banco de dados e remove os cookies de autenticação",
)
def logout(
    response: Response,
    session: Annotated[UserSession, Depends(get_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    revoke_session(db, session)
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    response.delete_cookie(key=settings.csrf_cookie_name, path="/")
    return {"message": "Sessão encerrada com sucesso."}


@router.get(
    "/me",
    response_model=AuthSessionResponse,
    summary="Retorna o usuário autenticado e o token CSRF ativo da sessão",
)
def get_me(
    session: Annotated[UserSession, Depends(get_current_session)],
) -> AuthSessionResponse:
    return AuthSessionResponse(
        authenticated=True,
        user=UserResponse.model_validate(session.user),
        csrf_token=session.csrf_token,
    )
