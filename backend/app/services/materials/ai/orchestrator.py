from __future__ import annotations

from collections.abc import Callable, Collection
import copy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging
from typing import Any
import uuid

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.base import utc_now
from app.models.material import (
    ApplicationMaterial,
    ApplicationMaterialVersion,
    MaterialVersionOrigin,
)
from app.models.user import User
from app.schemas.material import (
    MaterialAIEnhanceRequest,
    MaterialResponse,
    TargetLanguage,
)
from app.services.materials.ai._db_locks import (
    acquire_material_exclusivity_lock,
    run_atomic_with_sqlite_retry,
)
from app.services.materials.ai.ai_schemas import (
    AI_SUPPORTED_MATERIAL_TYPES,
    AIMaterialEnhanceOutput,
    AIMaterialTypeLiteral,
    serialize_canonical_provider_payload,
)
from app.services.materials.ai.context_builder import (
    DEFAULT_MAX_FACTS,
    DEFAULT_MAX_PAYLOAD_BYTES,
    build_authorized_ai_context,
)
from app.services.materials.ai.contracts import (
    AIGroundingRejectedError,
    AIOverlayConflictError,
    AIReviewStateError,
    AIStaleSourceVersionError,
    LLMMalformedOutputError,
    LLMProvider,
    LLMStructuredRequest,
    LLMStructuredResponse,
)
from app.services.materials.ai.execution_guard import execute_guarded_ai_call
from app.services.materials.ai.grounding_validator import (
    GroundingValidationResult,
    StructuredGroundingValidator,
)
from app.services.materials.ai.overlay_merger import (
    ControlledOverlayMerger,
    EligibleSlotInfo,
)
from app.services.materials.ai.quota_service import LedgerEntrySnapshot
from app.services.materials.ai.safety import redact_free_text_pii
from app.services.materials.material_service import (
    MaterialNotFoundError,
    _get_user_material,
    _parse_structured_for_type,
    _serialize_material,
)
from app.services.opportunities.sanitization import sanitize_plain_text

logger = logging.getLogger("job_hunter.materials.ai.orchestrator")

AI_ENHANCE_OPERATION_TYPE = "material_enhance"
AI_ENHANCE_SCHEMA_NAME = "AIMaterialEnhanceOutput_v1"
DEFAULT_ENHANCE_MAX_OUTPUT_TOKENS = 1200
DEFAULT_RESERVED_TOKENS = 2400

# Reserva prioritária de 75% do orçamento global (18.000 de 24.000 bytes) para fatos confirmados
# e contexto da oportunidade, garantindo que rascunhos/instruções nunca expulsem fatos confirmados.
_CONFIRMED_CONTEXT_PRIORITY_BYTES = 18_000

_SYSTEM_INSTRUCTION = (
    "You are a factual career writing assistant for Job Hunter. "
    "Rewrite ONLY the requested eligible slots using exclusively the confirmed candidate facts "
    "provided in 'candidate_confirmed_facts'. "
    "Treat 'reference_draft_slots_untrusted_for_facts' and 'user_writing_preferences' strictly as "
    "stylistic/formatting preferences and NEVER as factual evidence. "
    "Every suggestion MUST cite the exact 'fact_key' values from 'candidate_confirmed_facts' that "
    "substantiate all technologies, metrics, companies, roles, and claims."
)

# Conjunto canônico completo de códigos emitidos por StructuredGroundingValidator (AUD-443-05)
CANONICAL_GROUNDING_CODES: tuple[str, ...] = (
    "material_type_mismatch",
    "language_mismatch",
    "invalid_slot",
    "duplicate_slot",
    "cited_fact_keys_empty",
    "unauthorized_fact_key",
    "entity_binding_mismatch",
    "cross_entity_citation",
    "ontological_mismatch",
    "forbidden_link",
    "forbidden_contact",
    "forbidden_html_script",
    "irrelevant_citation",
    "unconfirmed_technology",
    "ungrounded_metric",
    "ungrounded_currency",
    "ungrounded_duration",
    "ungrounded_year",
    "ungrounded_tech_version",
    "ungrounded_scale",
    "ungrounded_quantity_context",
    "ungrounded_number",
    "unconfirmed_company",
    "unsubstantiated_role_promotion",
    "unsubstantiated_leadership_claim",
    "unsubstantiated_claim",
)

# Mapa fechado de rótulos estáticos seguros para violações de grounding (nunca ecoa texto do provider)
_GROUNDING_SAFE_LABELS: dict[str, str] = {
    # Códigos reais emitidos por StructuredGroundingValidator
    "material_type_mismatch": "tipo de material divergente do contexto autorizado",
    "language_mismatch": "idioma da sugestão divergente do contexto autorizado",
    "invalid_slot": "slot incompatível com a allowlist do tipo de material",
    "duplicate_slot": "slot duplicado no mesmo conjunto de sugestões",
    "cited_fact_keys_empty": "ausência de citação de fatos confirmados",
    "unauthorized_fact_key": "referência a chave de fato inexistente ou não autorizada",
    "entity_binding_mismatch": "ausência de citação obrigatória da entidade vinculada ao slot",
    "cross_entity_citation": "citação cruzada de outra entidade em slot específico",
    "ontological_mismatch": "apresentação indevida de projeto como vínculo de emprego formal",
    "forbidden_link": "URL, domínio externo ou link Markdown não permitido",
    "forbidden_contact": "dado de contato (e-mail ou telefone) não permitido na sugestão",
    "forbidden_html_script": "conteúdo HTML, SVG ou esquema ativo não permitido",
    "irrelevant_citation": "citação factual sem relação semântica com a afirmação técnica",
    "unconfirmed_technology": "tecnologia não comprovada nos fatos confirmados citados",
    "ungrounded_metric": "métrica percentual não fundamentada nos fatos citados",
    "ungrounded_currency": "valor monetário ou financeiro não fundamentado nos fatos citados",
    "ungrounded_duration": "duração ou tempo de experiência não fundamentado nos fatos citados",
    "ungrounded_year": "ano ou data não fundamentada nos fatos citados",
    "ungrounded_tech_version": "versão de tecnologia não fundamentada nos fatos citados",
    "ungrounded_scale": "escala ou volume não fundamentado nos fatos citados",
    "ungrounded_quantity_context": "quantidade ou contagem de entidades não fundamentada nos fatos citados",
    "ungrounded_number": "número ou quantitativo não fundamentado nos fatos citados",
    "unconfirmed_company": "organização ou empresa não fundamentada nos fatos citados",
    "unsubstantiated_role_promotion": "cargo ou senioridade não comprovada nos fatos citados",
    "unsubstantiated_leadership_claim": "afirmação de liderança ou gestão não comprovada nos fatos citados",
    "unsubstantiated_claim": "afirmação qualitativa exagerada sem evidência nos fatos citados",
    # Aliases legados de compatibilidade
    "unsafe_html_or_active_content": "conteúdo HTML, SVG ou esquema ativo não permitido",
    "unsafe_url_or_domain": "URL, domínio externo ou link Markdown não permitido",
    "unsafe_markdown_link": "link Markdown não permitido",
    "unsafe_email_in_output": "endereço de e-mail não permitido na sugestão",
    "unsafe_phone_in_output": "telefone não permitido na sugestão",
    "invalid_slot_for_material": "slot incompatível com a allowlist do tipo de material",
    "missing_citation": "ausência de citação de fatos confirmados",
    "unknown_fact_key": "referência a chave de fato inexistente ou não autorizada",
    "missing_entity_fact_citation": "ausência de citação obrigatória da entidade vinculada ao slot",
    "cross_entity_contamination": "citação cruzada de outra entidade em slot específico",
    "opportunity_requirement_claimed_as_experience": (
        "requisito da vaga afirmado como experiência sem comprovação"
    ),
    "ungrounded_scale_or_headcount": "escala ou tamanho de equipe não fundamentado nos fatos citados",
    "ungrounded_date_or_year": "ano ou data não fundamentada nos fatos citados",
    "ungrounded_monetary_value": "valor monetário ou financeiro não fundamentado nos fatos citados",
}


@dataclass(frozen=True, slots=True)
class _SourceMaterialFingerprint:
    """Impressão digital completa do estado do material, versão-fonte e histórico de vínculos."""

    material_id: uuid.UUID
    material_updated_at_iso: str
    source_version_id: uuid.UUID
    source_version_number: int
    source_origin: str
    source_is_approved: bool
    source_is_rejected: bool
    source_updated_at_iso: str
    source_content_sha256: str
    source_snapshot_sha256: str
    source_user_instructions: str | None
    material_target_language: str
    material_opportunity_id: uuid.UUID | None
    max_version_number: int
    max_active_version_number: int
    all_links_signature: tuple[tuple[str, str, str, str, bool, str, str], ...]


def _hash_json_mapping(raw_mapping: dict[str, Any] | None) -> str:
    canonical = serialize_canonical_provider_payload(raw_mapping or {})
    return hashlib.sha256(canonical).hexdigest()


def _compute_material_fingerprint(
    material: ApplicationMaterial,
    source_version: ApplicationMaterialVersion,
) -> _SourceMaterialFingerprint:
    max_ver = max((v.version_number for v in material.versions), default=0)
    max_active_ver = max(
        (v.version_number for v in material.versions if not getattr(v, "is_rejected", False)),
        default=0,
    )
    # Inclui TODOS os vínculos (ativos e históricos/desvinculados) para detectar ciclos link -> unlink (AUD-443-10)
    all_links = tuple(
        sorted(
            (
                str(lk.id),
                str(lk.application_id),
                str(lk.material_id),
                str(lk.version_id),
                lk.unlinked_at is None,
                lk.linked_at.isoformat() if lk.linked_at is not None else "",
                lk.unlinked_at.isoformat() if lk.unlinked_at is not None else "",
            )
            for lk in material.links
        )
    )
    mat_updated_iso = (
        material.updated_at.isoformat()
        if material.updated_at is not None
        else ""
    )
    ver_updated_iso = (
        source_version.updated_at.isoformat()
        if source_version.updated_at is not None
        else ""
    )
    return _SourceMaterialFingerprint(
        material_id=material.id,
        material_updated_at_iso=mat_updated_iso,
        source_version_id=source_version.id,
        source_version_number=source_version.version_number,
        source_origin=source_version.origin,
        source_is_approved=bool(source_version.is_approved),
        source_is_rejected=bool(getattr(source_version, "is_rejected", False)),
        source_updated_at_iso=ver_updated_iso,
        source_content_sha256=_hash_json_mapping(source_version.structured_content),
        source_snapshot_sha256=_hash_json_mapping(source_version.source_facts_snapshot),
        source_user_instructions=source_version.user_instructions,
        material_target_language=material.target_language,
        material_opportunity_id=material.opportunity_id,
        max_version_number=max_ver,
        max_active_version_number=max_active_ver,
        all_links_signature=all_links,
    )


def build_sanitized_grounding_error(
    validation_result: GroundingValidationResult,
    *,
    authorized_slot_ids: Collection[str] | None = None,
) -> AIGroundingRejectedError:
    """Constrói AIGroundingRejectedError com códigos estáticos, sem ecoar texto ou slot_id arbitrário do provider.

    Quando ``authorized_slot_ids`` é informado (conjunto de slots realmente existentes/elegíveis
    na versão de origem), qualquer ``slot_id`` não pertencente a esse conjunto é substituído por
    ``"unrecognized_slot"`` (AUD-443-04).
    """
    authorized_set: set[str] | None = (
        set(authorized_slot_ids) if authorized_slot_ids is not None else None
    )
    violation_pairs: list[tuple[str, str]] = []
    human_parts: list[str] = []

    for item in validation_result.flagged_items:
        # Caso 1: Falha estrutural de topo com chaves "error" e "detail" (ex.: material_type_mismatch, language_mismatch)
        top_error = item.get("error")
        if isinstance(top_error, str) and top_error.strip():
            code = top_error.strip().lower()
            label = _GROUNDING_SAFE_LABELS.get(
                code, "violação de fundamentação factual"
            )
            safe_code = code if code in _GROUNDING_SAFE_LABELS else "grounding_violation"
            pair = ("document", safe_code)
            if pair not in violation_pairs:
                violation_pairs.append(pair)
            if label not in human_parts:
                human_parts.append(label)
            continue

        # Caso 2: Falhas por item de sugestão ("slot_id" + "flags")
        raw_slot_id = str(item.get("slot_id") or "").strip()
        if not raw_slot_id:
            safe_slot_id = "unrecognized_slot"
        elif authorized_set is not None and raw_slot_id not in authorized_set:
            safe_slot_id = "unrecognized_slot"
        else:
            safe_slot_id = raw_slot_id

        raw_flags = item.get("flags") or []
        slot_labels: list[str] = []
        for raw_flag in raw_flags:
            code = str(raw_flag).split(":", 1)[0].strip().lower()
            label = _GROUNDING_SAFE_LABELS.get(
                code, "violação de fundamentação factual"
            )
            safe_code = code if code in _GROUNDING_SAFE_LABELS else "grounding_violation"
            pair = (safe_slot_id, safe_code)
            if pair not in violation_pairs:
                violation_pairs.append(pair)
            if label not in slot_labels:
                slot_labels.append(label)
        if slot_labels:
            human_parts.append(f"{safe_slot_id} ({'; '.join(slot_labels)})")

    if not human_parts:
        message = (
            "A sugestão gerada pela IA foi rejeitada pelo validador de fundamentação factual."
        )
    else:
        message = (
            "A sugestão gerada pela IA foi rejeitada por conter afirmações não comprovadas "
            f"nos fatos confirmados: {', '.join(human_parts)}."
        )

    return AIGroundingRejectedError(
        message,
        violation_codes=tuple(violation_pairs),
    )


def _truncate_str_preserving_chars(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[: max_chars - 3].rstrip() + "..."


def _build_budgeted_structured_input(
    *,
    base_context_payload: dict[str, Any],
    eligible_slots: tuple[EligibleSlotInfo, ...],
    user_instructions: str | None,
    max_total_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> dict[str, Any]:
    """Constrói structured_input respeitando teto global estrito em bytes UTF-8 (AUD-443-01).

    Ordem de prioridade:
    1. ``base_context_payload`` (``candidate_confirmed_facts`` e ``target_opportunity_context``)
       já construído com orçamento prioritário próprio e nunca reduzido aqui.
    2. Metadados estruturais obrigatórios do contrato (``eligible_target_slots`` e estrutura de
       ``reference_draft_slots_untrusted_for_facts``).
    3. Texto de rascunho atual dos slots elegíveis (``current_draft_text`` e ``question_text``),
       ajustado dinamicamente por busca binária em caracteres sobre medição exata de bytes UTF-8.
    4. ``user_writing_preferences`` (``user_instructions`` redigido contra PII), truncado de forma
       explícita e segura apenas quando necessário para respeitar ``max_total_bytes``.
    """
    if not eligible_slots:
        raise AIOverlayConflictError(
            "Nenhum slot elegível disponível para aprimoramento por IA nesta versão.",
            reason_code="no_eligible_slots",
        )

    sanitized_slots: list[dict[str, Any]] = []
    for slot in eligible_slots:
        clean_draft = sanitize_plain_text(slot.current_text, max_length=1500) or ""
        redacted_draft, _ = redact_free_text_pii(clean_draft)
        clean_q = ""
        if slot.question_text:
            raw_q = sanitize_plain_text(slot.question_text, max_length=400) or ""
            red_q, _ = redact_free_text_pii(raw_q)
            clean_q = red_q or ""
        sanitized_slots.append(
            {
                "slot_id": slot.slot_id,
                "draft_text": redacted_draft or "",
                "required_fact_key": slot.required_fact_key,
                "question_text": clean_q,
                "has_question": bool(slot.question_text),
            }
        )

    redacted_instructions: str | None = None
    if user_instructions and user_instructions.strip():
        clean_instr = sanitize_plain_text(user_instructions, max_length=1500)
        if clean_instr:
            red_instr, _ = redact_free_text_pii(clean_instr)
            if red_instr and red_instr.strip():
                redacted_instructions = red_instr.strip()

    eligible_ids = [s["slot_id"] for s in sanitized_slots]

    def _assemble_payload(draft_char_cap: int, instr_char_cap: int) -> dict[str, Any]:
        draft_entries: list[dict[str, Any]] = []
        for s in sanitized_slots:
            entry: dict[str, Any] = {
                "slot_id": s["slot_id"],
                "current_draft_text": _truncate_str_preserving_chars(
                    s["draft_text"], draft_char_cap
                ),
                "required_fact_key": s["required_fact_key"],
                "trust_level": "untrusted_draft_style_only",
            }
            if s["has_question"]:
                q_cap = min(400, max(32, draft_char_cap)) if draft_char_cap > 0 else 0
                entry["question_text"] = _truncate_str_preserving_chars(
                    s["question_text"], q_cap
                )
            draft_entries.append(entry)

        prefs_obj: dict[str, Any] | None = None
        if redacted_instructions is not None and instr_char_cap > 0:
            truncated_instr = _truncate_str_preserving_chars(
                redacted_instructions, instr_char_cap
            )
            if truncated_instr:
                prefs_obj = {
                    "instruction_text": truncated_instr,
                    "trust_level": "style_and_emphasis_only_not_factual_evidence",
                }

        return {
            **base_context_payload,
            "eligible_target_slots": eligible_ids,
            "reference_draft_slots_untrusted_for_facts": draft_entries,
            "user_writing_preferences": prefs_obj,
        }

    # 1. Verifica se o esqueleto estrutural mínimo cabe no orçamento global
    skeleton_payload = _assemble_payload(0, 0)
    skeleton_bytes = len(serialize_canonical_provider_payload(skeleton_payload))
    if skeleton_bytes > max_total_bytes:
        raise AIOverlayConflictError(
            "O conjunto mínimo de fatos confirmados e metadados excede o orçamento máximo de 24.000 bytes.",
            reason_code="payload_budget_exceeded",
        )

    # 2. Caso ideal: textos de rascunho completos + instruções completas cabem em max_total_bytes
    max_draft_len = max((len(s["draft_text"]) for s in sanitized_slots), default=0)
    max_instr_len = len(redacted_instructions) if redacted_instructions else 0
    full_payload = _assemble_payload(max_draft_len, max_instr_len)
    if len(serialize_canonical_provider_payload(full_payload)) <= max_total_bytes:
        return full_payload

    # 3. Reserva parcela justa para user_instructions (até 1.800 bytes ou 1/3 da folga disponível)
    remaining_after_skeleton = max_total_bytes - skeleton_bytes
    reserved_for_instr_bytes = (
        min(1800, remaining_after_skeleton // 3)
        if redacted_instructions is not None
        else 0
    )
    target_for_drafts = max_total_bytes - reserved_for_instr_bytes

    # Busca binária para determinar o maior draft_char_cap que cabe em target_for_drafts
    low_d, high_d = 0, max_draft_len
    best_draft_cap = 0
    while low_d <= high_d:
        mid_d = (low_d + high_d) // 2
        candidate_d = _assemble_payload(mid_d, 0)
        if len(serialize_canonical_provider_payload(candidate_d)) <= target_for_drafts:
            best_draft_cap = mid_d
            low_d = mid_d + 1
        else:
            high_d = mid_d - 1

    # 4. Busca binária para incluir o máximo de user_instructions no espaço restante até max_total_bytes
    best_instr_cap = 0
    if redacted_instructions is not None:
        low_i, high_i = 0, max_instr_len
        while low_i <= high_i:
            mid_i = (low_i + high_i) // 2
            candidate_i = _assemble_payload(best_draft_cap, mid_i)
            if len(serialize_canonical_provider_payload(candidate_i)) <= max_total_bytes:
                best_instr_cap = mid_i
                low_i = mid_i + 1
            else:
                high_i = mid_i - 1

    # 5. Se sobrou espaço após encaixar user_instructions, aproveita para expandir os drafts
    if best_draft_cap < max_draft_len:
        low_d2, high_d2 = best_draft_cap, max_draft_len
        while low_d2 <= high_d2:
            mid_d2 = (low_d2 + high_d2) // 2
            candidate_d2 = _assemble_payload(mid_d2, best_instr_cap)
            if len(serialize_canonical_provider_payload(candidate_d2)) <= max_total_bytes:
                best_draft_cap = mid_d2
                low_d2 = mid_d2 + 1
            else:
                high_d2 = mid_d2 - 1

    final_payload = _assemble_payload(best_draft_cap, best_instr_cap)
    final_bytes = len(serialize_canonical_provider_payload(final_payload))
    if final_bytes > max_total_bytes:
        raise AIOverlayConflictError(
            "Não foi possível montar o payload dentro do orçamento máximo de 24.000 bytes.",
            reason_code="payload_budget_exceeded",
        )
    return final_payload


def _resolve_session_factory(
    db: Session,
    explicit_factory: Callable[[], Session] | None,
) -> Callable[[], Session]:
    if explicit_factory is not None:
        return explicit_factory
    bind = db.get_bind()
    return lambda: Session(bind=bind, autoflush=False, expire_on_commit=False)


def enhance_material_version_with_ai(
    db: Session,
    user: User,
    *,
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: MaterialAIEnhanceRequest,
    session_factory: Callable[[], Session] | None = None,
    injected_provider: LLMProvider | None = None,
    settings_override: Settings | None = None,
    now_fn: Callable[[], datetime] | None = None,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> MaterialResponse:
    """Orquestra o aprimoramento assistido por IA de uma versão de material.

    Fluxo completo:
    1. Valida posse, estado da versão-fonte e elegibilidade de slots via ``ControlledOverlayMerger``.
    2. Constrói ``AuthorizedAIContext`` com orçamento prioritário para fatos confirmados e monta
       ``LLMStructuredRequest.structured_input`` comprovadamente ``<= 24.000`` bytes UTF-8.
    3. Captura impressão digital completa (fingerprint TOCTOU cobrindo conteúdo, status, versões e
       histórico completo de vínculos) e libera qualquer leitura pré-provider.
    4. Executa ``execute_guarded_ai_call`` (reserva cota + circuit breaker em Sessão #1; chama provider
       fora de transação; valida ``AIMaterialEnhanceOutput`` + ``StructuredGroundingValidator`` +
       ``ControlledOverlayMerger``).
    5. Em Sessão #2, adquire lock exclusivo sobre o material e versão-fonte, revalida fingerprint
       TOCTOU, persiste nova versão imutável ``origin="ai_assisted"`` (``is_approved=False``,
       ``is_rejected=False``), atualiza circuit breaker e confirma ledger (``version_id=new_version.id``)
       em UM ÚNICO commit atômico.
    """
    cfg = settings_override or get_settings()
    if not cfg.ai_assisted_enabled:
        from app.services.materials.ai.contracts import AIDisabledError

        raise AIDisabledError(
            "Aprimoramento assistido por IA está desabilitado nesta instância."
        )

    effective_max_total_bytes = max(
        1024, min(max_payload_bytes, DEFAULT_MAX_PAYLOAD_BYTES)
    )

    material = _get_user_material(db, user, material_id)
    source_version = next((v for v in material.versions if v.id == version_id), None)
    if source_version is None:
        raise MaterialNotFoundError("Versão de material não encontrada.")

    if getattr(source_version, "is_rejected", False):
        raise AIReviewStateError(
            "Não é permitido aprimorar com IA a partir de uma versão rejeitada."
        )

    max_active_ver = max(
        (v.version_number for v in material.versions if not getattr(v, "is_rejected", False)),
        default=0,
    )
    if source_version.version_number != max_active_ver:
        raise AIStaleSourceVersionError(
            "Apenas a versão ativa mais recente do material pode ser aprimorada com IA."
        )

    if material.material_type not in AI_SUPPORTED_MATERIAL_TYPES:
        raise AIReviewStateError(
            f"Tipo de material não suportado para aprimoramento por IA: '{material.material_type}'."
        )
    mat_type: AIMaterialTypeLiteral = material.material_type  # type: ignore[assignment]
    target_lang: TargetLanguage = (
        "en" if material.target_language == "en" else "pt-BR"
    )

    source_structured = _parse_structured_for_type(
        mat_type, source_version.structured_content
    )
    eligibility = ControlledOverlayMerger.resolve_eligible_slots(
        material_type=mat_type,
        source_content=source_structured,
        target_slot_ids=payload.target_slot_ids,
    )

    # Prioridade 1: Constrói o contexto factual confirmado reservando até 75% do orçamento global
    # para fatos confirmados e contexto da oportunidade (mínimo 1.024 bytes).
    context_priority_budget = max(
        1024,
        min(_CONFIRMED_CONTEXT_PRIORITY_BYTES, (effective_max_total_bytes * 3) // 4),
    )
    ai_context = build_authorized_ai_context(
        db,
        user,
        material_type=mat_type,
        opportunity=material.opportunity,
        application=None,
        target_language=target_lang,
        max_facts=DEFAULT_MAX_FACTS,
        max_payload_bytes=context_priority_budget,
    )
    if not ai_context.authorized_facts:
        raise AIOverlayConflictError(
            "Não há fatos confirmados suficientes dentro do orçamento de contexto para aprimorar este material.",
            reason_code="insufficient_confirmed_facts_in_budget",
        )

    authorized_fact_keys = ai_context.all_fact_keys()
    # Filtra slots entity_bound cuja entidade tenha sido truncada pelo limite de 60 fatos / bytes
    reachable_eligible_slots: list[EligibleSlotInfo] = []
    for slot in eligibility.eligible_slots:
        if slot.required_fact_key is not None and slot.required_fact_key not in authorized_fact_keys:
            if payload.target_slot_ids is not None:
                raise AIOverlayConflictError(
                    f"O fato confirmado vinculado ao slot '{slot.slot_id}' não pôde ser incluído no orçamento de contexto.",
                    slot_id=slot.slot_id,
                    reason_code="entity_fact_truncated_by_budget",
                )
            continue
        reachable_eligible_slots.append(slot)

    if not reachable_eligible_slots:
        raise AIOverlayConflictError(
            "Nenhum slot elegível possui fatos confirmados disponíveis dentro do orçamento de contexto.",
            reason_code="no_eligible_slots",
        )

    effective_instructions = (
        payload.user_instructions
        if payload.user_instructions is not None
        else source_version.user_instructions
    )

    # Prioridades 2, 3 e 4: Monta structured_input respeitando len(serialize_canonical_provider_payload) <= 24.000
    structured_input = _build_budgeted_structured_input(
        base_context_payload=ai_context.to_provider_payload(),
        eligible_slots=tuple(reachable_eligible_slots),
        user_instructions=effective_instructions,
        max_total_bytes=effective_max_total_bytes,
    )
    assert (
        len(serialize_canonical_provider_payload(structured_input))
        <= effective_max_total_bytes
    )

    authorized_slot_ids = frozenset(s.slot_id for s in reachable_eligible_slots)
    effective_target_slot_ids = [s.slot_id for s in reachable_eligible_slots]
    pre_fingerprint = _compute_material_fingerprint(material, source_version)

    # Libera qualquer transação de leitura na sessão do endpoint antes de abrir Sessão #1 e chamar o provider
    if db.in_transaction() and not (db.new or db.dirty or db.deleted):
        db.commit()

    llm_request = LLMStructuredRequest(
        operation_type=AI_ENHANCE_OPERATION_TYPE,
        schema_name=AI_ENHANCE_SCHEMA_NAME,
        response_schema=AIMaterialEnhanceOutput.model_json_schema(),
        system_instruction=_SYSTEM_INSTRUCTION,
        structured_input=structured_input,
        max_output_tokens=DEFAULT_ENHANCE_MAX_OUTPUT_TOKENS,
        temperature=0.2,
    )

    grounding_validator = StructuredGroundingValidator()

    def _validate_provider_response(
        llm_response: LLMStructuredResponse,
    ) -> AIMaterialEnhanceOutput:
        try:
            parsed_output = AIMaterialEnhanceOutput.model_validate(llm_response.data)
        except ValidationError as exc:
            raise LLMMalformedOutputError(
                "A resposta estruturada do provider violou o contrato de sugestões de IA."
            ) from exc

        if parsed_output.material_type != mat_type:
            raise LLMMalformedOutputError(
                "O tipo de material retornado pelo provider diverge do material solicitado."
            )

        grounding_res = grounding_validator.validate(
            context=ai_context,
            output=parsed_output,
        )
        if not grounding_res.is_valid:
            raise build_sanitized_grounding_error(
                grounding_res,
                authorized_slot_ids=authorized_slot_ids,
            )

        # Valida elegibilidade e aplicação sobre cópia em memória antes de abrir a Sessão #2
        ControlledOverlayMerger.apply_overlay(
            material_type=mat_type,
            source_content=source_structured,
            ai_output=parsed_output,
            target_slot_ids=(
                payload.target_slot_ids
                if payload.target_slot_ids is not None
                else None
            ),
        )
        return parsed_output

    def _persist_new_version_in_post_tx(
        db_post: Session,
        reservation: LedgerEntrySnapshot,
        llm_response: LLMStructuredResponse,
        validated_output: AIMaterialEnhanceOutput,
    ) -> tuple[uuid.UUID, uuid.UUID]:
        acquire_material_exclusivity_lock(
            db_post,
            user_id=user.id,
            material_id=material_id,
            source_version_id=version_id,
            allow_transaction_reset=False,
        )
        try:
            locked_material = _get_user_material(
                db_post, user, material_id, for_update=True
            )
        except MaterialNotFoundError as exc:
            raise AIStaleSourceVersionError(
                "O material de origem foi removido concorrentemente durante o processamento da IA."
            ) from exc

        locked_source = next(
            (v for v in locked_material.versions if v.id == version_id), None
        )
        if locked_source is None:
            raise AIStaleSourceVersionError(
                "A versão de origem não está mais disponível para aprimoramento."
            )

        post_fingerprint = _compute_material_fingerprint(
            locked_material, locked_source
        )
        if post_fingerprint != pre_fingerprint:
            raise AIStaleSourceVersionError(
                "A versão de origem ou o estado do material foi modificado concorrentemente durante o processamento da IA."
            )

        locked_structured = _parse_structured_for_type(
            mat_type, locked_source.structured_content
        )
        merge_result = ControlledOverlayMerger.apply_overlay(
            material_type=mat_type,
            source_content=locked_structured,
            ai_output=validated_output,
            target_slot_ids=(
                payload.target_slot_ids
                if payload.target_slot_ids is not None
                else None
            ),
        )

        current_max = db_post.scalar(
            select(
                func.coalesce(func.max(ApplicationMaterialVersion.version_number), 0)
            ).where(ApplicationMaterialVersion.material_id == locked_material.id)
        )
        next_number = int(current_max or 0) + 1

        new_snapshot = copy.deepcopy(dict(locked_source.source_facts_snapshot or {}))
        new_snapshot["ai_overlay"] = {
            "ledger_entry_id": str(reservation.id),
            "source_version_id": str(locked_source.id),
            "source_version_number": locked_source.version_number,
            "provider_name": llm_response.provider_name,
            "model_name": llm_response.model_name,
            "eligible_slot_ids": effective_target_slot_ids,
            "applied_slot_ids": list(merge_result.applied_slot_ids),
            "preserved_user_authored_slot_ids": list(
                merge_result.preserved_user_authored_slot_ids
            ),
            "preserved_manual_edit_slot_ids": list(
                merge_result.preserved_manual_edit_slot_ids
            ),
        }

        now = utc_now()
        new_version_id = uuid.uuid4()
        new_version = ApplicationMaterialVersion(
            id=new_version_id,
            material_id=locked_material.id,
            version_number=next_number,
            origin=MaterialVersionOrigin.AI_ASSISTED.value,
            parent_version_id=locked_source.id,
            user_instructions=effective_instructions,
            structured_content=merge_result.merged_content.model_dump(mode="json"),
            source_facts_snapshot=new_snapshot,
            unconfirmed_warnings=copy.deepcopy(
                list(locked_source.unconfirmed_warnings or [])
            ),
            missing_requirements=copy.deepcopy(
                list(locked_source.missing_requirements or [])
            ),
            is_approved=False,
            approved_at=None,
            is_rejected=False,
            rejected_at=None,
            created_at=now,
            updated_at=now,
        )
        locked_material.updated_at = now
        db_post.add(new_version)
        db_post.flush()
        return new_version_id, new_version_id

    def _load_serialized_material(
        db_loader: Session,
        _created_version_id: uuid.UUID | None,
    ) -> MaterialResponse:
        reloaded = _get_user_material(db_loader, user, material_id)
        return _serialize_material(reloaded)

    factory = _resolve_session_factory(db, session_factory)
    execution_result = execute_guarded_ai_call(
        session_factory=factory,
        user_id=user.id,
        request=llm_request,
        reserved_tokens=DEFAULT_RESERVED_TOKENS,
        material_id=material_id,
        version_id=version_id,
        response_validator=_validate_provider_response,
        post_transaction_persister=_persist_new_version_in_post_tx,
        after_commit_loader=_load_serialized_material,
        injected_provider=injected_provider,
        settings_override=cfg,
        now_fn=now_fn,
    )

    db.expire_all()
    if isinstance(execution_result.persisted_artifact, MaterialResponse):
        return execution_result.persisted_artifact
    return _serialize_material(_get_user_material(db, user, material_id))


def reject_ai_assisted_version(
    db: Session,
    user: User,
    *,
    material_id: uuid.UUID,
    version_id: uuid.UUID,
) -> MaterialResponse:
    """Marca uma versão ai_assisted não aprovada como rejeitada sem excluí-la fisicamente.

    Preserva a trilha de auditoria em application_material_versions e o vínculo em
    ai_usage_ledger.version_id, restaurando a versão ativa anterior ao topo de versions.
    """

    def _tx() -> MaterialResponse:
        material = _get_user_material(db, user, material_id, for_update=True)
        version = next((v for v in material.versions if v.id == version_id), None)
        if version is None:
            raise MaterialNotFoundError("Versão de material não encontrada.")

        if version.origin != MaterialVersionOrigin.AI_ASSISTED.value:
            raise AIReviewStateError(
                "Apenas versões geradas por IA assistida ('ai_assisted') podem ser rejeitadas."
            )
        if getattr(version, "is_rejected", False):
            raise AIReviewStateError(
                "Esta versão de IA assistida já foi rejeitada anteriormente."
            )
        if version.is_approved:
            raise AIReviewStateError(
                "Versão já aprovada é imutável e não pode ser rejeitada."
            )

        is_linked = any(link.version_id == version.id for link in material.links)
        if is_linked:
            raise AIReviewStateError(
                "Versão vinculada a candidatura não pode ser rejeitada."
            )

        has_dependent_children = any(
            v.parent_version_id == version.id for v in material.versions
        )
        if has_dependent_children:
            raise AIReviewStateError(
                "Não é possível rejeitar uma versão que já possui versões derivadas dependentes."
            )

        now = utc_now()
        version.is_rejected = True
        version.rejected_at = now
        version.updated_at = now
        material.updated_at = now
        db.commit()
        db.expire_all()

        reloaded = _get_user_material(db, user, material.id)
        return _serialize_material(reloaded)

    return run_atomic_with_sqlite_retry(db, _tx)
