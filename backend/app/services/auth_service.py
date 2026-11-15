from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    check_needs_rehash,
    compute_rate_limit_key,
    generate_csrf_token,
    generate_session_token,
    get_session_expiry,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.models.user import AccountStatus, AuthRateLimit, User, UserSession

# Hash dummy pré-computado para mitigar ataques de enumeração por tempo de resposta
_DUMMY_ARGON2_HASH = hash_password("dummy-mitigation-password-do-not-use")


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _rate_limit_scopes(client_ip: str, email: str) -> list[tuple[str, str, int]]:
    normalized_email = email.strip().lower()
    normalized_ip = (client_ip or "unknown").strip()
    return [
        (
            "ip_account",
            compute_rate_limit_key(f"ip_account:{normalized_ip}|{normalized_email}"),
            settings.login_account_ip_max_attempts,
        ),
        (
            "ip",
            compute_rate_limit_key(f"ip:{normalized_ip}"),
            settings.login_ip_max_attempts,
        ),
    ]


def check_login_rate_limit(
    db: Session,
    client_ip: str,
    email: str,
    now: datetime | None = None,
) -> int | None:
    """
    Verifica se a origem ou o par (origem, conta) está em período de cooldown.
    Retorna os segundos restantes de bloqueio (Retry-After) ou None se liberado.
    """
    current_time = _ensure_utc(now or datetime.now(UTC))
    max_retry_after: int | None = None

    for scope_type, scope_key, _ in _rate_limit_scopes(client_ip, email):
        record = db.execute(
            select(AuthRateLimit).where(
                AuthRateLimit.scope_type == scope_type,
                AuthRateLimit.scope_key == scope_key,
            )
        ).scalar_one_or_none()

        if record is None or record.blocked_until is None:
            continue

        blocked_until = _ensure_utc(record.blocked_until)
        if blocked_until > current_time:
            remaining = max(1, int((blocked_until - current_time).total_seconds()))
            if max_retry_after is None or remaining > max_retry_after:
                max_retry_after = remaining

    return max_retry_after


def record_login_failure(
    db: Session,
    client_ip: str,
    email: str,
    now: datetime | None = None,
) -> int | None:
    """
    Registra uma falha de autenticação de forma persistente (PostgreSQL/SQLite),
    aplicando cooldown temporário quando o limite é atingido.
    """
    current_time = _ensure_utc(now or datetime.now(UTC))
    triggered_retry_after: int | None = None

    for scope_type, scope_key, max_attempts in _rate_limit_scopes(client_ip, email):
        record = db.execute(
            select(AuthRateLimit).where(
                AuthRateLimit.scope_type == scope_type,
                AuthRateLimit.scope_key == scope_key,
            )
        ).scalar_one_or_none()

        if record is None:
            record = AuthRateLimit(
                scope_type=scope_type,
                scope_key=scope_key,
                failure_count=1,
                window_started_at=current_time,
                blocked_until=None,
                last_attempt_at=current_time,
            )
            db.add(record)
        else:
            window_started = _ensure_utc(record.window_started_at)
            window_expired = (
                current_time - window_started
            ).total_seconds() >= settings.login_rate_limit_window_seconds
            cooldown_expired = (
                record.blocked_until is None
                or _ensure_utc(record.blocked_until) <= current_time
            )

            if window_expired and cooldown_expired:
                record.failure_count = 1
                record.window_started_at = current_time
                record.blocked_until = None
            elif record.blocked_until is not None and cooldown_expired:
                # Após o término do cooldown, reinicia a contagem para evitar bloqueio permanente
                record.failure_count = 1
                record.window_started_at = current_time
                record.blocked_until = None
            else:
                record.failure_count += 1

            record.last_attempt_at = current_time

        if record.failure_count >= max_attempts:
            record.blocked_until = current_time + timedelta(
                seconds=settings.login_cooldown_seconds
            )
            triggered_retry_after = settings.login_cooldown_seconds

    db.commit()
    return triggered_retry_after


def reset_login_rate_limit_on_success(
    db: Session,
    client_ip: str,
    email: str,
) -> None:
    """Limpa o contador do par (origem, conta) após autenticação bem-sucedida."""
    normalized_email = email.strip().lower()
    normalized_ip = (client_ip or "unknown").strip()
    ip_account_key = compute_rate_limit_key(
        f"ip_account:{normalized_ip}|{normalized_email}"
    )
    db.execute(
        delete(AuthRateLimit).where(
            AuthRateLimit.scope_type == "ip_account",
            AuthRateLimit.scope_key == ip_account_key,
        )
    )
    db.commit()


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    normalized_email = email.strip().lower()
    stmt = select(User).where(User.email == normalized_email)
    user = db.execute(stmt).scalar_one_or_none()

    if user is None:
        verify_password(password, _DUMMY_ARGON2_HASH)
        return None

    if not verify_password(password, user.password_hash):
        return None

    if user.account_status != AccountStatus.ACTIVE.value:
        return None

    if check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
        db.refresh(user)

    return user


def create_user_session(
    db: Session,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[UserSession, str]:
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    csrf_token = generate_csrf_token()

    user_session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        csrf_token=csrf_token,
        expires_at=get_session_expiry(),
        user_agent=(user_agent or "")[:512] if user_agent else None,
        ip_address=(ip_address or "")[:64] if ip_address else None,
    )
    db.add(user_session)
    db.commit()
    db.refresh(user_session)
    return user_session, raw_token


def get_valid_session(db: Session, raw_token: str) -> UserSession | None:
    if not raw_token:
        return None
    token_hash = hash_session_token(raw_token)
    stmt = select(UserSession).where(UserSession.token_hash == token_hash)
    session = db.execute(stmt).scalar_one_or_none()

    if session is None:
        return None

    if session.revoked_at is not None:
        return None

    now = datetime.now(UTC)
    expires_at = _ensure_utc(session.expires_at)

    if expires_at <= now:
        return None

    if session.user.account_status != AccountStatus.ACTIVE.value:
        return None

    return session


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = datetime.now(UTC)
    db.commit()


def create_user_account(
    db: Session,
    *,
    email: str,
    display_name: str,
    password: str,
    is_admin: bool = False,
) -> User:
    normalized_email = email.strip().lower()
    clean_name = display_name.strip()

    if len(password) < 8:
        raise ValueError("A senha deve possuir no mínimo 8 caracteres.")
    if not clean_name:
        raise ValueError("O nome de exibição é obrigatório.")

    existing = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"Já existe um usuário cadastrado com o e-mail '{normalized_email}'.")

    user = User(
        email=normalized_email,
        display_name=clean_name,
        password_hash=hash_password(password),
        account_status=AccountStatus.ACTIVE.value,
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
