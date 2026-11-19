"""Suíte de testes da Subfase 04.4.2 — Contexto autorizado e Grounding estruturado (hardened)."""
from __future__ import annotations

from datetime import date
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.material import ApplicationMaterial, ApplicationMaterialVersion
from app.models.profile import (
    Education,
    EducationStatus,
    ExperienceType,
    Language,
    LanguageProficiency,
    ProfessionalProfile,
    ProfessionalProject,
    Skill,
    SkillProficiency,
    VerificationStatus,
    WorkExperience,
)
from app.services.auth_service import create_user_account
from app.services.materials.ai import (
    AIContextAuthorizationError,
    AIDisabledError,
    AIMaterialEnhanceOutput,
    AISuggestionItem,
    AuthorizedAIContext,
    AuthorizedFactItem,
    DisabledLLMProvider,
    LLMStructuredRequest,
    MockLLMProvider,
    SanitizedOpportunityContext,
    StructuredGroundingValidator,
    build_authorized_ai_context,
    extract_mentioned_technologies,
)
from tests.test_materials_phase041 import (
    _create_application,
    _create_confirmed_rich_profile,
    _create_opportunity,
)


# ============================================================================
# HELPERS SINTÉTICOS DE TESTE
# ============================================================================


def _build_test_context(
    *,
    material_type: str = "resume",
    target_language: str = "pt-BR",
) -> AuthorizedAIContext:
    """Cria um contexto sintético autorizado para testes determinísticos de grounding."""
    return AuthorizedAIContext(
        user_id="user-123",
        material_type=material_type,  # type: ignore[arg-type]
        target_language=target_language,  # type: ignore[arg-type]
        authorized_facts=[
            AuthorizedFactItem(
                fact_key="profile:prof-1",
                entity_type="profile",
                entity_id="prof-1",
                label="Desenvolvedor Backend Python",
                role_or_title="Desenvolvedor Backend Python",
                description="Profissional com foco em APIs REST, Python e FastAPI.",
                technologies=["Python", "FastAPI", "APIs REST"],
            ),
            AuthorizedFactItem(
                fact_key="experience:exp-1",
                entity_type="experience",
                entity_id="exp-1",
                label="Desenvolvedor Júnior — Acme",
                company_or_institution="Acme",
                role_or_title="Desenvolvedor Júnior",
                period="01/2023 – 06/2024",
                description=(
                    "Desenvolveu cinco APIs em Python 3.13 e FastAPI com redução de 25% na latência. "
                    "Contribuiu para melhorias no sistema com solidez e familiaridade no frontend."
                ),
                technologies=["Python", "FastAPI", "PostgreSQL"],
                verified_results="Redução de 25% no tempo de resposta das APIs.",
            ),
            AuthorizedFactItem(
                fact_key="experience:exp-2",
                entity_type="experience",
                entity_id="exp-2",
                label="Analista de Suporte — Beta",
                company_or_institution="Beta",
                role_or_title="Analista de Suporte",
                period="01/2022 – 12/2022",
                description="Atendimento de chamados e manutenção de scripts em JavaScript.",
                technologies=["JavaScript"],
            ),
            AuthorizedFactItem(
                fact_key="project:proj-1",
                entity_type="project",
                entity_id="proj-1",
                label="Job Hunter Engine",
                role_or_title="Autor e Desenvolvedor",
                period=None,
                description="Plataforma com FastAPI e Docker com 100% de cobertura nos testes.",
                verified_results="Cobertura de testes automatizados com 100% de sucesso.",
                technologies=["FastAPI", "Docker", "PostgreSQL"],
            ),
            AuthorizedFactItem(
                fact_key="skill:sk-1",
                entity_type="skill",
                entity_id="sk-1",
                label="Python",
                technologies=["Python"],
            ),
            AuthorizedFactItem(
                fact_key="skill:sk-2",
                entity_type="skill",
                entity_id="sk-2",
                label="FastAPI",
                technologies=["FastAPI"],
            ),
            AuthorizedFactItem(
                fact_key="language:lang-1",
                entity_type="language",
                entity_id="lang-1",
                label="Inglês",
                proficiency="advanced",
            ),
        ],
        opportunity=SanitizedOpportunityContext(
            title="Desenvolvedor Backend Sênior",
            company_name="Inova Tech",
            required_technologies=["Python", "FastAPI", "Kubernetes", "AWS", "Terraform"],
            all_technologies=["Python", "FastAPI", "Kubernetes", "AWS", "Terraform"],
        ),
    )


# ============================================================================
# GRUPO A: CONSTRUÇÃO DE CONTEXTO, AUTORIZAÇÃO (A-02) E PRIVACIDADE (M-01/M-02/M-03)
# ============================================================================


def test_a1_only_confirmed_facts_and_downgrade_reflected_immediately(db_session: Session) -> None:
    """A1: Apenas fatos confirmados entram; rebaixamento para pending_validation exclui imediatamente."""
    user = create_user_account(
        db_session,
        email="a1_test@example.com",
        password="ValidPassword123!",
        display_name="Usuário A1",
    )
    _create_confirmed_rich_profile(db_session, user.id)

    ctx = build_authorized_ai_context(db_session, user, material_type="resume")
    assert ctx.user_id == str(user.id)
    assert ctx.material_type == "resume"

    fact_keys = ctx.all_fact_keys()
    assert any(k.startswith("profile:") for k in fact_keys)
    assert any(k.startswith("experience:") for k in fact_keys)
    assert any(k.startswith("project:") for k in fact_keys)
    assert any(k.startswith("education:") for k in fact_keys)
    assert any(k.startswith("skill:") for k in fact_keys)
    assert any(k.startswith("language:") for k in fact_keys)

    # Rebaixa experiência confirmada para pending_validation -> deve sair imediatamente
    exp = db_session.scalar(
        select(WorkExperience).where(
            WorkExperience.user_id == user.id,
            WorkExperience.verification_status == VerificationStatus.CONFIRMED.value,
        )
    )
    assert exp is not None
    exp.verification_status = VerificationStatus.PENDING_VALIDATION.value
    db_session.commit()

    ctx_after = build_authorized_ai_context(db_session, user, material_type="resume")
    assert f"experience:{exp.id}" not in ctx_after.all_fact_keys()

    # Nenhuma mutação de ApplicationMaterial ou ApplicationMaterialVersion ocorreu
    assert db_session.scalar(select(func.count(ApplicationMaterial.id))) == 0
    assert db_session.scalar(select(func.count(ApplicationMaterialVersion.id))) == 0


def test_a2_unconfirmed_facts_strictly_omitted(db_session: Session) -> None:
    """A2: Fatos pendentes ou em rascunho são estritamente omitidos."""
    user = create_user_account(
        db_session,
        email="a2_test@example.com",
        password="ValidPassword123!",
        display_name="Usuário A2",
    )
    _create_confirmed_rich_profile(db_session, user.id)

    ctx = build_authorized_ai_context(db_session, user, material_type="resume")

    exp_companies = [f.company_or_institution for f in ctx.authorized_facts if f.entity_type == "experience"]
    assert "Startup APIs" not in exp_companies
    assert "Empresa Suporte Ltda" in exp_companies

    proj_names = [f.label for f in ctx.authorized_facts if f.entity_type == "project"]
    assert "Experimento Rascunho K8s" not in proj_names
    assert "Job Hunter Engine" in proj_names

    skill_names = [f.label for f in ctx.authorized_facts if f.entity_type == "skill"]
    assert "Docker" not in skill_names
    assert "FastAPI" in skill_names


def test_a3_m01_project_period_never_fabricated_from_updated_at(db_session: Session) -> None:
    """M-01 (Sonda 3B): Projeto sem data factual confirmada deve manter period=None (jamais updated_at.year)."""
    user = create_user_account(
        db_session,
        email="m01_sonda3b@example.com",
        password="ValidPassword123!",
        display_name="Usuário M01",
    )
    _create_confirmed_rich_profile(db_session, user.id)

    ctx = build_authorized_ai_context(db_session, user, material_type="resume")
    proj_facts = [f for f in ctx.authorized_facts if f.entity_type == "project"]
    assert len(proj_facts) == 1
    assert proj_facts[0].period is None
    assert proj_facts[0].company_or_institution is None


def test_a4_m02_pii_redacted_in_free_text_and_user_id_excluded_from_serialization(
    db_session: Session,
) -> None:
    """M-02: PII em campos de texto livre é redigida/omitida e user_id não aparece no payload externo."""
    user = create_user_account(
        db_session,
        email="m02_pii@example.com",
        password="ValidPassword123!",
        display_name="Usuário M02",
    )
    profile = ProfessionalProfile(
        user_id=user.id,
        full_name="João Teste",
        professional_email="joao.privado@example.com",
        phone="+55 11 98765-4321",
        city="Campinas",
        state="SP",
        country="Brasil",
        professional_title="Desenvolvedor Python",
        professional_summary=(
            "Atuo com Python e FastAPI. Fale comigo em joao.livre@gmail.com, "
            "WhatsApp +55 19 98765-4321 ou github.com/joaoteste. "
            "Moro na Rua das Flores, 123 - Apto 45, CEP 13010-000."
        ),
        linkedin_url="https://www.linkedin.com/in/joaoteste",
        github_url="https://github.com/joaoteste",
        portfolio_url="https://joaoteste.dev",
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    exp = WorkExperience(
        user_id=user.id,
        company="Empresa Limpa",
        role="Desenvolvedor Backend",
        description=(
            "Desenvolvi APIs em Python. Contato do gestor: gestor [at] empresa [dot] com "
            "ou telefone (19) 99876-5432 e CPF 123.456.789-00."
        ),
        start_date=date(2023, 1, 1),
        end_date=date(2024, 1, 1),
        is_current=False,
        experience_type=ExperienceType.CLT.value,
        technologies=["Python"],
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    proj = ProfessionalProject(
        user_id=user.id,
        name="Sistema Interno",
        role="Autor",
        description="Veja o código em https://meuportfolio.dev/privado ou escreva para dev@privado.org.",
        verified_results="Reduziu tempo de fila; contato: +55 20 99888-7766.",
        technologies=["Python"],
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    skill = Skill(
        user_id=user.id,
        name="Python",
        category="Backend",
        proficiency_level=SkillProficiency.ADVANCED.value,
        notes="Referência pessoal: endereço: Avenida Paulista, 1000, São Paulo.",
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    db_session.add_all([profile, exp, proj, skill])
    db_session.commit()

    ctx = build_authorized_ai_context(db_session, user, material_type="resume")

    # Backend preserva user_id e metadados operacionais internamente
    assert ctx.user_id == str(user.id)
    assert ctx.truncation_metadata.pii_redacted_fields_count > 0

    # Nenhuma forma de serialização pode expor user_id nem PII
    dumped = ctx.model_dump()
    dumped_json = ctx.model_dump_json()
    provider_payload = ctx.to_provider_payload()
    provider_json = json.dumps(provider_payload, ensure_ascii=False)

    assert "user_id" not in dumped
    assert "truncation_metadata" not in dumped
    assert str(user.id) not in dumped_json
    assert "user_id" not in provider_payload
    assert str(user.id) not in provider_json

    for forbidden in (
        "joao.privado@example.com",
        "joao.livre@gmail.com",
        "98765-4321",
        "99876-5432",
        "99888-7766",
        "linkedin.com",
        "github.com/joaoteste",
        "joaoteste.dev",
        "meuportfolio.dev",
        "dev@privado.org",
        "gestor [at] empresa",
        "Rua das Flores",
        "13010-000",
        "123.456.789-00",
        "Avenida Paulista, 1000",
    ):
        assert forbidden not in dumped_json, f"Vazamento de PII em model_dump_json: {forbidden}"
        assert forbidden not in provider_json, f"Vazamento de PII em to_provider_payload: {forbidden}"


def test_a5_a02_authorization_sondas_3c_3d_3e_and_valid_access(db_session: Session) -> None:
    """A-02: Reproduz Sondas 3C, 3D, 3E + valida acesso legítimo a oportunidade pública e privada própria."""
    user_a = create_user_account(
        db_session,
        email="auth_a@example.com",
        password="ValidPassword123!",
        display_name="Usuário A",
    )
    user_b = create_user_account(
        db_session,
        email="auth_b@example.com",
        password="ValidPassword123!",
        display_name="Usuário B",
    )
    _create_confirmed_rich_profile(db_session, user_a.id)
    _create_confirmed_rich_profile(db_session, user_b.id)

    opp_public = _create_opportunity(db_session, title="Vaga Pública Python", company_name="Public Corp")
    opp_private_a = _create_opportunity(
        db_session,
        title="Vaga Privada A",
        company_name="Privada A Corp",
        owner_user_id=user_a.id,
    )
    opp_private_b = _create_opportunity(
        db_session,
        title="Vaga Privada Secreta B",
        company_name="Secreta B Ltda",
        owner_user_id=user_b.id,
    )
    app_a_public = _create_application(db_session, user_a.id, opp_public)
    app_b_private = _create_application(db_session, user_b.id, opp_private_b)

    # Sonda 3C: oportunidade privada de B ao construir contexto de A -> REJEITADA
    with pytest.raises(AIContextAuthorizationError):
        build_authorized_ai_context(
            db_session,
            user_a,
            material_type="resume",
            opportunity=opp_private_b,
        )

    # Sonda 3D: candidatura pertencente a B ao construir contexto de A -> REJEITADA
    with pytest.raises(AIContextAuthorizationError):
        build_authorized_ai_context(
            db_session,
            user_a,
            material_type="cover_letter",
            application=app_b_private,
        )

    # Sonda 3E: candidatura de A vinculada a opp_public, mas chamador passa opp_private_a -> REJEITADA
    with pytest.raises(AIContextAuthorizationError):
        build_authorized_ai_context(
            db_session,
            user_a,
            material_type="cover_letter",
            application=app_a_public,
            opportunity=opp_private_a,
        )

    # Caso legítimo 1: oportunidade pública para usuário A -> PERMITIDA
    ctx_public = build_authorized_ai_context(
        db_session,
        user_a,
        material_type="resume",
        opportunity=opp_public,
    )
    assert ctx_public.opportunity is not None
    assert ctx_public.opportunity.title == "Vaga Pública Python"

    # Caso legítimo 2: oportunidade privada do próprio usuário A -> PERMITIDA
    ctx_own_private = build_authorized_ai_context(
        db_session,
        user_a,
        material_type="resume",
        opportunity=opp_private_a,
    )
    assert ctx_own_private.opportunity is not None
    assert ctx_own_private.opportunity.title == "Vaga Privada A"

    # Caso legítimo 3: candidatura de A + oportunidade consistente -> PERMITIDA
    ctx_consistent = build_authorized_ai_context(
        db_session,
        user_a,
        material_type="cover_letter",
        application=app_a_public,
        opportunity=opp_public,
    )
    assert ctx_consistent.opportunity is not None
    assert ctx_consistent.opportunity.company_name == "Public Corp"


def test_a6_m03_sondas_3f_3g_long_html_labels_and_155_skills_budget(db_session: Session) -> None:
    """M-03 (Sondas 3F e 3G): Labels HTML/longos são sanitizados/truncados e 155 skills não causam crash."""
    user = create_user_account(
        db_session,
        email="m03_budget@example.com",
        password="ValidPassword123!",
        display_name="Usuário M03",
    )
    _create_confirmed_rich_profile(db_session, user.id)

    # Sonda 3F: Experience e Education com HTML + strings longas (>200 chars ao concatenar)
    long_role = "<b>Desenvolvedor Backend</b> " + ("X" * 130)
    long_company = "<script>alert(1)</script>Empresa " + ("Y" * 130)
    exp_long = WorkExperience(
        user_id=user.id,
        company=long_company,
        role=long_role,
        description="Desenvolveu sistemas distribuídos em Python.",
        start_date=date(2023, 1, 1),
        is_current=True,
        experience_type=ExperienceType.CLT.value,
        technologies=["Python"],
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    edu_long = Education(
        user_id=user.id,
        institution="<img src=x onerror=alert(1)>Universidade " + ("U" * 130),
        course="<i>Bacharelado em Engenharia</i> " + ("C" * 130),
        field_of_study="Computação",
        education_status=EducationStatus.IN_PROGRESS.value,
        start_date=date(2022, 1, 1),
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    db_session.add_all([exp_long, edu_long])

    # Sonda 3G: 155 skills confirmadas
    for i in range(155):
        db_session.add(
            Skill(
                user_id=user.id,
                name=f"SkillConfirmada{i:03d}",
                category="Backend",
                proficiency_level=SkillProficiency.INTERMEDIATE.value,
                notes=f"Uso prático da habilidade número {i:03d}.",
                verification_status=VerificationStatus.CONFIRMED.value,
            )
        )
    db_session.commit()

    # Não deve lançar ValidationError
    ctx = build_authorized_ai_context(db_session, user, material_type="resume")

    # Labels sanitizados e <= 200 chars
    for fact in ctx.authorized_facts:
        assert len(fact.label) <= 200
        assert "<script>" not in fact.label
        assert "<b>" not in fact.label
        assert "<img" not in fact.label
        assert "onerror" not in fact.label.lower()

    # Orçamento de fatos e bytes respeitado, preservando entidades essenciais e registrando metadados
    assert len(ctx.authorized_facts) <= 60
    assert any(f.entity_type == "profile" for f in ctx.authorized_facts)
    assert any(f.entity_type == "experience" for f in ctx.authorized_facts)
    assert any(f.entity_type == "project" for f in ctx.authorized_facts)
    assert any(f.entity_type == "education" for f in ctx.authorized_facts)
    assert any(f.entity_type == "language" for f in ctx.authorized_facts)

    meta = ctx.truncation_metadata
    assert meta.total_confirmed_facts_available > 155
    assert meta.dropped_facts_count > 0
    assert meta.truncated_by_fact_limit is True
    assert meta.dropped_by_entity_type.get("skill", 0) > 0
    payload_bytes = len(
        json.dumps(ctx.to_provider_payload(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    assert payload_bytes <= meta.max_payload_bytes


def test_a7_multi_tenant_user_isolation(db_session: Session) -> None:
    """A7: Fatos do Usuário B nunca entram no contexto do Usuário A."""
    user_a = create_user_account(
        db_session,
        email="iso_a@example.com",
        password="ValidPassword123!",
        display_name="Usuário A",
    )
    user_b = create_user_account(
        db_session,
        email="iso_b@example.com",
        password="ValidPassword123!",
        display_name="Usuário B",
    )
    _create_confirmed_rich_profile(db_session, user_a.id)

    exp_b = WorkExperience(
        user_id=user_b.id,
        company="Empresa Secreta B",
        role="Desenvolvedor B",
        description="Trabalho confidencial do usuário B.",
        start_date=date(2022, 1, 1),
        is_current=True,
        experience_type=ExperienceType.CLT.value,
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    db_session.add(exp_b)
    db_session.commit()

    ctx_a = build_authorized_ai_context(db_session, user_a, material_type="resume")
    assert "empresa secreta b" not in ctx_a.all_confirmed_companies()
    assert f"experience:{exp_b.id}" not in ctx_a.all_fact_keys()


def test_a8_unsupported_material_type_rejected(db_session: Session) -> None:
    """A8: Tipo de material não suportado é rejeitado."""
    user = create_user_account(
        db_session,
        email="a8_test@example.com",
        password="ValidPassword123!",
        display_name="Usuário A8",
    )
    with pytest.raises(ValueError, match="Tipo de material não suportado"):
        build_authorized_ai_context(
            db_session,
            user,
            material_type="unsupported_type",  # type: ignore[arg-type]
        )


# ============================================================================
# GRUPO B: A-01 — REQUISITOS DA VAGA NUNCA AUTORIZAM COMPETÊNCIAS (SONDA 2A)
# ============================================================================


@pytest.mark.parametrize(
    ("material_type", "slot_id"),
    [
        ("resume", "summary"),
        ("cover_letter", "opportunity_alignment"),
        ("recruiter_message", "body"),
        ("freelance_proposal", "suggested_approach"),
        ("application_answers", "answer:q-cloud"),
    ],
)
def test_b1_a01_sonda_2a_opportunity_requirements_never_authorize_candidate_skills(
    material_type: str,
    slot_id: str,
) -> None:
    """A-01 (Sonda 2A): Kubernetes, AWS e Terraform na vaga NUNCA autorizam experiência do candidato nos 5 materiais."""
    ctx = _build_test_context(material_type=material_type)
    validator = StructuredGroundingValidator()

    output = AIMaterialEnhanceOutput(
        material_type=material_type,  # type: ignore[arg-type]
        suggestions=[
            AISuggestionItem(
                slot_id=slot_id,
                suggested_text="Profissional com experiência em Kubernetes, AWS e Terraform.",
                cited_fact_keys=["profile:prof-1"],
            )
        ],
    )

    result = validator.validate(ctx, output)
    assert result.is_valid is False
    reasons_joined = " ".join(result.rejection_reasons)
    assert "unconfirmed_technology" in reasons_joined
    assert "kubernetes" in reasons_joined
    assert "aws" in reasons_joined
    assert "terraform" in reasons_joined


def test_b2_a01_confirmed_candidate_tech_also_required_by_opportunity_is_accepted() -> None:
    """A-01 cenário legítimo: tecnologia exigida pela vaga que o usuário confirmou em fato citado é aceita."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    output = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="summary",
                suggested_text="Desenvolvedor com foco em Python, FastAPI e APIs REST.",
                cited_fact_keys=["profile:prof-1"],
            )
        ],
    )

    result = validator.validate(ctx, output)
    assert result.is_valid is True


# ============================================================================
# GRUPO C: A-03 — ALLOWLIST DE SLOTS, DUPLICIDADES E VÍNCULOS DE ENTIDADE (SONDAS 5A–5F)
# ============================================================================


@pytest.mark.parametrize(
    ("material_type", "bad_slot"),
    [
        # Sonda 5A: slots arbitrários
        ("resume", "block_1"),
        ("resume", "summary_1"),
        ("resume", "custom_narrative"),
        # Sonda 5B: slots de metadados e controle
        ("resume", "is_approved"),
        ("resume", "origin"),
        ("resume", "provenance"),
        ("resume", "header.email"),
        ("freelance_proposal", "pending_fields"),
        # Sonda 5C: slots de outro tipo de material
        ("resume", "answer:q-1"),
        ("resume", "opening"),
        ("cover_letter", "summary"),
        ("recruiter_message", "experience_highlight:exp-1"),
        ("application_answers", "summary"),
        ("freelance_proposal", "answer:q-1"),
    ],
)
def test_c1_a03_sondas_5a_5b_5c_slot_allowlist_enforced(material_type: str, bad_slot: str) -> None:
    """A-03 (Sondas 5A–5C): Slots arbitrários, de metadados e de outros materiais são rejeitados."""
    with pytest.raises(ValidationError):
        AIMaterialEnhanceOutput(
            material_type=material_type,  # type: ignore[arg-type]
            suggestions=[
                AISuggestionItem(
                    slot_id=bad_slot,
                    suggested_text="Texto qualquer em Python.",
                    cited_fact_keys=["profile:prof-1"],
                )
            ],
        )


def test_c2_a03_sonda_5d_duplicate_slot_rejected() -> None:
    """A-03 (Sonda 5D): slot_id duplicado no mesmo conjunto de sugestões é rejeitado pelo schema."""
    with pytest.raises(ValidationError, match="duplicado"):
        AIMaterialEnhanceOutput(
            material_type="resume",
            suggestions=[
                AISuggestionItem(
                    slot_id="summary",
                    suggested_text="Resumo um em Python.",
                    cited_fact_keys=["profile:prof-1"],
                ),
                AISuggestionItem(
                    slot_id="summary",
                    suggested_text="Resumo dois em FastAPI.",
                    cited_fact_keys=["profile:prof-1"],
                ),
            ],
        )


def test_c3_a03_sonda_5e_entity_id_mismatch_and_cross_entity_citation_rejected() -> None:
    """A-03 (Sonda 5E): experience_highlight:exp-1 não pode ser validado por exp-2 nem misturar projeto."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    # Entidade diferente da citada (exp-1 slot citando exp-2)
    out_wrong_id = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text="Atuou na Beta com JavaScript.",
                cited_fact_keys=["experience:exp-2"],
            )
        ],
    )
    res1 = validator.validate(ctx, out_wrong_id)
    assert res1.is_valid is False
    assert any("entity_binding_mismatch" in r for r in res1.rejection_reasons)

    # Mistura de experiência + projeto no slot específico de experiência
    out_mixed = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text="Usou Python e Docker na Acme.",
                cited_fact_keys=["experience:exp-1", "project:proj-1"],
            )
        ],
    )
    res2 = validator.validate(ctx, out_mixed)
    assert res2.is_valid is False
    assert any("cross_entity_citation" in r for r in res2.rejection_reasons)

    # Projeto apresentado como emprego formal
    out_proj_as_job = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="project_highlight:proj-1",
                suggested_text="Atuou em emprego formal em regime CLT desenvolvendo FastAPI.",
                cited_fact_keys=["project:proj-1"],
            )
        ],
    )
    res3 = validator.validate(ctx, out_proj_as_job)
    assert res3.is_valid is False
    assert any("ontological_mismatch" in r for r in res3.rejection_reasons)


def test_c4_a03_sonda_5f_irrelevant_language_citation_for_software_summary_rejected() -> None:
    """A-03 (Sonda 5F): Citar apenas idioma confirmado não fundamenta afirmação de desenvolvimento de software."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    output = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="summary",
                suggested_text="Profissional com experiência profissional em desenvolvimento de software e sistemas.",
                cited_fact_keys=["language:lang-1"],
            )
        ],
    )
    result = validator.validate(ctx, output)
    assert result.is_valid is False
    assert any("irrelevant_citation" in r for r in result.rejection_reasons)


def test_c5_extra_fields_forbidden_and_malformed_fact_key_rejected() -> None:
    """extra='forbid' e formato de fact_key continuam estritamente aplicados."""
    with pytest.raises(ValidationError):
        AISuggestionItem(
            slot_id="summary",
            suggested_text="Resumo.",
            cited_fact_keys=["profile:prof-1"],
            extra_field="proibido",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        AISuggestionItem(
            slot_id="summary",
            suggested_text="Resumo.",
            cited_fact_keys=["chave_invalida"],
        )


# ============================================================================
# GRUPO D: A-04 — BYPASSES NUMÉRICOS, TECNOLOGIAS, EMPRESAS, CARGOS E QUALITATIVOS
# ============================================================================


def test_d1_a04_cross_category_numeric_bypasses_all_rejected() -> None:
    """A-04: 3.13 != 3.13%, mês 06 != 6 anos, 25% != R$ 25 / USD 25, 5 APIs != 5 equipes."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    # 1. Python 3.13 no fato NÃO autoriza 3.13%
    out_pct = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text="Na Acme, obteve 3.13% de redução de erros.",
                cited_fact_keys=["experience:exp-1"],
            )
        ],
    )
    res_pct = validator.validate(ctx, out_pct)
    assert res_pct.is_valid is False
    assert any("ungrounded_metric" in r for r in res_pct.rejection_reasons)

    # 2. Data 01/2023 – 06/2024 (mês 06) NÃO autoriza 6 anos nem 6 meses
    for text in (
        "Atuou por 6 anos na Acme.",
        "Atuou por 6 meses na Acme.",
    ):
        out_dur = AIMaterialEnhanceOutput(
            material_type="resume",
            suggestions=[
                AISuggestionItem(
                    slot_id="experience_highlight:exp-1",
                    suggested_text=text,
                    cited_fact_keys=["experience:exp-1"],
                )
            ],
        )
        res_dur = validator.validate(ctx, out_dur)
        assert res_dur.is_valid is False
        assert any("ungrounded_duration" in r for r in res_dur.rejection_reasons)

    # 3. 25% no fato NÃO autoriza R$ 25 nem USD 25
    for text in (
        "Economizou R$ 25 na Acme.",
        "Saved USD 25 at Acme.",
    ):
        out_curr = AIMaterialEnhanceOutput(
            material_type="resume",
            suggestions=[
                AISuggestionItem(
                    slot_id="experience_highlight:exp-1",
                    suggested_text=text,
                    cited_fact_keys=["experience:exp-1"],
                )
            ],
        )
        res_curr = validator.validate(ctx, out_curr)
        assert res_curr.is_valid is False
        assert any("ungrounded_currency" in r for r in res_curr.rejection_reasons)

    # 4. Cinco APIs no fato NÃO autoriza cinco equipes nem 5 equipes
    for text in (
        "Atuou com cinco equipes na Acme.",
        "Atuou com 5 equipes na Acme.",
    ):
        out_qty = AIMaterialEnhanceOutput(
            material_type="resume",
            suggestions=[
                AISuggestionItem(
                    slot_id="experience_highlight:exp-1",
                    suggested_text=text,
                    cited_fact_keys=["experience:exp-1"],
                )
            ],
        )
        res_qty = validator.validate(ctx, out_qty)
        assert res_qty.is_valid is False
        assert any("ungrounded_quantity_context" in r for r in res_qty.rejection_reasons)

    # 5. Caso legítimo: 25% de latência e cinco APIs na MESMA categoria são aceitos
    out_ok = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text="Na Acme, desenvolveu cinco APIs em Python 3.13 com redução de 25% na latência.",
                cited_fact_keys=["experience:exp-1"],
            )
        ],
    )
    assert validator.validate(ctx, out_ok).is_valid is True


def test_d2_a04_suggestion_cannot_self_authorize_tech_version_numbers() -> None:
    """A-04 (7.2): A sugestão não pode inventar Python 3.13 nem React 18 para autorizar números de si mesma."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    # profile:prof-1 menciona Python, mas NÃO menciona 3.13
    output = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="summary",
                suggested_text="Desenvolvedor com experiência em Python 3.13 e FastAPI.",
                cited_fact_keys=["profile:prof-1"],
            )
        ],
    )
    result = validator.validate(ctx, output)
    assert result.is_valid is False
    assert any("ungrounded_tech_version" in r for r in result.rejection_reasons)


def test_d3_a04_spelled_number_substring_bypasses_rejected() -> None:
    """A-04 (7.3): 'solidez' não autoriza 'dez', 'familiaridade' não autoriza 'mil', 'frontend' não autoriza 'ten'."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    for text in (
        "Na Acme, entregou dez projetos em Python.",
        "Na Acme, atendeu mil clientes em Python.",
        "At Acme, delivered ten services with Python.",
    ):
        output = AIMaterialEnhanceOutput(
            material_type="resume",
            suggestions=[
                AISuggestionItem(
                    slot_id="experience_highlight:exp-1",
                    suggested_text=text,
                    cited_fact_keys=["experience:exp-1"],
                )
            ],
        )
        res = validator.validate(ctx, output)
        assert res.is_valid is False, f"Bypass por substring não bloqueado: {text}"


def test_d4_a04_javascript_does_not_authorize_java_and_project_docker_not_leaked_to_exp() -> None:
    """A-04 (7.5): JavaScript não autoriza Java; Docker do projeto não autoriza Docker em experiência diferente."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    # exp-2 tem JavaScript, NÃO Java
    out_java = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-2",
                suggested_text="Atuou na Beta mantendo sistemas em Java.",
                cited_fact_keys=["experience:exp-2"],
            )
        ],
    )
    res_java = validator.validate(ctx, out_java)
    assert res_java.is_valid is False
    assert any("unconfirmed_technology" in r and "java" in r for r in res_java.rejection_reasons)

    # proj-1 tem Docker, mas exp-1 NÃO tem Docker -> Docker não pode vazar para experience_highlight:exp-1
    out_docker = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text="Na Acme, desenvolveu APIs em Python utilizando Docker.",
                cited_fact_keys=["experience:exp-1"],
            )
        ],
    )
    res_docker = validator.validate(ctx, out_docker)
    assert res_docker.is_valid is False
    assert any("unconfirmed_technology" in r and "docker" in r for r in res_docker.rejection_reasons)


@pytest.mark.parametrize(
    "tech_phrase",
    [
        "MongoDB",
        "Apache Spark",
        "PyTorch",
        "SAP ERP",
        "Java",
        "JavaScript",
        "experience with Go",
        "Spring Boot",
        "Node.js",
        "Redis",
        "React",
    ],
)
def test_d5_a04_expanded_tech_catalog_blocks_unconfirmed_technologies(tech_phrase: str) -> None:
    """A-04 (7.5): Tecnologias conhecidas ausentes do fato citado são bloqueadas."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    output = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text=f"Na Acme, desenvolveu serviços utilizando {tech_phrase}.",
                cited_fact_keys=["experience:exp-1"],
            )
        ],
    )
    result = validator.validate(ctx, output)
    assert result.is_valid is False
    assert any("unconfirmed_technology" in r for r in result.rejection_reasons)


def test_d6_a04_invented_and_swapped_companies_rejected() -> None:
    """A-04 (7.6): Google, Meta, Amazon inventados e troca de Acme por Beta são rejeitados."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    for text in (
        "Trabalhou no Google desenvolvendo APIs em Python.",
        "Atuou na Meta com FastAPI.",
        "Worked at Amazon building Python services.",
        "Na Beta, desenvolveu APIs em Python e FastAPI.",
    ):
        output = AIMaterialEnhanceOutput(
            material_type="resume",
            suggestions=[
                AISuggestionItem(
                    slot_id="experience_highlight:exp-1",
                    suggested_text=text,
                    cited_fact_keys=["experience:exp-1"],
                )
            ],
        )
        result = validator.validate(ctx, output)
        assert result.is_valid is False, f"Empresa indevida não rejeitada: {text}"
        assert any("unconfirmed_company" in r for r in result.rejection_reasons)


@pytest.mark.parametrize(
    "inflated_text",
    [
        "Atuou como Desenvolvedor Sênior na Acme.",
        "Atuou como Arquiteto de Software na Acme.",
        "Atuou como Gerente de Engenharia na Acme.",
        "Atuou como Coordenador na Acme.",
        "Atuou como CEO da Acme.",
        "Foi Fundador da Acme.",
        "Atuou como Tech Lead na Acme.",
        "Atuou como Diretor na Acme.",
        "Atuou como Head de Engenharia na Acme.",
        "Liderou iniciativas de Python na Acme.",
        "Coordenou o desenvolvimento em Python na Acme.",
        "Gerenciou operações de FastAPI na Acme.",
        "Arquitetou os serviços em Python na Acme.",
        "Supervisionou entregas em Python na Acme.",
        "Led Python development at Acme.",
        "Managed FastAPI delivery at Acme.",
        "Founded the Python platform at Acme.",
        "Owned the architecture at Acme.",
        "Directed engineering initiatives at Acme.",
    ],
)
def test_d7_a04_seniority_roles_and_leadership_verbs_rejected(inflated_text: str) -> None:
    """A-04 (7.7): Cargos elevados e verbos de liderança sem evidência são rejeitados."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    output = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text=inflated_text,
                cited_fact_keys=["experience:exp-1"],
            )
        ],
    )
    result = validator.validate(ctx, output)
    assert result.is_valid is False, f"Promoção/liderança não rejeitada: {inflated_text}"
    assert any(
        "unsubstantiated_role_promotion" in r or "unsubstantiated_leadership_claim" in r
        for r in result.rejection_reasons
    )


def test_d8_a04_qualitative_exaggeration_rejected() -> None:
    """A-04 (7.8): Transformar 'Contribuiu para melhorias no sistema' em transformação sistêmica/redução de custos é rejeitado."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    # Com verbo "conduziu" e afirmações qualitativas exageradas
    out1 = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text=(
                    "Na Acme, conduziu uma transformação sistêmica que aumentou a eficiência "
                    "operacional e reduziu custos."
                ),
                cited_fact_keys=["experience:exp-1"],
            )
        ],
    )
    res1 = validator.validate(ctx, out1)
    assert res1.is_valid is False
    assert any("unsubstantiated_claim" in r for r in res1.rejection_reasons)

    # Mesmo sem verbo de liderança, a exageração qualitativa sozinha deve ser rejeitada
    out2 = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text=(
                    "Na Acme, participou de transformação sistêmica que aumentou a eficiência "
                    "operacional e reduziu custos."
                ),
                cited_fact_keys=["experience:exp-1"],
            )
        ],
    )
    res2 = validator.validate(ctx, out2)
    assert res2.is_valid is False
    assert any("unsubstantiated_claim" in r for r in res2.rejection_reasons)


# ============================================================================
# GRUPO E: M-04 (FALSOS POSITIVOS EM INGLÊS) E M-05 (SEGURANÇA DE SAÍDA)
# ============================================================================


@pytest.mark.parametrize(
    "natural_english_sentence",
    [
        "Worked on tasks before developers go to the store for supplies.",
        "Collaborated closely with the rest of the team on Python APIs.",
        "Maintained Python documentation during the spring season.",
        "Helped redistribute the workload across Python tasks.",
        "Avoided reactive behavior during Python maintenance.",
        "Documented a node in the process workflow for Python.",
    ],
)
def test_e1_m04_sonda_8b_english_natural_phrases_do_not_trigger_tech_false_positives(
    natural_english_sentence: str,
) -> None:
    """M-04 (Sonda 8B): Frases naturais em inglês não disparam falsos positivos de Go/REST/Spring/Redis/React/Node."""
    # Confirma diretamente no matcher dedicado que nenhuma tecnologia ambígua foi extraída
    detected = extract_mentioned_technologies(natural_english_sentence)
    assert detected <= {"python"}

    ctx = _build_test_context(material_type="resume", target_language="en")
    validator = StructuredGroundingValidator()
    output = AIMaterialEnhanceOutput(
        material_type="resume",
        target_language="en",
        suggestions=[
            AISuggestionItem(
                slot_id="summary",
                suggested_text=natural_english_sentence,
                cited_fact_keys=["profile:prof-1"],
            )
        ],
    )
    result = validator.validate(ctx, output)
    assert result.is_valid is True, f"Falso positivo em frase natural: {result.rejection_reasons}"


@pytest.mark.parametrize(
    ("unsafe_text", "expected_flag"),
    [
        # Sonda 6C.1: URL sem protocolo / domínio nu
        ("Veja meu trabalho em github.com/usuario para mais detalhes.", "forbidden_link"),
        ("Confira exemplos em meusite.dev/projetos.", "forbidden_link"),
        ("Acesse example.com para ver o portfólio.", "forbidden_link"),
        # Sonda 6C.2: E-mails ofuscados
        ("Contato via joao [at] exemplo [dot] com para propostas.", "forbidden_contact"),
        ("Escreva para joao at exemplo dot com quando desejar.", "forbidden_contact"),
        ("Fale em maria (at) empresa.com.br sobre a vaga.", "forbidden_contact"),
        # Sonda 6C.3: Telefones internacionais e DDD 19/20
        ("Telefone internacional +55 11 98765-4321 disponível.", "forbidden_contact"),
        ("Telefone de Campinas (19) 98765-4321 disponível.", "forbidden_contact"),
        ("Contato em Londres +44 20 7946 0958.", "forbidden_contact"),
        # Sonda 6C.4: Link Markdown multilinha
        ("Confira o [projeto\nprincipal](https://evil.example.com).", "forbidden_link"),
        ("Confira o [repositório](\nhttps://evil.example.com/repo\n).", "forbidden_link"),
        # Sonda 6C.5 / 6C.6 / 8A: Conteúdo ativo (vbscript, onfocus, svg, data:)
        ("Link malicioso vbscript:msgbox(1) inserido.", "forbidden_html_script"),
        ("Campo com onfocus=alert(1) embutido.", "forbidden_html_script"),
        ("Vetor <svg onload=alert(1)> injetado.", "forbidden_html_script"),
        ("Payload data:text/html;base64,PHNjcmlwdD4= inserido.", "forbidden_html_script"),
    ],
)
def test_e2_m05_sondas_6c_and_8a_unsafe_outputs_all_rejected(
    unsafe_text: str,
    expected_flag: str,
) -> None:
    """M-05 (Sondas 6C.1–6C.6 e 8A): Bypasses de URL, e-mail ofuscado, telefone, Markdown multilinha e conteúdo ativo."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    output = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="summary",
                suggested_text=unsafe_text,
                cited_fact_keys=["profile:prof-1"],
            )
        ],
    )
    result = validator.validate(ctx, output)
    assert result.is_valid is False, f"Payload inseguro não bloqueado: {unsafe_text}"
    assert any(expected_flag in r for r in result.rejection_reasons)


def test_e3_all_or_nothing_principle() -> None:
    """All-or-Nothing: 1 sugestão inválida em um lote rejeita todo o output."""
    ctx = _build_test_context(material_type="resume")
    validator = StructuredGroundingValidator()

    output = AIMaterialEnhanceOutput(
        material_type="resume",
        suggestions=[
            AISuggestionItem(
                slot_id="summary",
                suggested_text="Desenvolvedor focado em Python e FastAPI.",
                cited_fact_keys=["profile:prof-1"],
            ),
            AISuggestionItem(
                slot_id="experience_highlight:exp-1",
                suggested_text="Na Acme, desenvolveu APIs em Python com redução de 77% na latência.",
                cited_fact_keys=["experience:exp-1"],
            ),
        ],
    )
    result = validator.validate(ctx, output)
    assert result.is_valid is False
    assert any("77%" in r for r in result.rejection_reasons)


# ============================================================================
# GRUPO F: INTEGRAÇÃO COM MOCKLLMPROVIDER / DISABLED E OS 5 MATERIAIS
# ============================================================================


@pytest.mark.parametrize(
    ("material_type", "slot_id", "suggested_text", "cited_keys"),
    [
        (
            "resume",
            "summary",
            "Desenvolvedor Backend Python com foco em APIs REST e FastAPI.",
            ["profile:prof-1"],
        ),
        (
            "cover_letter",
            "opening",
            "Manifesto interesse na oportunidade na Inova Tech com base em minha atuação com Python e FastAPI.",
            ["profile:prof-1"],
        ),
        (
            "recruiter_message",
            "body",
            "Olá! Acompanho as oportunidades da Inova Tech e atuo com Python e FastAPI.",
            ["profile:prof-1"],
        ),
        (
            "freelance_proposal",
            "suggested_approach",
            "Proponho estruturar os serviços com FastAPI, Docker e PostgreSQL.",
            ["project:proj-1"],
        ),
        (
            "application_answers",
            "answer:q-backend",
            "Na Acme, desenvolvi cinco APIs em Python e FastAPI com PostgreSQL.",
            ["experience:exp-1"],
        ),
    ],
)
def test_f1_mock_provider_end_to_end_five_materials_with_provider_payload(
    material_type: str,
    slot_id: str,
    suggested_text: str,
    cited_keys: list[str],
) -> None:
    """F1: Fluxo ponta a ponta com MockLLMProvider nos 5 materiais usando to_provider_payload() sem user_id."""
    ctx = _build_test_context(material_type=material_type)
    provider_input = ctx.to_provider_payload()
    assert "user_id" not in provider_input
    assert "user-123" not in json.dumps(provider_input)

    payload = {
        "schema_version": 1,
        "material_type": material_type,
        "target_language": "pt-BR",
        "suggestions": [
            {
                "slot_id": slot_id,
                "suggested_text": suggested_text,
                "cited_fact_keys": cited_keys,
            }
        ],
    }

    mock_provider = MockLLMProvider(response_data=payload)
    req = LLMStructuredRequest(
        operation_type="material_enhance",
        schema_name="AIMaterialEnhanceOutput",
        response_schema={"type": "object", "required": ["suggestions", "material_type"]},
        system_instruction="Você é um redator profissional restrito aos fatos confirmados.",
        structured_input=provider_input,
    )
    resp = mock_provider.generate_structured(req)
    parsed = AIMaterialEnhanceOutput.model_validate(resp.data)

    validator = StructuredGroundingValidator()
    result = validator.validate(ctx, parsed)
    assert result.is_valid is True, f"Falha inesperada em {material_type}: {result.rejection_reasons}"
    assert "revisão e aprovação humana obrigatória" in result.epistemological_disclaimer


def test_f2_disabled_provider_remains_blocked() -> None:
    """F2: DisabledLLMProvider continua bloqueado sem chamadas externas."""
    disabled_provider = DisabledLLMProvider()
    req = LLMStructuredRequest(
        operation_type="material_enhance",
        schema_name="AIMaterialEnhanceOutput",
        response_schema={"type": "object"},
        system_instruction="Instrução qualquer.",
        structured_input={},
    )
    with pytest.raises(AIDisabledError, match="desabilitado nesta instância"):
        disabled_provider.generate_structured(req)
