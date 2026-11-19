from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.material import TargetLanguage

AI_SUPPORTED_MATERIAL_TYPES = (
    "resume",
    "cover_letter",
    "recruiter_message",
    "freelance_proposal",
    "application_answers",
)

AIMaterialTypeLiteral = Literal[
    "resume",
    "cover_letter",
    "recruiter_message",
    "freelance_proposal",
    "application_answers",
]

FactEntityTypeLiteral = Literal[
    "profile",
    "experience",
    "project",
    "education",
    "skill",
    "language",
]

_SAFE_SLOT_RE = re.compile(r"^[A-Za-z0-9_:-]+$")
_ENTITY_ID_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FACT_KEY_RE = re.compile(
    r"^(profile|experience|project|education|skill|language):[A-Za-z0-9_-]{1,64}$"
)

# Allowlist explícita de slots narrativos estáticos por tipo de material,
# derivada estritamente dos contratos de structured_content em app/schemas/material.py.
# Campos de controle, metadados, contato/header e pendências comerciais são excluídos.
STATIC_ALLOWED_SLOTS_BY_MATERIAL: dict[AIMaterialTypeLiteral, frozenset[str]] = {
    "resume": frozenset({"summary", "target_alignment"}),
    "cover_letter": frozenset({"opening", "opportunity_alignment", "closing"}),
    "recruiter_message": frozenset({"subject", "body", "sign_off"}),
    "freelance_proposal": frozenset(
        {
            "introduction",
            "project_understanding",
            "suggested_approach",
            "alignment_points",
            "closing",
        }
    ),
    "application_answers": frozenset(),
}

# Prefixos parametrizados permitidos por material_type:
# mapeiam prefixo -> tipo de entidade alvo (ou None para answer:<question_id>)
PARAMETERIZED_SLOT_PATTERNS_BY_MATERIAL: dict[
    AIMaterialTypeLiteral,
    tuple[tuple[str, FactEntityTypeLiteral | None], ...],
] = {
    "resume": (
        ("experience_highlight:", "experience"),
        ("project_highlight:", "project"),
    ),
    "cover_letter": (
        ("relevance_highlight:experience:", "experience"),
        ("relevance_highlight:project:", "project"),
    ),
    "recruiter_message": (),
    "freelance_proposal": (
        ("relevant_evidence:experience:", "experience"),
        ("relevant_evidence:project:", "project"),
    ),
    "application_answers": (
        ("answer:", None),
    ),
}


@dataclass(frozen=True, slots=True)
class ParsedSlotTarget:
    """Metadados estruturais resolvidos de um slot validado contra a allowlist."""

    material_type: AIMaterialTypeLiteral
    slot_id: str
    slot_kind: Literal["static", "entity_bound", "question_answer"]
    target_entity_type: FactEntityTypeLiteral | None = None
    target_entity_id: str | None = None

    @property
    def required_fact_key(self) -> str | None:
        if self.target_entity_type and self.target_entity_id:
            return f"{self.target_entity_type}:{self.target_entity_id}"
        return None


def parse_and_validate_slot_for_material(
    material_type: AIMaterialTypeLiteral,
    slot_id: str,
) -> ParsedSlotTarget:
    """Valida ``slot_id`` contra a allowlist estrita do ``material_type``."""
    if material_type not in AI_SUPPORTED_MATERIAL_TYPES:
        raise ValueError(f"Tipo de material não suportado: '{material_type}'.")

    clean = slot_id.strip()
    if not clean or not _SAFE_SLOT_RE.match(clean):
        raise ValueError(
            f"Identificador de slot inválido: '{clean}'. "
            "Caracteres permitidos são apenas [A-Za-z0-9_:-]."
        )

    static_slots = STATIC_ALLOWED_SLOTS_BY_MATERIAL[material_type]
    if clean in static_slots:
        return ParsedSlotTarget(
            material_type=material_type,
            slot_id=clean,
            slot_kind="static",
        )

    for prefix, entity_type in PARAMETERIZED_SLOT_PATTERNS_BY_MATERIAL[material_type]:
        if clean.startswith(prefix):
            suffix = clean[len(prefix) :]
            if not _ENTITY_ID_SEGMENT_RE.match(suffix):
                raise ValueError(
                    f"Identificador de destino inválido no slot '{clean}'."
                )
            if entity_type is None:
                return ParsedSlotTarget(
                    material_type=material_type,
                    slot_id=clean,
                    slot_kind="question_answer",
                )
            return ParsedSlotTarget(
                material_type=material_type,
                slot_id=clean,
                slot_kind="entity_bound",
                target_entity_type=entity_type,
                target_entity_id=suffix,
            )

    raise ValueError(
        f"Slot '{clean}' não é permitido para o tipo de material '{material_type}'."
    )


class ContextTruncationMetadata(BaseModel):
    """Metadados operacionais internos de orçamento e redação (nunca enviados ao provider)."""

    model_config = ConfigDict(extra="forbid")

    total_confirmed_facts_available: int = Field(default=0, ge=0)
    included_facts_count: int = Field(default=0, ge=0)
    dropped_facts_count: int = Field(default=0, ge=0)
    dropped_by_entity_type: dict[str, int] = Field(default_factory=dict)
    truncated_by_fact_limit: bool = False
    truncated_by_byte_budget: bool = False
    pii_redacted_fields_count: int = Field(default=0, ge=0)
    pii_omitted_fields_count: int = Field(default=0, ge=0)
    serialized_bytes: int = Field(default=0, ge=0)
    max_facts_limit: int = Field(default=60, ge=1)
    max_payload_bytes: int = Field(default=24_000, ge=1)


class AuthorizedFactItem(BaseModel):
    """Representação serializada mínima e segura de um fato profissional autorizado."""

    model_config = ConfigDict(extra="forbid")

    fact_key: str = Field(..., min_length=3, max_length=100)
    entity_type: FactEntityTypeLiteral
    entity_id: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    role_or_title: str | None = Field(default=None, max_length=200)
    company_or_institution: str | None = Field(default=None, max_length=200)
    period: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    verified_results: str | None = Field(default=None, max_length=1500)
    proficiency: str | None = Field(default=None, max_length=80)
    eligible_as_target_role: bool = False

    @field_validator("fact_key")
    @classmethod
    def _validate_fact_key(cls, value: str) -> str:
        clean = value.strip()
        if not _FACT_KEY_RE.match(clean):
            raise ValueError(f"Formato inválido de fact_key: '{clean}'")
        return clean

    @model_validator(mode="after")
    def _validate_entity_consistency(self) -> "AuthorizedFactItem":
        expected = f"{self.entity_type}:{self.entity_id}"
        if self.fact_key != expected:
            raise ValueError(
                f"Inconsistência em AuthorizedFactItem: fact_key '{self.fact_key}' != '{expected}'."
            )
        if self.entity_type == "project" and self.company_or_institution is not None:
            raise ValueError(
                "Projetos profissionais não podem possuir company_or_institution."
            )
        return self


class SanitizedOpportunityContext(BaseModel):
    """Contexto estruturado e higienizado da oportunidade alvo (nunca é evidência do candidato)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=200)
    seniority_level: str | None = Field(default=None, max_length=64)
    professional_area: str | None = Field(default=None, max_length=80)
    employment_type: str | None = Field(default=None, max_length=64)
    required_technologies: list[str] = Field(default_factory=list, max_length=20)
    desirable_technologies: list[str] = Field(default_factory=list, max_length=20)
    all_technologies: list[str] = Field(default_factory=list, max_length=30)
    language: str | None = Field(default=None, max_length=32)


class AuthorizedAIContext(BaseModel):
    """Contexto serializado fornecido à IA com garantia de autorização factual e minimização de PII.

    `user_id` e `truncation_metadata` são mantidos exclusivamente no backend (`exclude=True`)
    e nunca são serializados para o provider em `model_dump`, `model_dump_json` ou
    `to_provider_payload()`.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1, max_length=64, exclude=True)
    material_type: AIMaterialTypeLiteral
    target_language: TargetLanguage = "pt-BR"
    authorized_facts: list[AuthorizedFactItem] = Field(default_factory=list, max_length=60)
    opportunity: SanitizedOpportunityContext | None = None
    truncation_metadata: ContextTruncationMetadata = Field(
        default_factory=ContextTruncationMetadata,
        exclude=True,
    )

    def to_provider_payload(self) -> dict[str, Any]:
        """Retorna payload estritamente minimizado destinado ao LLMProvider (sem user_id/metadados)."""
        payload = self.model_dump(mode="json", exclude={"user_id", "truncation_metadata"})
        return {
            "material_type": payload["material_type"],
            "target_language": payload["target_language"],
            "candidate_confirmed_facts": payload["authorized_facts"],
            "target_opportunity_context": payload["opportunity"],
        }

    def get_fact(self, fact_key: str) -> AuthorizedFactItem | None:
        for fact in self.authorized_facts:
            if fact.fact_key == fact_key:
                return fact
        return None

    def all_fact_keys(self) -> set[str]:
        return {fact.fact_key for fact in self.authorized_facts}

    def all_confirmed_technologies(self) -> set[str]:
        techs: set[str] = set()
        for fact in self.authorized_facts:
            for t in fact.technologies:
                if t and t.strip():
                    techs.add(t.strip().lower())
            if fact.entity_type == "skill" and fact.label:
                techs.add(fact.label.strip().lower())
        return techs

    def all_confirmed_companies(self) -> set[str]:
        companies: set[str] = set()
        for fact in self.authorized_facts:
            if (
                fact.entity_type in {"experience", "education"}
                and fact.company_or_institution
                and fact.company_or_institution.strip()
            ):
                companies.add(fact.company_or_institution.strip().lower())
        return companies

    def all_confirmed_roles(self) -> set[str]:
        roles: set[str] = set()
        for fact in self.authorized_facts:
            if fact.role_or_title and fact.role_or_title.strip():
                roles.add(fact.role_or_title.strip().lower())
        return roles


class AISuggestionItem(BaseModel):
    """Item de sugestão narrativa para um slot de material gerado pela IA."""

    model_config = ConfigDict(extra="forbid")

    slot_id: str = Field(..., min_length=1, max_length=100)
    suggested_text: str = Field(..., min_length=1, max_length=4000)
    cited_fact_keys: list[str] = Field(..., min_length=1, max_length=20)

    @field_validator("slot_id")
    @classmethod
    def _validate_slot_id(cls, value: str) -> str:
        clean = value.strip()
        if not _SAFE_SLOT_RE.match(clean):
            raise ValueError(
                f"Identificador de slot inválido: '{clean}'. Deve conter apenas [A-Za-z0-9_:-]."
            )
        return clean

    @field_validator("suggested_text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("suggested_text não pode ser vazio.")
        return clean

    @field_validator("cited_fact_keys")
    @classmethod
    def _validate_cited_fact_keys(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for val in values:
            clean = val.strip()
            if not _FACT_KEY_RE.match(clean):
                raise ValueError(f"Chave de fato inválida na citação: '{clean}'")
            if clean not in cleaned:
                cleaned.append(clean)
        if not cleaned:
            raise ValueError("cited_fact_keys deve conter ao menos uma chave de fato válida.")
        return cleaned


class AIMaterialEnhanceOutput(BaseModel):
    """Contrato tipado de saída para sugestões estruturadas de aprimoramento por IA."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    material_type: AIMaterialTypeLiteral
    target_language: TargetLanguage = "pt-BR"
    suggestions: list[AISuggestionItem] = Field(..., min_length=1, max_length=30)

    @model_validator(mode="after")
    def _validate_slots_allowlist_and_uniqueness(self) -> "AIMaterialEnhanceOutput":
        seen_slots: set[str] = set()
        for item in self.suggestions:
            parse_and_validate_slot_for_material(self.material_type, item.slot_id)
            if item.slot_id in seen_slots:
                raise ValueError(
                    f"Slot duplicado não permitido no mesmo conjunto de sugestões: '{item.slot_id}'."
                )
            seen_slots.add(item.slot_id)
        return self
