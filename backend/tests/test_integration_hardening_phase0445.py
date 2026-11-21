from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.materials import get_optional_llm_provider
from app.core.config import Settings
from app.main import app
from app.models.ai_usage import AIUsageLedger, AIUsageStatus
from app.models.application import ApplicationStatusHistory
from app.models.opportunity import (
    EmploymentType,
    Opportunity,
    OpportunityType,
    ProfessionalArea,
    SeniorityLevel,
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
from app.services.auth_service import create_user_account
from app.services.materials.ai import (
    LLMProvider,
    LLMStructuredRequest,
    LLMStructuredResponse,
    LLMTokenUsage,
)
from app.services.opportunities.sync_service import ensure_default_sources
from tests.test_foundation_phase01 import login_and_get_csrf


class _IntegrationMockProvider(LLMProvider):
    """Provider determinístico de teste para jornada integrada da Subfase 04.4.5."""

    def __init__(self, handler) -> None:
        self._handler = handler

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-integration-0445"

    def generate_structured(self, request: LLMStructuredRequest) -> LLMStructuredResponse:
        return LLMStructuredResponse(
            data=self._handler(request),
            provider_name=self.provider_name,
            model_name=self.model_name,
            latency_ms=10,
            token_usage=LLMTokenUsage(input_tokens=220, output_tokens=110),
        )


def _seed_confirmed_and_unconfirmed_profile(
    db: Session,
    *,
    email: str,
    display_name: str,
    confirmed_company: str,
    unconfirmed_skill: str,
) -> tuple[Any, dict[str, str]]:
    user = create_user_account(
        db,
        email=email,
        display_name=display_name,
        password="StrongPassword123!",
        is_admin=False,
    )
    db.flush()

    profile = ProfessionalProfile(
        user_id=user.id,
        full_name=display_name,
        professional_email=email,
        city="São Paulo",
        state="SP",
        country="Brasil",
        professional_title="Desenvolvedor Backend Python",
        professional_summary="Desenvolvimento de APIs REST com Python, FastAPI e PostgreSQL.",
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    exp = WorkExperience(
        user_id=user.id,
        company=confirmed_company,
        role="Desenvolvedor Backend Júnior",
        experience_type=ExperienceType.JUNIOR.value,
        start_date=date(2024, 1, 1),
        is_current=True,
        description="Construção de serviços FastAPI com PostgreSQL e testes automatizados.",
        technologies=["Python", "FastAPI", "PostgreSQL"],
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    proj = ProfessionalProject(
        user_id=user.id,
        name="API Pagamentos",
        role="Desenvolvedor Backend",
        description="API modular de processamento assíncrono em Python e FastAPI.",
        technologies=["Python", "FastAPI"],
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    edu = Education(
        user_id=user.id,
        institution="Universidade Exemplo",
        course="Ciência da Computação",
        education_status=EducationStatus.IN_PROGRESS.value,
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    skill_confirmed = Skill(
        user_id=user.id,
        name="Python",
        category="Backend",
        proficiency_level=SkillProficiency.ADVANCED.value,
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    skill_pending = Skill(
        user_id=user.id,
        name=unconfirmed_skill,
        category="Cloud",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
        verification_status=VerificationStatus.PENDING_VALIDATION.value,
    )
    lang = Language(
        user_id=user.id,
        language_name="Inglês",
        proficiency_level=LanguageProficiency.INTERMEDIATE.value,
        verification_status=VerificationStatus.CONFIRMED.value,
    )
    db.add_all([profile, exp, proj, edu, skill_confirmed, skill_pending, lang])
    db.commit()

    return user, {
        "profile_key": f"profile:{profile.id}",
        "experience_key": f"experience:{exp.id}",
        "project_key": f"project:{proj.id}",
        "skill_key": f"skill:{skill_confirmed.id}",
    }


def test_tc445_01_end_to_end_opportunity_application_material_approval_link_and_export(
    db_session: Session,
    make_client,
):
    """Jornada vertical completa: oportunidade -> compatibilidade -> candidatura -> pipeline/agenda -> material -> aprovação -> vínculo -> exportação PDF/DOCX."""
    sources = {s.slug: s for s in ensure_default_sources(db_session)}
    src = sources["remote_ok"]

    _, _ = _seed_confirmed_and_unconfirmed_profile(
        db_session,
        email="e2e.alice@example.com",
        display_name="Alice Integrada",
        confirmed_company="Orbit Sistemas",
        unconfirmed_skill="KubernetesDraft",
    )

    now = datetime.now(UTC)
    public_opp = Opportunity(
        source_id=src.id,
        external_id="rk-445-e2e-1",
        title="Backend Python Junior Developer",
        company_name="Nebula Labs",
        description="Vaga backend com Python, FastAPI e PostgreSQL.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Worldwide"],
        source_url="https://remoteok.com/remote-jobs/nebula-445",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-445-e2e-1",
    )
    db_session.add(public_opp)
    db_session.commit()

    client: TestClient = make_client(("10.45.0.10", 50000))
    csrf = login_and_get_csrf(client, "e2e.alice@example.com", "StrongPassword123!")
    headers = {"X-CSRF-Token": csrf}

    # 1. Catálogo de oportunidades e compatibilidade com perfil confirmado
    list_opp_resp = client.get("/api/v1/opportunities")
    assert list_opp_resp.status_code == 200
    items = list_opp_resp.json()["items"]
    matched_opp = next((o for o in items if o["id"] == str(public_opp.id)), None)
    assert matched_opp is not None
    assert matched_opp["match"]["eligible"] is True
    assert matched_opp["match"]["overall_compatibility"] in ("compatible", "potential")

    # 2. Criação da candidatura e evolução no pipeline
    create_app_resp = client.post(
        "/api/v1/applications",
        headers=headers,
        json={"opportunity_id": str(public_opp.id), "status": "preparing"},
    )
    assert create_app_resp.status_code == 201, create_app_resp.text
    app_data = create_app_resp.json()
    app_id = app_data["id"]
    assert app_data["role_title"] == "Backend Python Junior Developer"
    assert app_data["company_name"] == "Nebula Labs"

    move_resp = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers=headers,
        json={"status": "interview", "note": "Convite para entrevista técnica"},
    )
    assert move_resp.status_code == 200, move_resp.text

    # 3. Entrevista, interação externa e verificação de coerência na agenda
    interview_at = (now + timedelta(days=2)).replace(microsecond=0).isoformat()
    iv_resp = client.post(
        f"/api/v1/applications/{app_id}/interviews",
        headers=headers,
        json={
            "round_name": "Entrevista Técnica Backend",
            "interview_format": "online",
            "scheduled_at": interview_at,
            "duration_minutes": 45,
        },
    )
    assert iv_resp.status_code == 201, iv_resp.text

    ext_resp = client.post(
        f"/api/v1/applications/{app_id}/external-interaction",
        headers=headers,
        json={
            "interaction_type": "email",
            "interaction_at": now.replace(microsecond=0).isoformat(),
            "note": "Recrutadora confirmou horário.",
        },
    )
    assert ext_resp.status_code == 200, ext_resp.text

    agenda_resp = client.get("/api/v1/applications/agenda")
    assert agenda_resp.status_code == 200, agenda_resp.text
    agenda_json = agenda_resp.json()
    assert any(ev["application_id"] == app_id for ev in agenda_json["events"])

    # Histórico imutável de status preservado
    history_rows = db_session.scalars(
        select(ApplicationStatusHistory).where(
            ApplicationStatusHistory.application_id == public_opp.id
        )
    ).all()
    assert len(history_rows) == 0  # garante que FK usa application.id, não opportunity.id
    app_detail = client.get(f"/api/v1/applications/{app_id}").json()
    assert len(app_detail["status_history"]) >= 2
    assert app_detail["last_external_interaction_note"] == "Recrutadora confirmou horário."

    # 4. Pré-análise e geração determinística de material (sem usar skill pendente)
    pre_resp = client.post(
        "/api/v1/materials/pre-analyze",
        headers=headers,
        json={
            "opportunity_id": str(public_opp.id),
            "application_id": app_id,
            "material_type": "resume",
            "target_language": "pt-BR",
        },
    )
    assert pre_resp.status_code == 200, pre_resp.text
    pre_data = pre_resp.json()
    assert pre_data["can_generate"] is True
    assert any("KubernetesDraft" in w["label"] for w in pre_data["unconfirmed_warnings"])

    mat_resp = client.post(
        "/api/v1/materials",
        headers=headers,
        json={
            "opportunity_id": str(public_opp.id),
            "application_id": app_id,
            "material_type": "resume",
            "target_language": "pt-BR",
            "title": "Currículo Nebula Labs",
        },
    )
    assert mat_resp.status_code == 201, mat_resp.text
    mat_data = mat_resp.json()
    mat_id = mat_data["id"]
    v1_id = mat_data["versions"][0]["id"]
    assert "KubernetesDraft" not in mat_data["versions"][0]["rendered_markdown"]
    assert "Orbit Sistemas" in mat_data["versions"][0]["rendered_markdown"]

    # 5. Aprovação explícita, vínculo à candidatura e exportação PDF/DOCX
    approve_resp = client.post(
        f"/api/v1/materials/{mat_id}/versions/{v1_id}/approve",
        headers=headers,
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["versions"][0]["is_approved"] is True

    link_resp = client.post(
        f"/api/v1/materials/{mat_id}/link",
        headers=headers,
        json={"application_id": app_id, "version_id": v1_id},
    )
    assert link_resp.status_code == 200, link_resp.text

    pdf_resp = client.get(
        f"/api/v1/materials/{mat_id}/versions/{v1_id}/download?format=pdf&template=classic_ats"
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF-")

    docx_resp = client.get(
        f"/api/v1/materials/{mat_id}/versions/{v1_id}/download?format=docx&template=classic_ats"
    )
    assert docx_resp.status_code == 200
    assert docx_resp.content.startswith(b"PK")


def test_tc445_02_ai_studio_rejection_preserves_linked_approved_v1_and_candidate_listings(
    db_session: Session,
    make_client,
    monkeypatch: pytest.MonkeyPatch,
):
    """Ciclo integrado: v1 aprovada e vinculada -> v2 ai_assisted -> rejeição de v2 -> recuperação de v1 ativa nas listagens e bloqueio em v2."""
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "ai_assisted_enabled", True)
    monkeypatch.setattr(config_module.settings, "ai_provider", "mock")

    user, keys = _seed_confirmed_and_unconfirmed_profile(
        db_session,
        email="ai.cycle@example.com",
        display_name="Carla Revisora",
        confirmed_company="Vortex Engenharia",
        unconfirmed_skill="RustDraft",
    )

    client: TestClient = make_client(("10.45.0.20", 50000))
    csrf = login_and_get_csrf(client, "ai.cycle@example.com", "StrongPassword123!")
    headers = {"X-CSRF-Token": csrf}

    # Oportunidade manual privada -> candidatura -> carta de apresentação v1 aprovada e vinculada
    opp_resp = client.post(
        "/api/v1/opportunities/manual",
        headers=headers,
        json={
            "title": "Backend Python Developer",
            "company_name": "Helios Tech",
            "source_url": "https://example.com/helios-backend",
            "description": "Desenvolvimento backend em Python e FastAPI.",
            "opportunity_type": "junior",
            "work_mode": "remote",
            "employment_type": "pj",
        },
    )
    assert opp_resp.status_code == 201, opp_resp.text
    opp_id = opp_resp.json()["id"]

    app_resp = client.post(
        "/api/v1/applications",
        headers=headers,
        json={"opportunity_id": opp_id, "status": "preparing"},
    )
    assert app_resp.status_code == 201, app_resp.text
    app_id = app_resp.json()["id"]

    mat_resp = client.post(
        "/api/v1/materials",
        headers=headers,
        json={
            "opportunity_id": opp_id,
            "application_id": app_id,
            "material_type": "cover_letter",
            "target_language": "pt-BR",
            "title": "Carta Helios Tech",
        },
    )
    assert mat_resp.status_code == 201, mat_resp.text
    mat_id = mat_resp.json()["id"]
    v1_id = mat_resp.json()["versions"][0]["id"]

    assert (
        client.post(f"/api/v1/materials/{mat_id}/versions/{v1_id}/approve", headers=headers).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/materials/{mat_id}/link",
            headers=headers,
            json={"application_id": app_id, "version_id": v1_id},
        ).status_code
        == 200
    )

    # Provider mockado gera sugestão grounded em fatos confirmados de v1
    def _mock_handler(_req: LLMStructuredRequest) -> dict[str, Any]:
        return {
            "material_type": "cover_letter",
            "target_language": "pt-BR",
            "suggestions": [
                {
                    "slot_id": "opening",
                    "suggested_text": (
                        "Atuo em desenvolvimento backend com Python e FastAPI na Vortex Engenharia, "
                        "construindo serviços estruturados e testados."
                    ),
                    "cited_fact_keys": [keys["experience_key"]],
                }
            ],
        }

    app.dependency_overrides[get_optional_llm_provider] = lambda: _IntegrationMockProvider(_mock_handler)
    try:
        enhance_resp = client.post(
            f"/api/v1/materials/{mat_id}/versions/{v1_id}/ai-enhance",
            headers=headers,
            json={"target_slot_ids": ["opening"], "user_instructions": "Seja objetiva"},
        )
        assert enhance_resp.status_code == 201, enhance_resp.text
        enhanced = enhance_resp.json()
        v2 = next(v for v in enhanced["versions"] if v["version_number"] == 2)
        assert v2["origin"] == "ai_assisted"
        assert v2["is_approved"] is False
        assert v2["is_rejected"] is False
        assert v2["is_mutable"] is False
        assert v2["parent_version_id"] == v1_id
        assert v2["source_facts_snapshot"]["ai_overlay"]["applied_slot_ids"] == ["opening"]

        # Ledger registrado e confirmado para a versão v2
        ledger_rows = db_session.scalars(
            select(AIUsageLedger).where(AIUsageLedger.user_id == user.id)
        ).all()
        assert len(ledger_rows) == 1
        assert ledger_rows[0].status == AIUsageStatus.COMPLETED.value
        assert str(ledger_rows[0].version_id) == v2["id"]

        # Rejeição persistida de v2
        reject_resp = client.post(
            f"/api/v1/materials/{mat_id}/versions/{v2['id']}/reject-ai",
            headers=headers,
        )
        assert reject_resp.status_code == 200, reject_resp.text
        after_reject = reject_resp.json()
        assert after_reject["latest_version_number"] == 2
        assert after_reject["latest_active_version_number"] == 1
        assert after_reject["latest_active_version_id"] == v1_id

        v1_after = next(v for v in after_reject["versions"] if v["id"] == v1_id)
        v2_after = next(v for v in after_reject["versions"] if v["id"] == v2["id"])
        assert v1_after["is_approved"] is True
        assert v1_after["is_mutable"] is False  # permanece imutável por estar aprovada e vinculada
        assert v2_after["is_rejected"] is True
        assert v2_after["rejected_at"] is not None

        # Listagens da candidatura e geral preservam v1 como ativa e vinculada
        linked_list = client.get(f"/api/v1/materials?application_id={app_id}").json()
        assert len(linked_list) == 1
        assert linked_list[0]["latest_version_number"] == 2
        assert linked_list[0]["latest_active_version_number"] == 1
        assert linked_list[0]["latest_active_version_id"] == v1_id
        assert linked_list[0]["linked_version_id"] == v1_id
        assert linked_list[0]["linked_version_number"] == 1
        assert linked_list[0]["linked_version_is_approved"] is True

        # Operações incompatíveis sobre v2 rejeitada são bloqueadas
        assert (
            client.post(f"/api/v1/materials/{mat_id}/versions/{v2['id']}/approve", headers=headers).status_code
            == 409
        )
        assert (
            client.post(f"/api/v1/materials/{mat_id}/versions/{v2['id']}/derive", headers=headers, json={}).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/materials/{mat_id}/link",
                headers=headers,
                json={"application_id": app_id, "version_id": v2["id"]},
            ).status_code
            in (409, 422)
        )
        assert (
            client.get(f"/api/v1/materials/{mat_id}/versions/{v2['id']}/export?format=markdown").status_code
            in (409, 422)
        )
        assert (
            client.get(f"/api/v1/materials/{mat_id}/versions/{v2['id']}/download?format=pdf&allow_draft=true").status_code
            in (409, 422)
        )

        # v1 continua exportável normalmente
        assert (
            client.get(f"/api/v1/materials/{mat_id}/versions/{v1_id}/download?format=pdf").status_code
            == 200
        )
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)


def test_tc445_03_multiuser_isolation_and_session_csrf_across_all_modules(
    db_session: Session,
    make_client,
    monkeypatch: pytest.MonkeyPatch,
):
    """Isolamento integrado entre dois usuários independentes (perfil, oportunidade privada, candidatura, material, IA, sessão e CSRF)."""
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "ai_assisted_enabled", True)
    monkeypatch.setattr(config_module.settings, "ai_provider", "mock")

    user_a, keys_a = _seed_confirmed_and_unconfirmed_profile(
        db_session,
        email="iso.a@example.com",
        display_name="Usuário A",
        confirmed_company="Alpha Corp",
        unconfirmed_skill="DraftA",
    )
    user_b, _ = _seed_confirmed_and_unconfirmed_profile(
        db_session,
        email="iso.b@example.com",
        display_name="Usuário B",
        confirmed_company="Beta Corp",
        unconfirmed_skill="DraftB",
    )

    client_a: TestClient = make_client(("10.45.0.31", 50000))
    csrf_a = login_and_get_csrf(client_a, "iso.a@example.com", "StrongPassword123!")
    headers_a = {"X-CSRF-Token": csrf_a}

    client_b: TestClient = make_client(("10.45.0.32", 50000))
    csrf_b = login_and_get_csrf(client_b, "iso.b@example.com", "StrongPassword123!")
    headers_b = {"X-CSRF-Token": csrf_b}

    # Usuário A cria oportunidade privada, candidatura e material
    opp_a = client_a.post(
        "/api/v1/opportunities/manual",
        headers=headers_a,
        json={
            "title": "Vaga Privada Alpha",
            "company_name": "Alpha Privada",
            "source_url": "https://example.com/alpha-private",
            "description": "Vaga exclusiva do usuário A.",
            "opportunity_type": "junior",
            "work_mode": "remote",
            "employment_type": "pj",
        },
    )
    assert opp_a.status_code == 201
    opp_a_id = opp_a.json()["id"]

    app_a = client_a.post(
        "/api/v1/applications",
        headers=headers_a,
        json={"opportunity_id": opp_a_id, "status": "preparing"},
    )
    assert app_a.status_code == 201
    app_a_id = app_a.json()["id"]

    mat_a = client_a.post(
        "/api/v1/materials",
        headers=headers_a,
        json={
            "opportunity_id": opp_a_id,
            "application_id": app_a_id,
            "material_type": "resume",
            "target_language": "pt-BR",
        },
    )
    assert mat_a.status_code == 201
    mat_a_id = mat_a.json()["id"]
    v1_a_id = mat_a.json()["versions"][0]["id"]

    # Usuário B não vê oportunidade privada de A nem consegue criar candidatura ou material sobre ela
    assert client_b.get(f"/api/v1/opportunities/{opp_a_id}").status_code == 404
    assert (
        client_b.post(
            "/api/v1/applications",
            headers=headers_b,
            json={"opportunity_id": opp_a_id, "status": "interested"},
        ).status_code
        == 404
    )

    # Usuário B não acessa candidatura nem material de A (nem aprova, deriva, vincula, exporta ou aciona IA)
    assert client_b.get(f"/api/v1/applications/{app_a_id}").status_code == 404
    assert client_b.get(f"/api/v1/materials/{mat_a_id}").status_code == 404
    assert (
        client_b.post(
            f"/api/v1/materials/{mat_a_id}/versions/{v1_a_id}/approve",
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client_b.post(
            f"/api/v1/materials/{mat_a_id}/versions/{v1_a_id}/derive",
            headers=headers_b,
            json={},
        ).status_code
        == 404
    )
    assert (
        client_b.post(
            f"/api/v1/materials/{mat_a_id}/versions/{v1_a_id}/reject-ai",
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client_b.get(
            f"/api/v1/materials/{mat_a_id}/versions/{v1_a_id}/download?format=pdf&allow_draft=true"
        ).status_code
        == 404
    )

    # Tentativa de Usuário B acionar AI enhance no material de A retorna 404 e não consome ledger/quota
    def _should_not_run(_req: LLMStructuredRequest) -> dict[str, Any]:
        raise AssertionError("Provider não deve ser chamado para material de outro usuário.")

    app.dependency_overrides[get_optional_llm_provider] = lambda: _IntegrationMockProvider(_should_not_run)
    try:
        ai_cross = client_b.post(
            f"/api/v1/materials/{mat_a_id}/versions/{v1_a_id}/ai-enhance",
            headers=headers_b,
            json={},
        )
        assert ai_cross.status_code == 404
        ledger_all = db_session.scalars(select(AIUsageLedger)).all()
        assert len(ledger_all) == 0
    finally:
        app.dependency_overrides.pop(get_optional_llm_provider, None)

    # Proteção CSRF em mutações e revogação de sessão no logout
    no_csrf = client_a.post(
        f"/api/v1/materials/{mat_a_id}/versions/{v1_a_id}/approve",
    )
    assert no_csrf.status_code == 403

    logout_resp = client_a.post("/api/v1/auth/logout", headers=headers_a)
    assert logout_resp.status_code == 200
    assert client_a.get("/api/v1/profile").status_code == 401
    assert user_a.id != user_b.id
    assert keys_a["experience_key"].startswith("experience:")


def test_tc445_04_default_safe_config_security_headers_and_production_mock_guard(
    make_client,
):
    """Confirma defaults seguros de IA (disabled), bloqueio de mock em produção e headers de segurança HTTP."""
    defaults = Settings(_env_file=None, secret_key="a" * 40)
    assert defaults.ai_assisted_enabled is False
    assert defaults.ai_provider == "disabled"

    with pytest.raises(ValidationError, match="AI_PROVIDER='mock'"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="ProdKey!9876543210_UniqueChars_XYZ_0445",
            cookie_secure=True,
            cors_origins="https://jobhunter.ctrls.dev.br",
            ai_assisted_enabled=True,
            ai_provider="mock",
        )

    client: TestClient = make_client(("10.45.0.40", 50000))
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.headers.get("X-Content-Type-Options") == "nosniff"
    assert health.headers.get("X-Frame-Options") == "DENY"
    assert health.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
