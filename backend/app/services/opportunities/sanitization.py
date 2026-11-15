import hashlib
import html
import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

MAX_DESCRIPTION_LENGTH = 15000
MAX_TITLE_LENGTH = 255
TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "source",
    "fbclid",
    "gclid",
}

_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style|iframe|object|embed)[^>]*>.*?</\1>")
_HTML_BREAK_RE = re.compile(r"(?i)<(br\s*/?|/p|/div|/li|/h[1-6]|tr)[^>]*>")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def sanitize_external_html_text(
    raw_value: str | None,
    *,
    max_length: int = MAX_DESCRIPTION_LENGTH,
) -> str | None:
    """Remove scripts, tags HTML perigosas e controla o tamanho de textos externos."""
    if not raw_value or not isinstance(raw_value, str):
        return None

    cleaned = _SCRIPT_STYLE_RE.sub(" ", raw_value)
    cleaned = _HTML_BREAK_RE.sub("\n", cleaned)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = html.unescape(cleaned)

    lines = [_MULTI_SPACE_RE.sub(" ", line).strip() for line in cleaned.splitlines()]
    normalized = "\n".join(line for line in lines if line)
    normalized = _MULTI_NEWLINE_RE.sub("\n\n", normalized).strip()

    if not normalized:
        return None
    if len(normalized) > max_length:
        return normalized[: max_length - 3].rstrip() + "..."
    return normalized


def sanitize_plain_text(
    raw_value: str | None,
    *,
    max_length: int = MAX_TITLE_LENGTH,
) -> str | None:
    if not raw_value or not isinstance(raw_value, str):
        return None
    text = sanitize_external_html_text(raw_value, max_length=max_length)
    if text is None:
        return None
    single_line = _MULTI_SPACE_RE.sub(" ", text.replace("\n", " ")).strip()
    if not single_line:
        return None
    if len(single_line) > max_length:
        return single_line[: max_length - 3].rstrip() + "..."
    return single_line


def is_forbidden_ssrf_host(hostname: str) -> bool:
    host = hostname.strip().lower().rstrip(".")
    if not host:
        return True
    if host in {"localhost", "localhost.localdomain", "metadata.google.internal"}:
        return True
    if host.endswith((".local", ".internal", ".localhost")):
        return True

    # Verifica endereços IP literais (IPv4/IPv6), bloqueando redes privadas, loopback e link-local
    try:
        ip_obj = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False

    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def validate_safe_external_url(
    raw_url: str,
    *,
    allow_localhost: bool = False,
) -> str:
    """
    Valida que a URL utiliza estritamente http:// ou https://, sem credenciais embutidas
    nem destinos locais/link-local de SSRF (ex: 169.254.169.254).
    """
    candidate = raw_url.strip()
    if not candidate:
        raise ValueError("URL não pode estar vazia.")

    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Somente URLs com esquema http:// ou https:// são permitidas.")

    if not parsed.netloc or not parsed.hostname:
        raise ValueError("URL externa deve conter um domínio ou host válido.")

    if parsed.username or parsed.password:
        raise ValueError("URLs com credenciais embutidas não são permitidas.")

    if not allow_localhost and is_forbidden_ssrf_host(parsed.hostname):
        raise ValueError(
            "Destino de URL inválido: endereços locais, privados ou de metadados são bloqueados."
        )

    if len(candidate) > 1000:
        raise ValueError("URL excede o limite máximo de 1000 caracteres.")
    return candidate


def normalize_canonical_url(raw_url: str) -> str:
    """Normaliza URL para deduplicação removendo parâmetros de rastreamento e fragmentos."""
    validated = validate_safe_external_url(raw_url)
    parsed = urlparse(validated)
    filtered_query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_QUERY_PARAMS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(sorted(filtered_query)),
            "",
        )
    )


def normalize_string_list(items: list[str] | None, *, max_items: int = 30) -> list[str]:
    if not items:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        cleaned = sanitize_plain_text(str(raw), max_length=100)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= max_items:
            break
    return result


def compute_opportunity_content_hash(
    *,
    title: str,
    company_name: str | None,
    source_url: str,
    work_mode: str,
    employment_type: str,
    location_text: str | None,
    description: str | None,
) -> str:
    payload = "|".join(
        [
            title.strip().lower(),
            (company_name or "").strip().lower(),
            source_url.strip().lower(),
            work_mode.strip().lower(),
            employment_type.strip().lower(),
            (location_text or "").strip().lower(),
            (description or "")[:1000].strip().lower(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
