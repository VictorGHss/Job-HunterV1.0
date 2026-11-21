from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import threading
from typing import Any
import uuid

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.materials import get_optional_llm_provider
from app.core.config import Settings
from app.main import app
from app.models.ai_usage import AICircuitBreakerRecord, AICircuitState, AIUsageLedger, AIUsageStatus
from app.models.application import Application, ApplicationStatus
from app.models.material import (
    ApplicationMaterial,
    ApplicationMaterialVersion,
    MaterialVersionOrigin,
)
from app.models.opportunity import (
    EmploymentType,
    ExperienceRequirementMode,
    ExternalSourceStatus,
    Opportunity,
    OpportunitySource,
    OpportunityType,
    ProfessionalArea,
    SeniorityLevel,
    SourceType,
    WorkMode,
)
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
from app.schemas.material import (
    MaterialAIEnhanceRequest,
    MaterialCreateRequest,
    MaterialLinkRequest,
    MaterialRegenerateRequest,
    MaterialVersionDeriveRequest,
    MaterialVersionUpdateRequest,
    WritingGenerationOptions,
)
from app.services.auth_service import create_user_account
from app.services.materials.ai import (
    AICircuitOpenError,
    AIDisabledError,
    AIGroundingRejectedError,
    AIOverlayConflictError,
    AIQuotaExceededError,
    AIReservationStateError,
    AIReviewStateError,
    AIStaleSourceVersionError,
    ControlledOverlayMerger,
    LLMProvider,
    LLMStructuredRequest,
    LLMStructuredResponse,
    LLMTokenUsage,
    MockLLMProvider,
    enhance_material_version_with_ai,
    get_circuit_state,
    reject_ai_assisted_version,
)
from app.services.materials.material_service import (
    MaterialImmutableError,
    MaterialPreconditionError,
    approve_material_version,
    create_material,
    derive_material_version,
    export_material_version,
    get_material_detail,
    link_material_version,
    list_materials,
    regenerate_material_version,
    update_material_version,
)
from tests.conftest import resolve_test_database_url
from tests.test_foundation_phase01 import login_and_get_csrf


class _CallbackLLMProvider(LLMProvider):
    """Provider determinístico de teste que delega geração a um callback customizado."""

    def __init__(
        self,
        handler: Callable[[LLMStructuredRequest], dict[str, Any]],
        *,
        provider_name: str = "mock",
        model_name: str = "mock-deterministic-v1",
        token_usage: LLMTokenUsage | None = LLMTokenUsage(input_tokens=320, output_tokens=180),
        latency_ms: int = 12,
    ) -> None:
        self._handler = handler
        self._provider_name = provider_name
        self._model_name = model_name
        self._token_usage = token_usage
        self._latency_ms = latency_ms
        self.captured_requests: list[LLMStructuredRequest] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate_structured(self, request: LLMStructuredRequest) -> LLMStructuredResponse:
        self.captured_requests.append(request)
        payload = self._handler(request)
        return LLMStructuredResponse(
            data=payload,
            provider_name=self._provider_name,
            model_name=self._model_name,
            latency_ms=self._latency_ms,
            token_usage=self._token_usage,
        )


def _ai_enabled_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "ai_assisted_enabled": True,
        "ai_provider": "mock",
        "ai_model_name": "mock-deterministic-v1",
        "ai_request_timeout_seconds": 10.0,
        "ai_user_window_max_requests": 10,
        "ai_rate_limit_window_seconds": 300,
        "ai_user_daily_max_requests": 40,
        "ai_user_daily_max_tokens": 120_000,
        "ai_global_daily_max_tokens": 600_000,
        "ai_reservation_ttl_seconds": 60,
        "ai_circuit_breaker_failure_threshold": 3,
        "ai_circuit_breaker_cooldown_seconds": 60,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _seed_user_and_csrf(
    make_client,
    db_session: Session,
    email: str,
    password: str = "StrongPass!2026",
):
    user = create_user_account(
        db_session,
        email=email,
        display_name=email.split("@")[0],
        password=password,
    )
    client = make_client()
    csrf = login_and_get_csrf(client, email, password)
    return user, client, csrf


def _csrf_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


def _seed_confirmed_facts_and_opportunity(
    db_session: Session,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    now_dt = datetime.now(UTC)
    slug = "test-source-phase0443"
    source = db_session.scalar(
        select(OpportunitySource).where(OpportunitySource.slug == slug)
    )
    if source is None:
        source = OpportunitySource(
            slug=slug,
            name="Fonte 0443",
            source_type=SourceType.JSON_API.value,
            base_url="https://source0443.example.com",
            terms_url="https://source0443.example.com/terms",
            attribution_text="Fonte de teste 0443",
        )
        db_session.add(source)
        db_session.flush()

    opp = Opportunity(
        title="Desenvolvedor Python Backend",
        company_name="Acme Sistemas",
        external_id=f"ext-0443-{uuid.uuid4().hex[:8]}",
        source_url=f"https://example.com/jobs/{uuid.uuid4().hex[:8]}",
        description="Vaga backend com Python, FastAPI, PostgreSQL e Docker.",
        requirements=["Python", "FastAPI", "PostgreSQL"],
        technologies=["Python", "FastAPI", "PostgreSQL", "Docker"],
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        experience_requirement_mode=ExperienceRequirementMode.PREFERRED.value,
        experience_min_years=1,
        employment_type=EmploymentType.CLT.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        secondary_areas=[],
        language="pt-BR",
        source_status=ExternalSourceStatus.ACTIVE.value,
        first_seen_at=now_dt,
        last_seen_at=now_dt,
        content_hash=uuid.uuid4().hex,
        source_id=source.id,
    )
    db_session.add(opp)

    profile = ProfessionalProfile(
        user_id=user_id,
        full_name="Victor Andrade",
        professional_email="victor.andrade@example.com",
        phone="+55 11 97777-6666",
        city="São Paulo",
        state="SP",
        country="Brasil",
        professional_title="Desenvolvedor Backend Python",
        professional_summary="Desenvolvedor backend com atuação comprovada em Python, FastAPI, PostgreSQL e Docker.",
        linkedin_url="https://www.linkedin.com/in/victorandrade",
        github_url="https://github.com/victorandrade",
        portfolio_url="https://victorandrade.dev",
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    db_session.add(profile)

    exp = WorkExperience(
        user_id=user_id,
        company="DataFlow Tecnologia",
        role="Desenvolvedor Backend Júnior",
        description="Desenvolvimento e manutenção de APIs REST com Python, FastAPI e PostgreSQL.",
        start_date=date(2023, 2, 1),
        end_date=date(2024, 11, 1),
        is_current=False,
        experience_type=ExperienceType.CLT.value,
        eligible_as_target_role=True,
        technologies=["Python", "FastAPI", "PostgreSQL"],
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    db_session.add(exp)

    proj = ProfessionalProject(
        user_id=user_id,
        name="Motor de Conciliação Financeira",
        description="Serviço de processamento assíncrono construído com Python, FastAPI, PostgreSQL e Docker.",
        technologies=["Python", "FastAPI", "PostgreSQL", "Docker"],
        verified_results="Processamento auditável de lotes diários com Python e PostgreSQL.",
        links={"github": "https://github.com/victorandrade/conciliacao"},
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    db_session.add(proj)

    edu = Education(
        user_id=user_id,
        institution="Universidade Estadual",
        course="Ciência da Computação",
        field_of_study="Computação",
        education_status=EducationStatus.COMPLETED.value,
        start_date=date(2019, 2, 1),
        expected_graduation_date=date(2022, 12, 15),
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    db_session.add(edu)

    skills: list[Skill] = []
    for skill_name in ("Python", "FastAPI", "PostgreSQL", "Docker"):
        sk = Skill(
            user_id=user_id,
            name=skill_name,
            category="Backend",
            proficiency_level=SkillProficiency.INTERMEDIATE.value,
            verification_status=VerificationStatus.CONFIRMED.value,
        )
        db_session.add(sk)
        skills.append(sk)

    lang = Language(
        user_id=user_id,
        language_name="Inglês",
        proficiency_level=LanguageProficiency.INTERMEDIATE.value,
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    db_session.add(lang)

    db_session.commit()
    db_session.refresh(opp)
    db_session.refresh(profile)
    db_session.refresh(exp)
    db_session.refresh(proj)
    for sk in skills:
        db_session.refresh(sk)

    return {
        "opportunity": opp,
        "profile_key": f"profile:{profile.id}",
        "experience_id": str(exp.id),
        "experience_key": f"experience:{exp.id}",
        "project_id": str(proj.id),
        "project_key": f"project:{proj.id}",
        "skill_keys": [f"skill:{sk.id}" for sk in skills],
    }


def test_tc443_01_migration_0012_upgrade_downgrade_and_check_constraint(tmp_path: Path):
    """TC-443-01: Valida roundtrip 0011 -> 0012 -> 0011 -> head e CheckConstraint rejection_state_consistent."""
    mig_url = resolve_test_database_url(tmp_path)
    connect_args = {"check_same_thread": False} if mig_url.startswith("sqlite") else {}
    engine = create_engine(mig_url, connect_args=connect_args, future=True)

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", mig_url)

    script_dir = ScriptDirectory.from_config(alembic_cfg)
    assert script_dir.get_heads() == ["0012_ai_version_rejection_state"]

    user_id = uuid.uuid4()
    mat_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    now = datetime.now(UTC)

    try:
        with engine.begin() as conn:
            alembic_cfg.attributes["connection"] = conn
            command.upgrade(alembic_cfg, "0011_ai_usage_ledger")

        is_sqlite = engine.dialect.name == "sqlite"
        now_param = now.isoformat() if is_sqlite else now

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, display_name, password_hash, account_status, is_admin, created_at, updated_at) "
                    "VALUES (:id, :email, :name, :pwd, 'active', :is_admin, :now, :now)"
                ),
                {
                    "id": str(user_id) if is_sqlite else user_id,
                    "email": "mig0012@example.com",
                    "name": "Mig 0012",
                    "pwd": "hash",
                    "is_admin": False,
                    "now": now_param,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO application_materials (id, user_id, opportunity_id, material_type, title, target_language, created_at, updated_at) "
                    "VALUES (:id, :uid, NULL, 'resume', 'Currículo 0012', 'pt-BR', :now, :now)"
                ),
                {
                    "id": str(mat_id) if is_sqlite else mat_id,
                    "uid": str(user_id) if is_sqlite else user_id,
                    "now": now_param,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO application_material_versions "
                    "(id, material_id, version_number, origin, structured_content, source_facts_snapshot, unconfirmed_warnings, missing_requirements, is_approved, created_at, updated_at) "
                    "VALUES (:id, :mid, 1, 'generated', '{}', '{}', '[]', '[]', :approved, :now, :now)"
                ),
                {
                    "id": str(ver_id) if is_sqlite else ver_id,
                    "mid": str(mat_id) if is_sqlite else mat_id,
                    "approved": False,
                    "now": now_param,
                },
            )

        # Upgrade 0011 -> 0012
        with engine.begin() as conn:
            alembic_cfg.attributes["connection"] = conn
            command.upgrade(alembic_cfg, "0012_ai_version_rejection_state")

        insp = inspect(engine)
        ver_cols = {c["name"] for c in insp.get_columns("application_material_versions")}
        assert {"is_rejected", "rejected_at"}.issubset(ver_cols)
        idx_names = {
            idx["name"] for idx in insp.get_indexes("application_material_versions")
        }
        assert "ix_material_versions_mat_rejected_ver" in idx_names

        # CheckConstraint bloqueia estados inconsistentes:
        # 1) is_rejected=True com rejected_at=NULL
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO application_material_versions "
                        "(id, material_id, version_number, origin, structured_content, source_facts_snapshot, unconfirmed_warnings, missing_requirements, is_approved, is_rejected, rejected_at, created_at, updated_at) "
                        "VALUES (:id, :mid, 2, 'ai_assisted', '{}', '{}', '[]', '[]', :approved, :rejected, NULL, :now, :now)"
                    ),
                    {
                        "id": str(uuid.uuid4()) if is_sqlite else uuid.uuid4(),
                        "mid": str(mat_id) if is_sqlite else mat_id,
                        "approved": False,
                        "rejected": True,
                        "now": now_param,
                    },
                )

        # 2) is_rejected=True com is_approved=True
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO application_material_versions "
                        "(id, material_id, version_number, origin, structured_content, source_facts_snapshot, unconfirmed_warnings, missing_requirements, is_approved, approved_at, is_rejected, rejected_at, created_at, updated_at) "
                        "VALUES (:id, :mid, 3, 'ai_assisted', '{}', '{}', '[]', '[]', :approved, :now, :rejected, :now, :now, :now)"
                    ),
                    {
                        "id": str(uuid.uuid4()) if is_sqlite else uuid.uuid4(),
                        "mid": str(mat_id) if is_sqlite else mat_id,
                        "approved": True,
                        "rejected": True,
                        "now": now_param,
                    },
                )

        # Downgrade 0012 -> 0011 e upgrade até head
        with engine.begin() as conn:
            alembic_cfg.attributes["connection"] = conn
            command.downgrade(alembic_cfg, "0011_ai_usage_ledger")

        cols_after_down = {
            c["name"] for c in inspect(engine).get_columns("application_material_versions")
        }
        assert "is_rejected" not in cols_after_down
        assert "rejected_at" not in cols_after_down

        with engine.begin() as conn:
            alembic_cfg.attributes["connection"] = conn
            command.upgrade(alembic_cfg, "head")
        assert "is_rejected" in {
            c["name"] for c in inspect(engine).get_columns("application_material_versions")
        }

        with engine.begin() as conn:
            alembic_cfg.attributes["connection"] = conn
            command.downgrade(alembic_cfg, "base")
    finally:
        engine.dispose()


def test_tc443_02_resume_ai_enhance_e2e_and_ledger_binding(
    make_client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """TC-443-02: Aprimoramento E2E de currículo (201), versionamento imutável e vínculo no ledger."""
    monkeypatch.setattr(
        "app.services.materials.ai.orchestrator.get_settings",
        lambda: _ai_enabled_settings(),
    )
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "tc443_02@example.com")
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Desenvolvedor Backend Python com atuação confirmada em FastAPI, PostgreSQL e Docker.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                },
                {
                    "slot_id": "target_alignment",
                    "suggested_text": "Alinhamento técnico com a vaga de Desenvolvedor Python Backend na Acme Sistemas usando Python e FastAPI.",
                    "cited_fact_keys": [facts["experience_key"], *facts["skill_keys"][:2]],
                },
                {
                    "slot_id": f"experience_highlight:{facts['experience_id']}",
                    "suggested_text": "- Construção e manutenção de APIs REST com Python e FastAPI\n- Persistência relacional em PostgreSQL na DataFlow Tecnologia",
                    "cited_fact_keys": [facts["experience_key"]],
                },
                {
                    "slot_id": f"project_highlight:{facts['project_id']}",
                    "suggested_text": "- Processamento assíncrono em Python e FastAPI com PostgreSQL e Docker",
                    "cited_fact_keys": [facts["project_key"]],
                },
            ],
        }
    )

    app.dependency_overrides[get_optional_llm_provider] = lambda: provider
    try:
        resp = client.post(
            f"/api/v1/materials/{mat.id}/versions/{v1.id}/ai-enhance",
            json={"user_instructions": "Priorize clareza objetiva para recrutamento técnico."},
            headers=_csrf_headers(csrf),
        )
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["latest_version_number"] == 2
    assert body["latest_active_version_number"] == 2
    assert len(body["versions"]) == 2

    v2_data = body["versions"][0]
    v1_data = body["versions"][1]
    assert v2_data["version_number"] == 2
    assert v2_data["origin"] == "ai_assisted"
    assert v2_data["parent_version_id"] == str(v1.id)
    assert v2_data["is_approved"] is False
    assert v2_data["is_rejected"] is False
    assert v2_data["is_mutable"] is False
    assert v1_data["version_number"] == 1
    assert v1_data["is_mutable"] is False

    # Verifica structured_content de v2 e preservação de v1
    v2_sc = v2_data["structured_content"]
    assert "FastAPI, PostgreSQL e Docker" in v2_sc["summary"]["text"]
    assert v2_sc["summary"]["provenance"] == "confirmed_fact"
    assert "DataFlow Tecnologia" in v2_sc["experiences"][0]["description"]
    assert v2_sc["experiences"][0]["provenance"] == "confirmed_fact"
    assert v2_sc["header"] == v1_data["structured_content"]["header"]
    assert v2_sc["education"] == v1_data["structured_content"]["education"]
    assert v2_sc["skills"] == v1_data["structured_content"]["skills"]

    # Verifica ledger concluído e vinculado à nova versão v2
    db_session.expire_all()
    ledger_entry = db_session.scalar(
        select(AIUsageLedger).where(
            AIUsageLedger.user_id == user.id,
            AIUsageLedger.material_id == mat.id,
        )
    )
    assert ledger_entry is not None
    assert ledger_entry.status == AIUsageStatus.COMPLETED.value
    assert str(ledger_entry.version_id) == v2_data["id"]
    assert ledger_entry.input_tokens == 320
    assert ledger_entry.output_tokens == 180
    assert ledger_entry.total_tokens == 500
    assert v2_data["source_facts_snapshot"]["ai_overlay"]["ledger_entry_id"] == str(
        ledger_entry.id
    )


def test_tc443_03_cover_letter_ai_enhance_e2e_and_greeting_preservation(
    db_session: Session,
):
    """TC-443-03: Aprimoramento E2E de cover_letter preservando greeting user_authored e header."""
    user = create_user_account(
        db_session,
        email="tc443_03@example.com",
        display_name="TC 03",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    cl_mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="cover_letter",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
            writing_options=WritingGenerationOptions(contact_name="Mariana Costa"),
        ),
    )
    cl_v1 = cl_mat.versions[0]
    cl_provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "cover_letter",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "opening",
                    "suggested_text": "Apresento minha trajetória confirmada em Python, FastAPI e PostgreSQL para a vaga na Acme Sistemas.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                },
                {
                    "slot_id": f"relevance_highlight:experience:{facts['experience_id']}",
                    "suggested_text": "Atuação na DataFlow Tecnologia desenvolvendo APIs REST com Python, FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["experience_key"]],
                },
            ],
        }
    )
    cl_res = enhance_material_version_with_ai(
        db_session,
        user,
        material_id=cl_mat.id,
        version_id=cl_v1.id,
        payload=MaterialAIEnhanceRequest(),
        injected_provider=cl_provider,
        settings_override=cfg,
    )
    cl_v2 = cl_res.versions[0]
    assert cl_v2.origin == "ai_assisted"
    assert cl_v2.structured_content.greeting.text == cl_v1.structured_content.greeting.text
    assert cl_v2.structured_content.greeting.provenance == "user_authored"
    assert "Acme Sistemas" in cl_v2.structured_content.opening.text


def test_tc443_04_recruiter_message_ai_enhance_and_character_count_recalculation(
    db_session: Session,
):
    """TC-443-04: Aprimoramento E2E de recruiter_message com recálculo determinístico de character_count."""
    user = create_user_account(
        db_session,
        email="tc443_04@example.com",
        display_name="TC 04",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    rm_mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="recruiter_message",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
            writing_options=WritingGenerationOptions(
                channel="email",
                contact_name="Carlos",
            ),
        ),
    )
    rm_v1 = rm_mat.versions[0]
    rm_provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "recruiter_message",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "subject",
                    "suggested_text": "Candidatura — Desenvolvedor Python Backend (FastAPI / PostgreSQL)",
                    "cited_fact_keys": [facts["profile_key"]],
                },
                {
                    "slot_id": "body",
                    "suggested_text": "Entro em contato sobre a vaga na Acme Sistemas compartilhando minha experiência com Python, FastAPI e PostgreSQL na DataFlow Tecnologia.",
                    "cited_fact_keys": [facts["experience_key"]],
                },
            ],
        }
    )
    rm_res = enhance_material_version_with_ai(
        db_session,
        user,
        material_id=rm_mat.id,
        version_id=rm_v1.id,
        payload=MaterialAIEnhanceRequest(),
        injected_provider=rm_provider,
        settings_override=cfg,
    )
    rm_v2 = rm_res.versions[0]
    assert rm_v2.structured_content.greeting.provenance == "user_authored"
    assert rm_v2.structured_content.character_count == len(
        rm_v2.rendered_plain_text.strip()
    )


def test_tc443_05_freelance_proposal_ai_enhance_and_pending_fields_protection(
    db_session: Session,
):
    """TC-443-05: Aprimoramento E2E de freelance_proposal preservando integralmente pending_fields."""
    user = create_user_account(
        db_session,
        email="tc443_05@example.com",
        display_name="TC 05",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    fp_mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="freelance_proposal",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    fp_v1 = fp_mat.versions[0]
    assert fp_v1.has_blocking_pending_fields is True
    fp_provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "freelance_proposal",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "introduction",
                    "suggested_text": "Apresento proposta técnica fundamentada na experiência com Python, FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                },
                {
                    "slot_id": "suggested_approach",
                    "suggested_text": "Implementação estruturada utilizando Python, FastAPI, PostgreSQL e Docker.",
                    "cited_fact_keys": [facts["project_key"]],
                },
            ],
        }
    )
    fp_res = enhance_material_version_with_ai(
        db_session,
        user,
        material_id=fp_mat.id,
        version_id=fp_v1.id,
        payload=MaterialAIEnhanceRequest(),
        injected_provider=fp_provider,
        settings_override=cfg,
    )
    fp_v2 = fp_res.versions[0]
    assert fp_v2.structured_content.pending_fields == fp_v1.structured_content.pending_fields
    assert fp_v2.has_blocking_pending_fields is True
    with pytest.raises(MaterialPreconditionError):
        approve_material_version(db_session, user, fp_mat.id, fp_v2.id)


def test_tc443_06_application_answers_ai_enhance_and_protected_items(
    db_session: Session,
):
    """TC-443-06: Aprimoramento E2E de application_answers protegendo user_answered e needs_user_input."""
    user = create_user_account(
        db_session,
        email="tc443_06@example.com",
        display_name="TC 06",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    aa_mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="application_answers",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
            writing_options=WritingGenerationOptions(
                questions=[
                    "Qual é sua experiência técnica com Python e FastAPI?",
                    "Qual é sua pretensão salarial mensal?",
                    "Qual é sua disponibilidade para início?",
                ],
                initial_answers=[
                    {
                        "question": "Qual é sua pretensão salarial mensal?",
                        "user_answer": "R$ 6.500,00 mensais.",
                    }
                ],
            ),
        ),
    )
    aa_v1 = aa_mat.versions[0]
    items_list_v1 = aa_v1.structured_content.items
    q1_id = items_list_v1[0].question_id
    q2_id = items_list_v1[1].question_id
    q3_id = items_list_v1[2].question_id
    assert items_list_v1[0].status == "answered_from_facts"
    assert items_list_v1[0].provenance == "confirmed_fact"
    assert items_list_v1[1].status == "user_answered"
    assert items_list_v1[1].provenance == "user_authored"
    assert items_list_v1[2].status == "needs_user_input"

    aa_provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "application_answers",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": f"answer:{q1_id}",
                    "suggested_text": "Experiência comprovada com Python, FastAPI e PostgreSQL na DataFlow Tecnologia e no projeto Motor de Conciliação Financeira.",
                    "cited_fact_keys": [facts["experience_key"], facts["project_key"]],
                }
            ],
        }
    )

    for protected_slot in (f"answer:{q2_id}", f"answer:{q3_id}"):
        with pytest.raises(AIOverlayConflictError):
            enhance_material_version_with_ai(
                db_session,
                user,
                material_id=aa_mat.id,
                version_id=aa_v1.id,
                payload=MaterialAIEnhanceRequest(target_slot_ids=[protected_slot]),
                injected_provider=aa_provider,
                settings_override=cfg,
            )

    aa_res = enhance_material_version_with_ai(
        db_session,
        user,
        material_id=aa_mat.id,
        version_id=aa_v1.id,
        payload=MaterialAIEnhanceRequest(),
        injected_provider=aa_provider,
        settings_override=cfg,
    )
    aa_v2 = aa_res.versions[0]
    items_v2 = {it.question_id: it for it in aa_v2.structured_content.items}
    assert "Motor de Conciliação Financeira" in (items_v2[q1_id].answer_text or "")
    assert items_v2[q2_id].answer_text == "R$ 6.500,00 mensais."
    assert items_v2[q2_id].provenance == "user_authored"
    assert items_v2[q3_id].status == "needs_user_input"
    assert items_v2[q3_id].answer_text is None


def test_tc443_07_manual_edit_policy2_and_user_authored_protection(
    db_session: Session,
):
    """TC-443-07: Valida Política 2 para manual_edit (auto preserva, explícito permite) e proteção absoluta de user_authored."""
    user = create_user_account(
        db_session,
        email="tc443_07@example.com",
        display_name="TC 07",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    cl_mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="cover_letter",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = cl_mat.versions[0]
    edited_sc = v1.structured_content.model_copy(deep=True)
    # Edita opening mantendo source_fact_keys para que o reconciliador marque opening como manual_edit
    edited_sc.opening.text = "Apresento meu perfil confirmado em Python e FastAPI com foco em qualidade."
    # Edita closing sem source_fact_keys para que o reconciliador marque closing como user_authored
    edited_sc.closing.text = "Agradeço muito a atenção ao meu processo seletivo."
    edited_sc.closing.source_fact_keys = []

    updated_mat = update_material_version(
        db_session,
        user,
        cl_mat.id,
        v1.id,
        MaterialVersionUpdateRequest(structured_content=edited_sc.model_dump(mode="json")),
    )
    v1_edited = updated_mat.versions[0]
    assert v1_edited.structured_content.opening.provenance == "manual_edit"
    assert v1_edited.structured_content.closing.provenance == "user_authored"
    assert v1_edited.structured_content.opportunity_alignment.provenance == "confirmed_fact"

    # 1) Modo automático (target_slot_ids=None): pula opening (manual_edit) e closing (user_authored)
    auto_provider = _CallbackLLMProvider(
        lambda req: {
            "schema_version": 1,
            "material_type": "cover_letter",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "opportunity_alignment",
                    "suggested_text": "Alinhamento confirmado em Python, FastAPI e PostgreSQL para a Acme Sistemas.",
                    "cited_fact_keys": [facts["experience_key"]],
                }
            ],
        }
    )
    res_auto = enhance_material_version_with_ai(
        db_session,
        user,
        material_id=cl_mat.id,
        version_id=v1_edited.id,
        payload=MaterialAIEnhanceRequest(target_slot_ids=None),
        injected_provider=auto_provider,
        settings_override=cfg,
    )
    v2_auto = res_auto.versions[0]
    assert "opening" not in auto_provider.captured_requests[0].structured_input["eligible_target_slots"]
    assert "closing" not in auto_provider.captured_requests[0].structured_input["eligible_target_slots"]
    assert v2_auto.structured_content.opening.text == v1_edited.structured_content.opening.text
    assert v2_auto.structured_content.opening.provenance == "manual_edit"
    assert v2_auto.structured_content.closing.text == v1_edited.structured_content.closing.text
    assert v2_auto.structured_content.closing.provenance == "user_authored"

    # Rejeita v2_auto para restaurar v1_edited como ativa
    reject_ai_assisted_version(
        db_session, user, material_id=cl_mat.id, version_id=v2_auto.id
    )

    # 2) Modo explícito (target_slot_ids=["opening"]): permite aprimorar opening (manual_edit)
    explicit_provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "cover_letter",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "opening",
                    "suggested_text": "Apresento experiência confirmada com Python, FastAPI e PostgreSQL na DataFlow Tecnologia.",
                    "cited_fact_keys": [facts["experience_key"]],
                }
            ],
        }
    )
    res_explicit = enhance_material_version_with_ai(
        db_session,
        user,
        material_id=cl_mat.id,
        version_id=v1_edited.id,
        payload=MaterialAIEnhanceRequest(target_slot_ids=["opening"]),
        injected_provider=explicit_provider,
        settings_override=cfg,
    )
    v3_explicit = res_explicit.versions[0]
    assert v3_explicit.version_number == 3
    assert "DataFlow Tecnologia" in v3_explicit.structured_content.opening.text
    assert v3_explicit.structured_content.opening.provenance == "confirmed_fact"

    # 3) Modo explícito apontando para closing (user_authored) é bloqueado com AIOverlayConflictError
    reject_ai_assisted_version(
        db_session, user, material_id=cl_mat.id, version_id=v3_explicit.id
    )
    with pytest.raises(AIOverlayConflictError) as exc_info:
        enhance_material_version_with_ai(
            db_session,
            user,
            material_id=cl_mat.id,
            version_id=v1_edited.id,
            payload=MaterialAIEnhanceRequest(target_slot_ids=["closing"]),
            injected_provider=explicit_provider,
            settings_override=cfg,
        )
    assert exc_info.value.reason_code == "protected_user_authored_slot"


def test_tc443_08_payload_enrichment_and_untrusted_separation(
    db_session: Session,
):
    """TC-443-08: Segregação tipada de rascunho atual e user_instructions sem contaminar candidate_confirmed_facts."""
    user = create_user_account(
        db_session,
        email="tc443_08_only@example.com",
        display_name="TC 08",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Desenvolvedor Python Backend com atuação confirmada em FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                }
            ],
        }
    )

    enhance_material_version_with_ai(
        db_session,
        user,
        material_id=mat.id,
        version_id=v1.id,
        payload=MaterialAIEnhanceRequest(
            target_slot_ids=["summary"],
            user_instructions="Priorize tom direto. Não use Kubernetes. Contato: privado@example.com",
        ),
        injected_provider=provider,
        settings_override=cfg,
    )

    assert len(provider.captured_requests) == 1
    sent_input = provider.captured_requests[0].structured_input
    assert "candidate_confirmed_facts" in sent_input
    assert "reference_draft_slots_untrusted_for_facts" in sent_input
    assert sent_input["reference_draft_slots_untrusted_for_facts"][0]["slot_id"] == "summary"
    assert (
        sent_input["reference_draft_slots_untrusted_for_facts"][0]["trust_level"]
        == "untrusted_draft_style_only"
    )
    assert (
        sent_input["user_writing_preferences"]["trust_level"]
        == "style_and_emphasis_only_not_factual_evidence"
    )
    assert "privado@example.com" not in sent_input["user_writing_preferences"]["instruction_text"]
    confirmed_blob = str(sent_input["candidate_confirmed_facts"]).lower()
    assert "kubernetes" not in confirmed_blob


def test_tc443_09_sanitized_grounding_rejection_without_provider_echo(
    make_client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """TC-443-09: Rejeição 422 por falha de grounding sem ecoar trechos brutos da sugestão do provider."""
    monkeypatch.setattr(
        "app.services.materials.ai.orchestrator.get_settings",
        lambda: _ai_enabled_settings(),
    )
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "tc443_09@example.com")
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    forbidden_secret_phrase = "SECRET_UNCONFIRMED_KUBERNETES_GOOGLE_45_PERCENT"
    hallucinating_provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": (
                        f"Liderei equipe de 40 engenheiros com Kubernetes na Google reduzindo custos em 45% ({forbidden_secret_phrase})."
                    ),
                    "cited_fact_keys": [facts["profile_key"]],
                }
            ],
        }
    )

    app.dependency_overrides[get_optional_llm_provider] = lambda: hallucinating_provider
    try:
        resp = client.post(
            f"/api/v1/materials/{mat.id}/versions/{v1.id}/ai-enhance",
            json={
                "target_slot_ids": ["summary"],
                "user_instructions": "Destaque Kubernetes e 45% de melhoria de latência.",
            },
            headers=_csrf_headers(csrf),
        )
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)

    assert resp.status_code == 422
    assert resp.headers.get("X-AI-Error-Code") == "grounding_rejected"
    detail_text = resp.json()["detail"]
    assert isinstance(detail_text, str)
    assert forbidden_secret_phrase not in detail_text
    assert "Kubernetes" not in detail_text
    assert "45%" not in detail_text
    assert "Google" not in detail_text

    db_session.expire_all()
    refreshed_mat = get_material_detail(db_session, user, mat.id)
    assert len(refreshed_mat.versions) == 1
    cb = get_circuit_state(db_session, provider_key="mock")
    assert cb.state == AICircuitState.CLOSED
    assert cb.consecutive_failures == 0

    ledger = db_session.scalar(
        select(AIUsageLedger).where(
            AIUsageLedger.user_id == user.id,
            AIUsageLedger.material_id == mat.id,
        )
    )
    assert ledger is not None
    assert ledger.status == AIUsageStatus.FAILED.value
    assert ledger.error_code == "grounding_rejected"
    assert ledger.version_id == v1.id


def test_tc443_10_provider_errors_and_circuit_breaker_opening(
    make_client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """TC-443-10: Malformed output (502), timeout (504) e abertura do circuit breaker (503 com Retry-After)."""
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "tc443_10@example.com")
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    monkeypatch.setattr(
        "app.services.materials.ai.orchestrator.get_settings",
        lambda: _ai_enabled_settings(ai_circuit_breaker_failure_threshold=2),
    )

    malformed_provider = MockLLMProvider(simulate_invalid_output=True)
    app.dependency_overrides[get_optional_llm_provider] = lambda: malformed_provider
    try:
        resp_malformed = client.post(
            f"/api/v1/materials/{mat.id}/versions/{v1.id}/ai-enhance",
            json={},
            headers=_csrf_headers(csrf),
        )
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)
    assert resp_malformed.status_code == 502
    assert resp_malformed.headers.get("X-AI-Error-Code") == "malformed_output"
    assert "unexpected_field" not in resp_malformed.text

    timeout_provider = MockLLMProvider(simulate_timeout=True)
    app.dependency_overrides[get_optional_llm_provider] = lambda: timeout_provider
    try:
        resp_timeout = client.post(
            f"/api/v1/materials/{mat.id}/versions/{v1.id}/ai-enhance",
            json={},
            headers=_csrf_headers(csrf),
        )
        resp_circuit = client.post(
            f"/api/v1/materials/{mat.id}/versions/{v1.id}/ai-enhance",
            json={},
            headers=_csrf_headers(csrf),
        )
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)

    assert resp_timeout.status_code == 504
    assert resp_timeout.headers.get("X-AI-Error-Code") == "provider_timeout"
    assert resp_circuit.status_code == 503
    assert resp_circuit.headers.get("X-AI-Error-Code") == "circuit_open"
    assert int(resp_circuit.headers.get("Retry-After", "0")) >= 1


def test_tc443_11_kill_switch_and_quota_exhaustion(
    make_client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """TC-443-11: Kill switch (503 ai_disabled) e esgotamento de cota (429 com Retry-After)."""
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "tc443_11@example.com")
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    monkeypatch.setattr(
        "app.services.materials.ai.orchestrator.get_settings",
        lambda: _ai_enabled_settings(ai_assisted_enabled=False),
    )
    resp_disabled = client.post(
        f"/api/v1/materials/{mat.id}/versions/{v1.id}/ai-enhance",
        json={},
        headers=_csrf_headers(csrf),
    )
    assert resp_disabled.status_code == 503
    assert resp_disabled.headers.get("X-AI-Error-Code") == "ai_disabled"

    monkeypatch.setattr(
        "app.services.materials.ai.orchestrator.get_settings",
        lambda: _ai_enabled_settings(ai_user_window_max_requests=1),
    )
    provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Desenvolvedor Python com atuação confirmada em FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                }
            ],
        }
    )
    app.dependency_overrides[get_optional_llm_provider] = lambda: provider
    try:
        resp_first = client.post(
            f"/api/v1/materials/{mat.id}/versions/{v1.id}/ai-enhance",
            json={"target_slot_ids": ["summary"]},
            headers=_csrf_headers(csrf),
        )
        assert resp_first.status_code == 201
        v2_id = resp_first.json()["versions"][0]["id"]
        resp_quota = client.post(
            f"/api/v1/materials/{mat.id}/versions/{v2_id}/ai-enhance",
            json={"target_slot_ids": ["summary"]},
            headers=_csrf_headers(csrf),
        )
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)

    assert resp_quota.status_code == 429
    assert int(resp_quota.headers.get("Retry-After", "0")) >= 1
    assert "quota_exceeded:" in (resp_quota.headers.get("X-AI-Error-Code") or "")


def test_tc443_12_persisted_rejection_lifecycle_and_active_version_restoration(
    make_client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """TC-443-12: Rejeição persistida sem DELETE físico, preservação do ledger e restauração de mutabilidade."""
    monkeypatch.setattr(
        "app.services.materials.ai.orchestrator.get_settings",
        lambda: _ai_enabled_settings(),
    )
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "tc443_12@example.com")
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]
    assert v1.is_mutable is True

    provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Resumo aprimorado com Python, FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                }
            ],
        }
    )

    app.dependency_overrides[get_optional_llm_provider] = lambda: provider
    try:
        resp_enhance = client.post(
            f"/api/v1/materials/{mat.id}/versions/{v1.id}/ai-enhance",
            json={"target_slot_ids": ["summary"]},
            headers=_csrf_headers(csrf),
        )
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)

    assert resp_enhance.status_code == 201
    v2_id = resp_enhance.json()["versions"][0]["id"]

    resp_reject = client.post(
        f"/api/v1/materials/{mat.id}/versions/{v2_id}/reject-ai",
        headers=_csrf_headers(csrf),
    )
    assert resp_reject.status_code == 200, resp_reject.text
    after_reject = resp_reject.json()

    assert after_reject["latest_version_number"] == 2
    assert after_reject["latest_active_version_number"] == 1
    assert after_reject["latest_active_version_id"] == str(v1.id)
    assert len(after_reject["versions"]) == 2
    assert after_reject["versions"][0]["id"] == str(v1.id)
    assert after_reject["versions"][0]["is_mutable"] is True
    assert after_reject["versions"][1]["id"] == v2_id
    assert after_reject["versions"][1]["is_rejected"] is True
    assert after_reject["versions"][1]["rejected_at"] is not None
    assert after_reject["versions"][1]["is_mutable"] is False

    summaries = list_materials(db_session, user)
    assert len(summaries) == 1
    assert summaries[0].latest_version_number == 2
    assert summaries[0].latest_active_version_number == 1
    assert summaries[0].latest_active_version_id == v1.id

    db_session.expire_all()
    ledger = db_session.scalar(
        select(AIUsageLedger).where(AIUsageLedger.material_id == mat.id)
    )
    assert ledger is not None
    assert str(ledger.version_id) == v2_id

    edited_v1_payload = v1.structured_content.model_dump(mode="json")
    edited_v1_payload["manual_notes"] = [
        {
            "id": "note-post-reject",
            "title": "Observação",
            "content": "Nota manual adicionada em v1 após rejeitar v2.",
            "source_fact_keys": [],
            "provenance": "user_authored",
        }
    ]
    resp_edit_v1 = client.put(
        f"/api/v1/materials/{mat.id}/versions/{v1.id}",
        json={"structured_content": edited_v1_payload},
        headers=_csrf_headers(csrf),
    )
    assert resp_edit_v1.status_code == 200

    regen = regenerate_material_version(
        db_session,
        user,
        mat.id,
        MaterialRegenerateRequest(user_instructions="Regenerando v3 a partir de v1 ativa"),
    )
    assert regen.versions[0].version_number == 3
    assert regen.versions[0].parent_version_id == v1.id


def test_tc443_13_rejected_version_restrictions_across_all_operations(
    make_client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """TC-443-13: Bloqueio de edição, derivação, aprovação, vínculo, exportação e download sobre versão rejeitada."""
    monkeypatch.setattr(
        "app.services.materials.ai.orchestrator.get_settings",
        lambda: _ai_enabled_settings(),
    )
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "tc443_13@example.com")
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    # Não pode rejeitar versão que não seja ai_assisted
    assert (
        client.post(
            f"/api/v1/materials/{mat.id}/versions/{v1.id}/reject-ai",
            headers=_csrf_headers(csrf),
        ).status_code
        == 409
    )

    provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Resumo aprimorado com Python, FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                }
            ],
        }
    )
    app.dependency_overrides[get_optional_llm_provider] = lambda: provider
    try:
        resp_enhance = client.post(
            f"/api/v1/materials/{mat.id}/versions/{v1.id}/ai-enhance",
            json={"target_slot_ids": ["summary"]},
            headers=_csrf_headers(csrf),
        )
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)

    v2_id = resp_enhance.json()["versions"][0]["id"]
    assert (
        client.post(
            f"/api/v1/materials/{mat.id}/versions/{v2_id}/reject-ai",
            headers=_csrf_headers(csrf),
        ).status_code
        == 200
    )

    # 1) Rejeitar novamente -> 409
    assert (
        client.post(
            f"/api/v1/materials/{mat.id}/versions/{v2_id}/reject-ai",
            headers=_csrf_headers(csrf),
        ).status_code
        == 409
    )
    # 2) Aprovar versão rejeitada -> 409
    assert (
        client.post(
            f"/api/v1/materials/{mat.id}/versions/{v2_id}/approve",
            headers=_csrf_headers(csrf),
        ).status_code
        == 409
    )
    # 3) Editar versão rejeitada -> 409
    assert (
        client.put(
            f"/api/v1/materials/{mat.id}/versions/{v2_id}",
            json={"structured_content": v1.structured_content.model_dump(mode="json")},
            headers=_csrf_headers(csrf),
        ).status_code
        == 409
    )
    # 4) Derivar a partir de versão rejeitada -> 409
    assert (
        client.post(
            f"/api/v1/materials/{mat.id}/versions/{v2_id}/derive",
            json={},
            headers=_csrf_headers(csrf),
        ).status_code
        == 409
    )
    # 5) Aprimorar com IA a partir de versão rejeitada -> 409
    assert (
        client.post(
            f"/api/v1/materials/{mat.id}/versions/{v2_id}/ai-enhance",
            json={},
            headers=_csrf_headers(csrf),
        ).status_code
        == 409
    )
    # 6) Exportar texto/markdown de versão rejeitada -> 422
    assert (
        client.get(
            f"/api/v1/materials/{mat.id}/versions/{v2_id}/export?format=markdown",
        ).status_code
        == 422
    )
    # 7) Baixar PDF/DOCX de versão rejeitada (mesmo com allow_draft=true) -> 422
    assert (
        client.get(
            f"/api/v1/materials/{mat.id}/versions/{v2_id}/download?format=pdf&allow_draft=true",
        ).status_code
        == 422
    )


def test_tc443_14_ai_version_immutability_derive_and_approve_flows(
    db_session: Session,
):
    """TC-443-14: Versão ai_assisted é imutável via PUT; permite aprovação direta ou derivação para edição."""
    user = create_user_account(
        db_session,
        email="tc443_14@example.com",
        display_name="TC 14",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Desenvolvedor Python Backend com experiência confirmada em FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                }
            ],
        }
    )
    enhanced = enhance_material_version_with_ai(
        db_session,
        user,
        material_id=mat.id,
        version_id=v1.id,
        payload=MaterialAIEnhanceRequest(target_slot_ids=["summary"]),
        injected_provider=provider,
        settings_override=cfg,
    )
    v2 = enhanced.versions[0]
    assert v2.origin == "ai_assisted"
    assert v2.is_mutable is False

    # PUT direto em v2 (ai_assisted) é bloqueado mesmo sendo a versão ativa mais recente
    with pytest.raises(MaterialImmutableError):
        update_material_version(
            db_session,
            user,
            mat.id,
            v2.id,
            MaterialVersionUpdateRequest(
                structured_content=v2.structured_content.model_dump(mode="json")
            ),
        )

    # Derivar v3 a partir de v2 cria rascunho mutável (origin="derived") e remove ai_overlay do snapshot derivado
    derived = derive_material_version(
        db_session,
        user,
        mat.id,
        v2.id,
        MaterialVersionDeriveRequest(user_instructions="Derivada para ajuste manual"),
    )
    v3 = derived.versions[0]
    assert v3.version_number == 3
    assert v3.origin == "derived"
    assert v3.parent_version_id == v2.id
    assert v3.is_mutable is True
    assert "ai_overlay" not in v3.source_facts_snapshot

    # Como v2 agora possui filha dependente (v3), v2 não pode mais ser rejeitada
    with pytest.raises(AIReviewStateError):
        reject_ai_assisted_version(
            db_session,
            user,
            material_id=mat.id,
            version_id=v2.id,
        )

    # Aprovar v2 diretamente também funciona (e bloqueia rejeição posterior)
    approved = approve_material_version(db_session, user, mat.id, v2.id)
    v2_approved = next(v for v in approved.versions if v.id == v2.id)
    assert v2_approved.is_approved is True
    with pytest.raises(AIReviewStateError):
        reject_ai_assisted_version(
            db_session,
            user,
            material_id=mat.id,
            version_id=v2.id,
        )


def test_tc443_15_toctou_concurrent_modification_during_provider_call(
    db_engine,
    db_session: Session,
):
    """TC-443-15: Modificação concorrente da versão-fonte ou vínculo durante o provider aborta com 409 (stale_source_version)."""
    user = create_user_account(
        db_session,
        email="tc443_15@example.com",
        display_name="TC 15",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    SessionMaker = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def _provider_with_concurrent_approval(_req: LLMStructuredRequest) -> dict[str, Any]:
        # Enquanto o provider executa fora de transação, outra sessão aprova v1 concorrentemente
        with SessionMaker() as concurrent_db:
            approve_material_version(concurrent_db, user, mat.id, v1.id)
        return {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Desenvolvedor Python Backend com atuação confirmada em FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                }
            ],
        }

    provider = _CallbackLLMProvider(_provider_with_concurrent_approval)

    with pytest.raises(AIStaleSourceVersionError):
        enhance_material_version_with_ai(
            db_session,
            user,
            material_id=mat.id,
            version_id=v1.id,
            payload=MaterialAIEnhanceRequest(target_slot_ids=["summary"]),
            injected_provider=provider,
            settings_override=cfg,
        )

    db_session.expire_all()
    reloaded = get_material_detail(db_session, user, mat.id)
    # Nenhuma versão v2 órfã foi criada
    assert len(reloaded.versions) == 1
    assert reloaded.versions[0].is_approved is True

    # Ledger registrou failed com error_code="stale_source_version" e circuit breaker continua closed
    ledger = db_session.scalar(
        select(AIUsageLedger).where(AIUsageLedger.material_id == mat.id)
    )
    assert ledger is not None
    assert ledger.status == AIUsageStatus.FAILED.value
    assert ledger.error_code == "stale_source_version"
    assert get_circuit_state(db_session, provider_key="mock").state == AICircuitState.CLOSED


def test_tc443_16_parallel_ai_enhance_race_condition_exclusivity(
    db_engine,
    db_session: Session,
):
    """TC-443-16: Duas chamadas concorrentes de ai-enhance para (material_id, version_id) serializam no lock sem duplicar versão."""
    user = create_user_account(
        db_session,
        email="tc443_16@example.com",
        display_name="TC 16",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    barrier = threading.Barrier(2)
    SessionMaker = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def _synced_handler(_req: LLMStructuredRequest) -> dict[str, Any]:
        barrier.wait(timeout=10.0)
        return {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Desenvolvedor Python com atuação confirmada em FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                }
            ],
        }

    provider = _CallbackLLMProvider(_synced_handler)
    outcomes: list[str] = []
    lock = threading.Lock()

    def _worker() -> None:
        with SessionMaker() as worker_db:
            try:
                enhance_material_version_with_ai(
                    worker_db,
                    user,
                    material_id=mat.id,
                    version_id=v1.id,
                    payload=MaterialAIEnhanceRequest(target_slot_ids=["summary"]),
                    session_factory=SessionMaker,
                    injected_provider=provider,
                    settings_override=cfg,
                )
                with lock:
                    outcomes.append("success")
            except AIStaleSourceVersionError:
                with lock:
                    outcomes.append("stale_conflict")

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join(timeout=20.0)
    t2.join(timeout=20.0)

    assert sorted(outcomes) == ["stale_conflict", "success"]

    db_session.expire_all()
    reloaded = get_material_detail(db_session, user, mat.id)
    assert len(reloaded.versions) == 2
    assert reloaded.versions[0].version_number == 2
    assert reloaded.versions[0].origin == "ai_assisted"

    ledgers = list(
        db_session.scalars(
            select(AIUsageLedger).where(AIUsageLedger.material_id == mat.id)
        ).all()
    )
    assert len(ledgers) == 2
    statuses = sorted(entry.status for entry in ledgers)
    assert statuses == [AIUsageStatus.COMPLETED.value, AIUsageStatus.FAILED.value]


def test_tc443_17_atomic_rollback_and_ambiguous_commit_contingency(
    db_engine,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """TC-443-17: Rollback atômico quando confirmação do ledger falha + reconciliação de commit ambíguo."""
    user = create_user_account(
        db_session,
        email="tc443_17@example.com",
        display_name="TC 17",
        password="StrongPass!2026",
    )
    facts = _seed_confirmed_facts_and_opportunity(db_session, user.id)
    cfg = _ai_enabled_settings()

    mat = create_material(
        db_session,
        user,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1 = mat.versions[0]

    provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Desenvolvedor Python com atuação confirmada em FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts["profile_key"], facts["experience_key"]],
                }
            ],
        }
    )

    # Parte A: Falha na confirmação do ledger após o flush de new_version -> rollback atômico (sem v2 órfã)
    def _failing_confirm(*_args: Any, **_kwargs: Any):
        raise RuntimeError("Simulated database failure before atomic commit")

    with monkeypatch.context() as mp:
        mp.setattr(
            "app.services.materials.ai.execution_guard.confirm_ai_quota_usage",
            _failing_confirm,
        )
        with pytest.raises(RuntimeError, match="Simulated database failure"):
            enhance_material_version_with_ai(
                db_session,
                user,
                material_id=mat.id,
                version_id=v1.id,
                payload=MaterialAIEnhanceRequest(target_slot_ids=["summary"]),
                injected_provider=provider,
                settings_override=cfg,
            )

    db_session.expire_all()
    reloaded_a = get_material_detail(db_session, user, mat.id)
    assert len(reloaded_a.versions) == 1
    failed_ledger = db_session.scalar(
        select(AIUsageLedger).where(AIUsageLedger.material_id == mat.id)
    )
    assert failed_ledger is not None
    assert failed_ledger.status == AIUsageStatus.FAILED.value
    assert failed_ledger.error_code == "persistence_failed"

    # Parte B: Commit ambíguo (db_post.commit() efetivamente comita no banco mas levanta exceção de transporte logo após)
    BaseSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    call_counter = {"post_created": 0}

    def _ambiguous_session_factory() -> Session:
        sess = BaseSession()
        call_counter["post_created"] += 1
        # A 2ª sessão aberta por execute_guarded_ai_call é db_post (1ª é db_pre, 3ª é db_contingency)
        if call_counter["post_created"] == 2:
            real_commit = sess.commit

            def _commit_then_raise() -> None:
                real_commit()
                raise RuntimeError("Simulated ambiguous network drop after DB commit")

            sess.commit = _commit_then_raise  # type: ignore[method-assign]
        return sess

    recovered_res = enhance_material_version_with_ai(
        db_session,
        user,
        material_id=mat.id,
        version_id=v1.id,
        payload=MaterialAIEnhanceRequest(target_slot_ids=["summary"]),
        session_factory=_ambiguous_session_factory,
        injected_provider=provider,
        settings_override=cfg,
    )
    assert recovered_res.latest_active_version_number == 2
    assert recovered_res.versions[0].version_number == 2
    assert recovered_res.versions[0].origin == "ai_assisted"

    db_session.expire_all()
    completed_ledger = db_session.scalar(
        select(AIUsageLedger).where(
            AIUsageLedger.material_id == mat.id,
            AIUsageLedger.version_id == recovered_res.versions[0].id,
        )
    )
    assert completed_ledger is not None
    assert completed_ledger.status == AIUsageStatus.COMPLETED.value


def test_tc443_18_multitenant_isolation_and_csrf_enforcement(
    make_client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """TC-443-18: Isolamento estrito entre usuários (404 uniforme sem consumir cota) e proteção CSRF (403)."""
    monkeypatch.setattr(
        "app.services.materials.ai.orchestrator.get_settings",
        lambda: _ai_enabled_settings(),
    )
    user_a, client_a, csrf_a = _seed_user_and_csrf(make_client, db_session, "user_a_443@example.com")
    user_b, client_b, csrf_b = _seed_user_and_csrf(make_client, db_session, "user_b_443@example.com")
    facts_a = _seed_confirmed_facts_and_opportunity(db_session, user_a.id)

    mat_a = create_material(
        db_session,
        user_a,
        MaterialCreateRequest(
            material_type="resume",
            opportunity_id=facts_a["opportunity"].id,
            target_language="pt-BR",
        ),
    )
    v1_a = mat_a.versions[0]

    provider = _CallbackLLMProvider(
        lambda _req: {
            "schema_version": 1,
            "material_type": "resume",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "summary",
                    "suggested_text": "Desenvolvedor Python com atuação confirmada em FastAPI e PostgreSQL.",
                    "cited_fact_keys": [facts_a["profile_key"], facts_a["experience_key"]],
                }
            ],
        }
    )

    app.dependency_overrides[get_optional_llm_provider] = lambda: provider
    try:
        # 1) Requisição sem cabeçalho X-CSRF-Token falha com 403 Forbidden
        resp_no_csrf = client_a.post(
            f"/api/v1/materials/{mat_a.id}/versions/{v1_a.id}/ai-enhance",
            json={},
        )
        assert resp_no_csrf.status_code == 403

        # 2) Usuário B tentando aprimorar material do Usuário A recebe 404 uniforme sem chamar o provider
        resp_cross_enhance = client_b.post(
            f"/api/v1/materials/{mat_a.id}/versions/{v1_a.id}/ai-enhance",
            json={},
            headers=_csrf_headers(csrf_b),
        )
        assert resp_cross_enhance.status_code == 404
        assert len(provider.captured_requests) == 0

        # Usuário A cria versão v2 ai_assisted
        resp_ok = client_a.post(
            f"/api/v1/materials/{mat_a.id}/versions/{v1_a.id}/ai-enhance",
            json={"target_slot_ids": ["summary"]},
            headers=_csrf_headers(csrf_a),
        )
        assert resp_ok.status_code == 201
        v2_a_id = resp_ok.json()["versions"][0]["id"]

        # 3) Usuário B tentando rejeitar v2_a do Usuário A recebe 404 uniforme
        resp_cross_reject = client_b.post(
            f"/api/v1/materials/{mat_a.id}/versions/{v2_a_id}/reject-ai",
            headers=_csrf_headers(csrf_b),
        )
        assert resp_cross_reject.status_code == 404

        # 4) Requisição de reject-ai sem CSRF falha com 403
        resp_reject_no_csrf = client_a.post(
            f"/api/v1/materials/{mat_a.id}/versions/{v2_a_id}/reject-ai",
        )
        assert resp_reject_no_csrf.status_code == 403
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)

    # Zero registros no ledger para user_b
    b_ledger_count = db_session.scalar(
        select(func.count(AIUsageLedger.id)).where(AIUsageLedger.user_id == user_b.id)
    )
    assert b_ledger_count == 0
