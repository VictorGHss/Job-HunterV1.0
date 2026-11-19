from __future__ import annotations

import re
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

_SAFE_SLOT_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_FACT_KEY_RE = re.compile(r"^(profile|experience|project|education|skill|language):[A-Za-z0-9_-]+$")


class AuthorizedFactItem(BaseModel):
    """Representação serializada mínima e segura de um fato profissional autorizado."""

    model_config = ConfigDict(extra="forbid")

    fact_key: str = Field(..., min_length=3, max_length=100)
    entity_type: Literal["profile", "experience", "project", "education", "skill", "language"]
    entity_id: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    role_or_title: str | None = Field(default=None, max_length=200)
    company_or_institution: str | None = Field(default=None, max_length=200)
    period: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    technologies: list[str] = Field(default_factory=list, max_length=50)
    verified_results: str | None = Field(default=None, max_length=4000)
    proficiency: str | None = Field(default=None, max_length=80)
    matched_requirements: list[str] = Field(default_factory=list, max_length=30)
    eligible_as_target_role: bool = False

    @field_validator("fact_key")
    @classmethod
    def _validate_fact_key(cls, value: str) -> str:
        clean = value.strip()
        if not _FACT_KEY_RE.match(clean):
            raise ValueError(f"Formato inválido de fact_key: '{clean}'")
        return clean


class SanitizedOpportunityContext(BaseModel):
    """Contexto estruturado e higienizado da oportunidade/vaga alvo."""

    model_config = ConfigDict(extra="forbid")

    opportunity_id: str | None = Field(default=None, max_length=64)
    application_id: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=200)
    seniority_level: str | None = Field(default=None, max_length=64)
    professional_area: str | None = Field(default=None, max_length=80)
    employment_type: str | None = Field(default=None, max_length=64)
    required_technologies: list[str] = Field(default_factory=list, max_length=30)
    desirable_technologies: list[str] = Field(default_factory=list, max_length=30)
    all_technologies: list[str] = Field(default_factory=list, max_length=50)
    language: str | None = Field(default=None, max_length=32)


class AuthorizedAIContext(BaseModel):
    """Contexto serializado fornecido à IA com garantia de autorização factual e minimização de dados."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1, max_length=64)
    material_type: AIMaterialTypeLiteral
    target_language: TargetLanguage = "pt-BR"
    authorized_facts: list[AuthorizedFactItem] = Field(default_factory=list, max_length=150)
    opportunity: SanitizedOpportunityContext | None = None

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
            if fact.company_or_institution and fact.company_or_institution.strip():
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
                f"Identificador de slot inválido: '{clean}'. Deve conter apenas [A-Za-z0-9_.:-]."
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
