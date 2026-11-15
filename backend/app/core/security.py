import hashlib
import hmac
import ipaddress
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request

from app.core.config import settings

# Argon2id explícito conforme recomendação OWASP
password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(plain_password: str) -> str:
    """Gera hash seguro da senha usando Argon2id."""
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verifica a senha contra o hash Argon2id armazenado."""
    try:
        return password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def check_needs_rehash(password_hash: str) -> bool:
    """Verifica se o hash atual precisa ser atualizado para novos parâmetros."""
    return password_hasher.check_needs_rehash(password_hash)


def generate_session_token() -> str:
    """Gera um token de sessão opaco com alta entropia (256 bits)."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Gera um token CSRF criptograficamente seguro."""
    return secrets.token_urlsafe(32)


def hash_session_token(raw_token: str) -> str:
    """Calcula o SHA-256 do token de sessão para armazenamento seguro em banco."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def compute_rate_limit_key(raw_identifier: str) -> str:
    """Gera chave HMAC-SHA256 determinística para rate limiting sem persistir PII em texto claro."""
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        raw_identifier.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_csrf_tokens(cookie_or_session_token: str | None, header_token: str | None) -> bool:
    """Compara tokens CSRF em tempo constante."""
    if not cookie_or_session_token or not header_token:
        return False
    return secrets.compare_digest(cookie_or_session_token, header_token)


def get_session_expiry() -> datetime:
    """Calcula a data/hora de expiração da sessão em UTC."""
    return datetime.now(UTC) + timedelta(hours=settings.session_expire_hours)


def _parse_ip(raw_ip: str | None) -> str | None:
    if not raw_ip:
        return None
    cleaned = raw_ip.strip()
    if not cleaned:
        return None
    try:
        return str(ipaddress.ip_address(cleaned))
    except ValueError:
        return None


def _is_trusted_proxy(
    ip_str: str,
    trusted_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip_obj in network for network in trusted_networks)


def extract_trusted_client_ip(request: Request) -> str:
    """
    Extrai o endereço IP de origem do cliente com proteção contra spoofing de headers.

    Regras:
    1. Se o peer direto (request.client.host) NÃO pertencer a TRUSTED_PROXY_CIDRS,
       todos os cabeçalhos de encaminhamento são ignorados.
    2. Se o peer direto pertencer a TRUSTED_PROXY_CIDRS:
       - Quando TRUST_CF_CONNECTING_IP=true, prioriza CF-Connecting-IP se válido.
       - Caso contrário, percorre X-Forwarded-For da direita para a esquerda descartando
         proxies confiáveis, selecionando o último hop externo confiável.
       - Se não houver X-Forwarded-For válido, tenta X-Real-IP.
    """
    raw_peer = request.client.host if request.client else None
    peer_ip = _parse_ip(raw_peer)
    if peer_ip is None:
        return raw_peer or "unknown"

    trusted_nets = settings.trusted_proxy_networks
    if not _is_trusted_proxy(peer_ip, trusted_nets):
        return peer_ip

    if settings.trust_cf_connecting_ip:
        cf_ip = _parse_ip(request.headers.get("CF-Connecting-IP"))
        if cf_ip is not None:
            return cf_ip

    xff_header = request.headers.get("X-Forwarded-For")
    if xff_header:
        parsed_hops: list[str] = []
        for part in xff_header.split(","):
            parsed = _parse_ip(part)
            if parsed is not None:
                parsed_hops.append(parsed)
        if parsed_hops:
            for hop in reversed(parsed_hops):
                if not _is_trusted_proxy(hop, trusted_nets):
                    return hop
            return parsed_hops[0]

    x_real_ip = _parse_ip(request.headers.get("X-Real-IP"))
    if x_real_ip is not None:
        return x_real_ip

    return peer_ip
