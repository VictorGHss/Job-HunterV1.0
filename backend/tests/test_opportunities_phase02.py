from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.cli import main as cli_main
from app.models.opportunity import (
    EmploymentType,
    ExperienceRequirementMode,
    ExternalSourceStatus,
    Opportunity,
    OpportunitySource,
    OpportunitySourceLink,
    OpportunitySyncRun,
    OpportunityType,
    OpportunityUserState,
    ProfessionalArea,
    SeniorityLevel,
    SyncRunStatus,
    WorkMode,
)
from app.models.profile import (
    Education,
    EducationStatus,
    ExperienceType,
    ProfessionalProject,
    Skill,
    SkillProficiency,
    WorkExperience,
)
from app.services.auth_service import create_user_account
from app.services.opportunities.classification import (
    classify_experience_requirements,
    classify_opportunity,
)
from app.services.opportunities.connectors.base import (
    ConnectorFetchError,
    ConnectorPayloadError,
)
from app.services.opportunities.connectors.github_vagas import (
    GitHubBackendBRConnector,
    GitHubFrontendBRConnector,
    redact_contact_pii,
)
from app.services.opportunities.connectors.himalayas import HimalayasConnector
from app.services.opportunities.connectors.jobicy import JobicyConnector
from app.services.opportunities.connectors.remote_ok import RemoteOKConnector
from app.services.opportunities.connectors.remotive import RemotiveConnector
from app.services.opportunities.matching import evaluate_opportunity_for_user
from app.services.opportunities.sanitization import (
    normalize_canonical_url,
    sanitize_external_html_text,
    validate_safe_external_url,
)
from app.services.opportunities.sync_service import reclassify_opportunities, sync_sources
from app.services.profile_service import get_or_create_profile


def login_and_get_csrf(client, email: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def sample_remote_ok_payload() -> list[dict]:
    return [
        {"legal": "Notice: attribution required for Remote OK feed."},
        {
            "id": "109001",
            "position": "Junior Python Backend Engineer",
            "company": "Acme Cloud",
            "tags": ["python", "fastapi", "postgresql"],
            "location": "Worldwide",
            "salary_min": 45000,
            "salary_max": 60000,
            "salary_currency": "USD",
            "description": "<p>Build <b>FastAPI</b> services and PostgreSQL APIs.</p><script>alert(1)</script>",
            "url": "https://remoteok.com/remote-jobs/junior-python-backend-109001?utm_source=feed",
            "apply_url": "https://jobs.example.com/apply/109001",
            "date": "2026-11-10T12:00:00+00:00",
        },
        {
            "id": "109002",
            "position": "Backend Engineering Intern",
            "company": "DevLab Global",
            "tags": ["intern", "python", "api"],
            "location": "USA only",
            "description": "<p>Internship helping with backend APIs in Python.</p>",
            "url": "https://remoteok.com/remote-jobs/backend-intern-109002",
            "date": "2026-11-11T12:00:00+00:00",
        },
    ]


def sample_remotive_payload() -> dict:
    return {
        "job-count": 2,
        "jobs": [
            {
                "id": 208001,
                "title": "Freelance Full Stack Python Developer",
                "company_name": "Studio Norte",
                "category": "Software Development",
                "job_type": "freelance",
                "publication_date": "2026-11-12T08:30:00",
                "candidate_required_location": "LATAM, Brazil",
                "salary": "$40 - $60 / hour",
                "description": "<p>Freelance project building React and FastAPI microservices.</p>",
                "tags": ["python", "react", "typescript"],
                "url": "https://remotive.com/remote-jobs/software-dev/freelance-python-208001",
            },
            {
                "id": 208002,
                "title": "Junior Frontend Developer",
                "company_name": "Remote Ambiguous Co",
                "category": "Software Development",
                "job_type": "full_time",
                "publication_date": "2026-11-09T10:00:00",
                "candidate_required_location": "",
                "salary": "",
                "description": "<p>React and TypeScript developer role with clean UI focus.</p>",
                "tags": ["react", "typescript"],
                "url": "https://remotive.com/remote-jobs/software-dev/junior-frontend-208002",
            },
        ],
    }


def test_sanitization_and_url_security():
    cleaned = sanitize_external_html_text(
        "<div>Olá <strong>Dev</strong>!<script>stealCookie()</script><br>Requisitos: Python</div>"
    )
    assert cleaned is not None
    assert "<script>" not in cleaned
    assert "stealCookie" not in cleaned
    assert "Olá Dev" in cleaned
    assert "Requisitos: Python" in cleaned

    canonical = normalize_canonical_url(
        "HTTPS://RemoteOK.com/remote-jobs/123?utm_source=x&ref=abc&id=9#top"
    )
    assert canonical == "https://remoteok.com/remote-jobs/123?id=9"

    for unsafe in [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "http://127.0.0.1:8000/secret",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "https://user:pass@example.com/job",
    ]:
        with pytest.raises(ValueError):
            validate_safe_external_url(unsafe)


def test_remote_ok_and_remotive_parsing_and_retry_limits():
    sleep_calls: list[float] = []
    attempts = {"remote_ok": 0}

    def remote_ok_handler(request: httpx.Request) -> httpx.Response:
        attempts["remote_ok"] += 1
        if attempts["remote_ok"] == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json=sample_remote_ok_payload())

    ok_connector = RemoteOKConnector(
        transport=httpx.MockTransport(remote_ok_handler),
        sleep_fn=lambda s: sleep_calls.append(s),
    )
    ok_drafts = ok_connector.collect()
    assert attempts["remote_ok"] == 2
    assert sleep_calls == [3.0]
    assert len(ok_drafts) == 2

    jr_ok = ok_drafts[0]
    assert jr_ok.external_id == "109001"
    assert jr_ok.opportunity_type == OpportunityType.JUNIOR.value
    assert jr_ok.work_mode == WorkMode.REMOTE.value
    assert jr_ok.eligible_countries == ["Worldwide"]
    assert jr_ok.eligibility_unknown is False
    assert jr_ok.salary_min == 45000.0
    assert jr_ok.source_url == "https://remoteok.com/remote-jobs/junior-python-backend-109001"
    assert "<script>" not in (jr_ok.description or "")

    intern_ok = ok_drafts[1]
    assert intern_ok.opportunity_type == OpportunityType.INTERNSHIP.value
    assert intern_ok.employment_type == EmploymentType.INTERNSHIP.value
    assert intern_ok.eligible_countries == ["USA only"]

    remotive_connector = RemotiveConnector(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=sample_remotive_payload())
        ),
        sleep_fn=lambda _: None,
    )
    rem_drafts = remotive_connector.collect()
    assert len(rem_drafts) == 2
    assert rem_drafts[0].opportunity_type == OpportunityType.FREELANCE.value
    assert rem_drafts[0].salary_currency == "USD"
    assert rem_drafts[0].salary_period == "hour"
    assert rem_drafts[0].eligible_countries == ["LATAM", "Brazil"]
    assert rem_drafts[1].eligibility_unknown is True

    # Payload acima do limite deve falhar de modo controlado
    oversized_connector = RemoteOKConnector(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b'{"x": "' + b"a" * 500 + b'"}')
        ),
        max_response_bytes=120,
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ConnectorFetchError):
        oversized_connector.collect()

    # JSON malformado ou formato inválido deve falhar sem quebrar o motor
    bad_json_connector = RemotiveConnector(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b"<html>not-json</html>")
        ),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ConnectorPayloadError):
        bad_json_connector.collect()


def test_sync_deduplication_idempotency_intervals_and_conservative_absence(db_session):
    remote_data = sample_remote_ok_payload()
    remotive_calls = {"count": 0}

    def build_connectors(ok_payload=None, fail_ok=False):
        def ok_handler(_):
            if fail_ok:
                return httpx.Response(503)
            return httpx.Response(200, json=ok_payload if ok_payload is not None else remote_data)

        def remotive_handler(_):
            remotive_calls["count"] += 1
            return httpx.Response(500)

        return {
            "remote_ok": RemoteOKConnector(
                transport=httpx.MockTransport(ok_handler),
                max_retries=0,
                sleep_fn=lambda _: None,
            ),
            "remotive": RemotiveConnector(
                transport=httpx.MockTransport(remotive_handler),
                max_retries=0,
                sleep_fn=lambda _: None,
            ),
        }

    # Dry-run não persiste oportunidades e não consulta Remotive desabilitada
    dry_results = sync_sources(
        db_session,
        dry_run=True,
        connector_overrides=build_connectors(),
    )
    assert len(dry_results) == 1
    assert dry_results[0].source_slug == "remote_ok"
    assert dry_results[0].fetched_count == 2 and dry_results[0].inserted_count == 0
    assert remotive_calls["count"] == 0
    assert db_session.execute(select(Opportunity)).scalars().all() == []

    # 1a sincronização real (somente Remote OK ativa)
    first_results = sync_sources(
        db_session,
        connector_overrides=build_connectors(),
    )
    assert len(first_results) == 1
    assert first_results[0].status == SyncRunStatus.SUCCESS.value
    assert first_results[0].inserted_count == 2
    assert remotive_calls["count"] == 0
    opps = db_session.execute(select(Opportunity).order_by(Opportunity.external_id)).scalars().all()
    assert len(opps) == 2
    first_seen_snapshot = opps[0].first_seen_at

    # Respeito ao intervalo mínimo sem --force
    skipped_results = sync_sources(
        db_session,
        force=False,
        connector_overrides=build_connectors(),
    )
    assert len(skipped_results) == 1
    assert skipped_results[0].status == SyncRunStatus.SKIPPED.value
    assert remotive_calls["count"] == 0

    # 2a sincronização com atualização sem duplicar (inclui duplicata por URL canônica com external_id alterado)
    updated_ok = sample_remote_ok_payload()
    updated_ok[1]["position"] = "Junior Python & FastAPI Engineer"
    updated_ok[2]["id"] = "999999"
    second_results = sync_sources(
        db_session,
        source_slug="remote_ok",
        force=True,
        connector_overrides=build_connectors(ok_payload=updated_ok),
    )
    assert len(second_results) == 1
    assert second_results[0].updated_count == 2
    assert second_results[0].inserted_count == 0
    # Restaura external_id original para o teste de ausência conservadora abaixo
    updated_ok[2]["id"] = "109002"
    sync_sources(
        db_session,
        source_slug="remote_ok",
        force=True,
        connector_overrides=build_connectors(ok_payload=updated_ok),
    )

    refreshed = db_session.execute(
        select(Opportunity).where(Opportunity.external_id == "109001")
    ).scalar_one()
    assert refreshed.title == "Junior Python & FastAPI Engineer"
    assert refreshed.first_seen_at == first_seen_snapshot

    # Falha da fonte NÃO encerra vagas existentes (e Remotive continua sem requisições)
    partial_failure = sync_sources(
        db_session,
        force=True,
        connector_overrides=build_connectors(fail_ok=True),
    )
    assert len(partial_failure) == 1
    assert partial_failure[0].source_slug == "remote_ok"
    assert partial_failure[0].status == SyncRunStatus.FAILED.value
    assert remotive_calls["count"] == 0

    db_session.expire_all()
    still_active = db_session.execute(
        select(Opportunity).where(Opportunity.external_id == "109001")
    ).scalar_one()
    assert still_active.source_status == ExternalSourceStatus.ACTIVE.value

    # Ausência conservadora: 1 ausência não muda para unknown, 3 ausências consecutivas marcam unknown
    payload_without_109002 = [remote_data[0], remote_data[1]]
    for expected_missing_count, expected_status in [
        (1, ExternalSourceStatus.ACTIVE.value),
        (2, ExternalSourceStatus.ACTIVE.value),
        (3, ExternalSourceStatus.UNKNOWN.value),
    ]:
        sync_sources(
            db_session,
            source_slug="remote_ok",
            force=True,
            connector_overrides=build_connectors(ok_payload=payload_without_109002),
        )
        intern_opp = db_session.execute(
            select(Opportunity).where(Opportunity.external_id == "109002")
        ).scalar_one()
        assert intern_opp.missing_sync_count == expected_missing_count
        assert intern_opp.source_status == expected_status


def test_matching_rules_respect_preferences_geography_and_substantive_data(db_session):
    user = create_user_account(
        db_session,
        email="dev.matching@example.com",
        display_name="Dev Matching",
        password="StrongPassword123!",
        is_admin=False,
    )
    import copy

    profile = get_or_create_profile(db_session, user)
    profile.country = "Brasil"
    prefs = copy.deepcopy(profile.preferences)
    prefs["junior_developer"]["block_clt"] = True
    prefs["junior_developer"]["excluded_areas"] = ["Suporte técnico"]
    prefs["junior_developer"]["priority_areas"] = ["Backend", "Python"]
    prefs["source_restrictions"]["workana_enabled"] = False
    prefs["internships"]["enabled"] = False
    profile.preferences = prefs
    db_session.commit()

    # 1. CLT bloqueado explicitamente
    clt_opp = Opportunity(
        external_id="m1",
        title="Desenvolvedor Júnior Backend CLT",
        description="Vaga CLT para Python e FastAPI.",
        opportunity_type=OpportunityType.JUNIOR.value,
        employment_type=EmploymentType.CLT.value,
        work_mode=WorkMode.REMOTE.value,
        eligible_countries=["Brasil"],
        eligibility_unknown=False,
        requirements=["Python", "FastAPI"],
        technologies=["Python", "FastAPI"],
        source_url="https://example.com/clt",
        content_hash="h1",
    )
    eval_clt = evaluate_opportunity_for_user(clt_opp, profile)
    assert eval_clt.eligible is False
    assert any("block_clt" in r for r in eval_clt.exclusion_reasons)

    # 2. Palavra-chave positiva no título NÃO vence área excluída nem falta de dados substantivos
    excluded_kw_opp = Opportunity(
        external_id="m2",
        title="Python Junior Developer - Suporte técnico N1",
        description="Atendimento de chamados em suporte técnico.",
        opportunity_type=OpportunityType.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        eligible_countries=["Worldwide"],
        eligibility_unknown=False,
        requirements=[],
        technologies=[],
        source_url="https://example.com/suporte",
        content_hash="h2",
    )
    eval_excl = evaluate_opportunity_for_user(excluded_kw_opp, profile)
    assert eval_excl.eligible is False
    assert any("Suporte técnico" in r for r in eval_excl.exclusion_reasons)

    # 3. Palavra-chave apenas no título sem suporte em tecnologias/requisitos/descrição é sinalizada
    title_only_opp = Opportunity(
        external_id="m3",
        title="Junior Python Developer",
        description="Detalhes da stack serão enviados posteriormente.",
        opportunity_type=OpportunityType.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        eligible_countries=["Worldwide"],
        eligibility_unknown=False,
        requirements=[],
        technologies=[],
        source_url="https://example.com/title-only",
        content_hash="h3",
    )
    eval_title_only = evaluate_opportunity_for_user(title_only_opp, profile)
    assert any("Menção apenas no título" in r for r in eval_title_only.inclusion_reasons)

    # 4. Workana bloqueado quando desabilitado nas preferências
    workana_opp = Opportunity(
        external_id="m4",
        title="Projeto Freelance API FastAPI",
        description="API REST em Python.",
        opportunity_type=OpportunityType.FREELANCE.value,
        employment_type=EmploymentType.FREELANCE.value,
        work_mode=WorkMode.REMOTE.value,
        eligible_countries=["Brasil"],
        eligibility_unknown=False,
        requirements=["FastAPI"],
        technologies=["Python"],
        source_url="https://www.workana.com/job/fastapi-api",
        content_hash="h4",
    )
    eval_workana = evaluate_opportunity_for_user(workana_opp, profile)
    assert eval_workana.eligible is False
    assert any("Workana" in r for r in eval_workana.exclusion_reasons)

    # 5. Restrição geográfica "USA only" exclui perfil do Brasil; elegibilidade desconhecida preserva com alerta
    usa_only = Opportunity(
        external_id="m5",
        title="Junior Python Engineer",
        description="Python microservices.",
        opportunity_type=OpportunityType.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        eligible_countries=["USA only"],
        eligibility_unknown=False,
        requirements=["Python"],
        technologies=["Python"],
        source_url="https://example.com/usa-only",
        content_hash="h5",
    )
    eval_usa = evaluate_opportunity_for_user(usa_only, profile)
    assert eval_usa.eligible is False
    assert eval_usa.geographic_eligibility == "excluded"

    unknown_geo = Opportunity(
        external_id="m6",
        title="Junior Python Engineer",
        description="Python microservices.",
        opportunity_type=OpportunityType.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        eligible_countries=[],
        eligibility_unknown=True,
        requirements=["Python"],
        technologies=["Python"],
        source_url="https://example.com/unknown-geo",
        content_hash="h6",
    )
    eval_unknown = evaluate_opportunity_for_user(unknown_geo, profile)
    assert eval_unknown.eligible is True
    assert eval_unknown.geographic_eligibility == "unknown"
    assert any("não especificada" in r for r in eval_unknown.inclusion_reasons)

    # 6. Estágio desabilitado exclui oportunidades de estágio
    intern_opp = Opportunity(
        external_id="m7",
        title="Estágio em Desenvolvimento Python",
        description="Atuação em APIs.",
        opportunity_type=OpportunityType.INTERNSHIP.value,
        employment_type=EmploymentType.INTERNSHIP.value,
        work_mode=WorkMode.HYBRID.value,
        city="Campinas",
        country="Brasil",
        eligibility_unknown=False,
        requirements=["Python"],
        technologies=["Python"],
        source_url="https://example.com/intern",
        content_hash="h7",
    )
    eval_intern = evaluate_opportunity_for_user(intern_opp, profile)
    assert eval_intern.eligible is False
    assert any("estágio" in r.lower() for r in eval_intern.exclusion_reasons)


def test_api_opportunities_privacy_immutability_filters_pagination_and_states(
    db_session, make_client
):
    user_a = create_user_account(
        db_session,
        email="user.a@example.com",
        display_name="Usuário A",
        password="StrongPasswordA123!",
        is_admin=True,
    )
    user_b = create_user_account(
        db_session,
        email="user.b@example.com",
        display_name="Usuário B",
        password="StrongPasswordB123!",
        is_admin=False,
    )
    profile_a = get_or_create_profile(db_session, user_a)
    profile_a.country = "Brasil"
    profile_b = get_or_create_profile(db_session, user_b)
    profile_b.country = "Brasil"
    db_session.commit()

    # Sincroniza 3 vagas elegíveis da Remote OK usando transporte mockado (Remotive desabilitada)
    extended_remote_ok = sample_remote_ok_payload() + [
        {
            "id": "109003",
            "position": "Freelance Backend API Engineer",
            "company": "Studio Sul",
            "tags": ["freelance", "python", "fastapi"],
            "location": "Worldwide",
            "description": "<p>Build Python FastAPI services.</p>",
            "url": "https://remoteok.com/remote-jobs/freelance-backend-109003",
            "date": "2026-11-12T12:00:00+00:00",
        },
        {
            "id": "109004",
            "position": "Junior Software Engineer React & Python",
            "company": "Norte Tech",
            "tags": ["junior", "react", "python"],
            "location": "LATAM",
            "description": "<p>React + Python junior engineering position.</p>",
            "url": "https://remoteok.com/remote-jobs/junior-software-109004",
            "date": "2026-11-13T12:00:00+00:00",
        },
    ]
    remotive_calls = {"count": 0}

    def remotive_should_not_run(_):
        remotive_calls["count"] += 1
        return httpx.Response(500)

    sync_sources(
        db_session,
        connector_overrides={
            "remote_ok": RemoteOKConnector(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, json=extended_remote_ok)
                ),
                sleep_fn=lambda _: None,
            ),
            "remotive": RemotiveConnector(
                transport=httpx.MockTransport(remotive_should_not_run),
                sleep_fn=lambda _: None,
            ),
        },
    )
    assert remotive_calls["count"] == 0

    client_a = make_client(("10.10.0.1", 50000))
    client_b = make_client(("10.10.0.2", 50000))

    # Sem autenticação -> 401
    assert client_a.get("/api/v1/opportunities").status_code == 401

    csrf_a = login_and_get_csrf(client_a, "user.a@example.com", "StrongPasswordA123!")
    csrf_b = login_and_get_csrf(client_b, "user.b@example.com", "StrongPasswordB123!")

    # Fontes públicas sem exposição de segredos e com estado correto de habilitação
    sources_resp = client_a.get("/api/v1/opportunities/sources")
    assert sources_resp.status_code == 200
    sources_json = sources_resp.json()
    sources_by_slug = {s["slug"]: s for s in sources_json}
    assert set(sources_by_slug.keys()) == {
        "remote_ok",
        "jobicy",
        "himalayas",
        "github_backend_br",
        "github_frontend_br",
        "remotive",
    }
    assert sources_by_slug["remote_ok"]["enabled"] is True
    assert sources_by_slug["jobicy"]["enabled"] is True
    assert sources_by_slug["himalayas"]["enabled"] is True
    assert sources_by_slug["github_backend_br"]["enabled"] is True
    assert sources_by_slug["github_frontend_br"]["enabled"] is True
    assert sources_by_slug["remotive"]["enabled"] is False

    # Listagem padrão com filtro + paginação limitada
    bad_page_size = client_a.get("/api/v1/opportunities?page_size=200")
    assert bad_page_size.status_code == 422

    list_resp = client_a.get("/api/v1/opportunities?page=1&page_size=2")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["page_size"] == 2
    assert list_data["total"] >= 3
    assert "raw_metadata" not in list_data["items"][0]

    # Global provider record NÃO pode ser editado por usuário
    global_id = list_data["items"][0]["id"]
    patch_global = client_a.patch(
        f"/api/v1/opportunities/{global_id}",
        json={"title": "Título Adulterado"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert patch_global.status_code == 403

    # Salvar/dispensar é isolado por usuário
    save_a = client_a.patch(
        f"/api/v1/opportunities/{global_id}/state",
        json={"is_saved": True},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert save_a.status_code == 200
    assert save_a.json()["is_saved"] is True

    saved_a = client_a.get("/api/v1/opportunities?saved_only=true").json()
    saved_b = client_b.get("/api/v1/opportunities?saved_only=true").json()
    assert saved_a["total"] == 1
    assert saved_b["total"] == 0

    dismiss_a = client_a.patch(
        f"/api/v1/opportunities/{global_id}/state",
        json={"is_dismissed": True},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert dismiss_a.status_code == 200
    assert dismiss_a.json()["is_dismissed"] is True
    assert dismiss_a.json()["is_saved"] is False

    # Oculta para A por padrão, ainda visível para B
    list_a_after_dismiss = client_a.get("/api/v1/opportunities").json()
    list_b_after_dismiss = client_b.get("/api/v1/opportunities").json()
    assert all(item["id"] != global_id for item in list_a_after_dismiss["items"])
    assert any(item["id"] == global_id for item in list_b_after_dismiss["items"])

    # Cadastro manual privado + bloqueio SSRF
    unsafe_manual = client_a.post(
        "/api/v1/opportunities/manual",
        json={
            "title": "Vaga Interna",
            "opportunity_type": "junior",
            "source_url": "http://127.0.0.1:8080/internal",
        },
        headers={"X-CSRF-Token": csrf_a},
    )
    assert unsafe_manual.status_code == 422

    manual_resp = client_a.post(
        "/api/v1/opportunities/manual",
        json={
            "title": "Estágio Engenharia de Dados BR",
            "company_name": "DataBR",
            "opportunity_type": "internship",
            "employment_type": "internship",
            "work_mode": "hybrid",
            "location_text": "São Paulo, SP",
            "country": "Brasil",
            "eligible_countries": ["Brasil"],
            "technologies": ["Python", "SQL"],
            "description": "<p>Estágio com ETL em Python e PostgreSQL.</p>",
            "source_url": "https://carreiras.empresa.example.com/estagio-dados?utm_medium=share",
        },
        headers={"X-CSRF-Token": csrf_a},
    )
    assert manual_resp.status_code == 201, manual_resp.text
    manual_id = manual_resp.json()["id"]
    assert manual_resp.json()["is_manual"] is True
    assert manual_resp.json()["source_url"] == "https://carreiras.empresa.example.com/estagio-dados"

    # Usuário B não enxerga nem altera oportunidade manual de Usuário A
    assert client_b.get(f"/api/v1/opportunities/{manual_id}").status_code == 404
    assert (
        client_b.patch(
            f"/api/v1/opportunities/{manual_id}",
            json={"title": "Hijack"},
            headers={"X-CSRF-Token": csrf_b},
        ).status_code
        == 404
    )

    # Usuário A pode editar sua própria oportunidade manual
    patch_manual_a = client_a.patch(
        f"/api/v1/opportunities/{manual_id}",
        json={"title": "Estágio Engenharia de Dados Python"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert patch_manual_a.status_code == 200
    assert patch_manual_a.json()["title"] == "Estágio Engenharia de Dados Python"


def test_cli_sync_opportunities_dry_run_and_error_handling(
    db_engine, monkeypatch, capsys
):
    from sqlalchemy.orm import sessionmaker

    TestSession = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr("app.cli.SessionLocal", TestSession)

    # Fonte inexistente retorna erro (exit code 1)
    exit_invalid = cli_main(["sync-opportunities", "--source", "fonte_inexistente"])
    assert exit_invalid == 1

    # Mock do RemoteOKConnector para executar via CLI sem internet externa
    class MockRemoteOK(RemoteOKConnector):
        def __init__(self):
            super().__init__(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, json=sample_remote_ok_payload())
                ),
                sleep_fn=lambda _: None,
            )

    monkeypatch.setattr(
        "app.services.opportunities.sync_service.CONNECTOR_CLASSES",
        {"remote_ok": MockRemoteOK, "remotive": MockRemoteOK},
    )

    exit_dry = cli_main(
        ["sync-opportunities", "--source", "remote_ok", "--dry-run"]
    )
    assert exit_dry == 0
    captured = capsys.readouterr()
    assert "fonte=remote_ok" in captured.out
    assert "coletadas=2" in captured.out

    # CLI recusa --source remotive (desabilitada por padrão) com erro controlado
    exit_remotive = cli_main(["sync-opportunities", "--source", "remotive"])
    assert exit_remotive == 1
    captured_err = capsys.readouterr()
    assert "desabilitada" in captured_err.err.lower()


def test_source_compliance_remotive_disabled_and_remote_ok_active(
    db_session, db_engine, make_client, monkeypatch, capsys
):
    from sqlalchemy.orm import sessionmaker
    from app.services.opportunities.sync_service import ensure_default_sources

    # 1 e 2: Remote OK habilitada por padrão; Remotive desabilitada por padrão
    sources = ensure_default_sources(db_session)
    by_slug = {s.slug: s for s in sources}
    assert by_slug["remote_ok"].enabled is True
    assert by_slug["remote_ok"].refresh_interval_seconds == 3600
    assert by_slug["remotive"].enabled is False
    assert RemotiveConnector.definition.enabled_by_default is False
    assert RemoteOKConnector.definition.enabled_by_default is True

    # 6: Se Remotive estava habilitada no banco previamente, ensure_default_sources atualiza para False;
    # Se Remote OK foi desabilitada manualmente pelo operador, ensure_default_sources NÃO a reativa!
    by_slug["remotive"].enabled = True
    by_slug["remote_ok"].enabled = False
    db_session.commit()

    reinitialized = {s.slug: s for s in ensure_default_sources(db_session)}
    assert reinitialized["remotive"].enabled is False
    assert reinitialized["remote_ok"].enabled is False

    # Restaura remote_ok=True manualmente para os testes de sincronização abaixo
    reinitialized["remote_ok"].enabled = True
    db_session.commit()

    remotive_http_calls = {"count": 0}
    remote_ok_http_calls = {"count": 0}

    def remotive_guard(_):
        remotive_http_calls["count"] += 1
        return httpx.Response(503)

    def ok_handler(_):
        remote_ok_http_calls["count"] += 1
        return httpx.Response(200, json=sample_remote_ok_payload())

    overrides = {
        "remote_ok": RemoteOKConnector(
            transport=httpx.MockTransport(ok_handler),
            sleep_fn=lambda _: None,
        ),
        "remotive": RemotiveConnector(
            transport=httpx.MockTransport(remotive_guard),
            sleep_fn=lambda _: None,
        ),
    }

    # 3 e 8: Remotive desabilitada não sofre requisição HTTP; Remote OK sincroniza normalmente
    res_normal = sync_sources(db_session, connector_overrides=overrides)
    assert len(res_normal) == 1
    assert res_normal[0].source_slug == "remote_ok"
    assert res_normal[0].status == SyncRunStatus.SUCCESS.value
    assert res_normal[0].inserted_count == 2
    assert remote_ok_http_calls["count"] == 1
    assert remotive_http_calls["count"] == 0

    # 4: --force NÃO contorna a desabilitação da Remotive (nem executa HTTP contra ela)
    res_force = sync_sources(db_session, force=True, connector_overrides=overrides)
    assert [r.source_slug for r in res_force] == ["remote_ok"]
    assert remotive_http_calls["count"] == 0
    assert remote_ok_http_calls["count"] == 2

    # 5: --source remotive recusa execução sem consultar API (tanto no serviço quanto via CLI)
    with pytest.raises(ValueError, match="(?i)desabilitada"):
        sync_sources(
            db_session,
            source_slug="remotive",
            force=True,
            connector_overrides=overrides,
        )
    assert remotive_http_calls["count"] == 0

    TestSession = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr("app.cli.SessionLocal", TestSession)
    cli_code = cli_main(["sync-opportunities", "--source", "remotive", "--force"])
    assert cli_code == 1
    assert remotive_http_calls["count"] == 0
    capsys.readouterr()

    # 7: API /opportunities/sources reporta estado correto de habilitação
    user = create_user_account(
        db_session,
        email="sources.check@example.com",
        display_name="Source Check",
        password="StrongPassword123!",
        is_admin=False,
    )
    db_session.commit()
    client = make_client(("10.10.0.9", 50000))
    login_and_get_csrf(client, "sources.check@example.com", "StrongPassword123!")
    api_sources = {s["slug"]: s for s in client.get("/api/v1/opportunities/sources").json()}
    assert api_sources["remote_ok"]["enabled"] is True
    assert api_sources["remotive"]["enabled"] is False

    # 9: Mesmo que enabled=True exista no banco para Remotive, ensure_default_sources impõe False
    # e Remote OK sincroniza normalmente; e em cenário controlado de falha HTTP 503 da Remotive,
    # a sincronização da Remote OK não é interrompida.
    remotive_row = db_session.execute(
        select(OpportunitySource).where(OpportunitySource.slug == "remotive")
    ).scalar_one()
    remotive_row.enabled = True
    db_session.commit()

    res_guarded = sync_sources(db_session, force=True, connector_overrides=overrides)
    assert len(res_guarded) == 1
    assert res_guarded[0].source_slug == "remote_ok"
    assert res_guarded[0].status == SyncRunStatus.SUCCESS.value
    assert remotive_http_calls["count"] == 0

    from dataclasses import replace

    enabled_rem_def = replace(RemotiveConnector.definition, enabled_by_default=True)
    monkeypatch.setattr(RemotiveConnector, "definition", enabled_rem_def)
    overrides["remotive"].definition = enabled_rem_def
    remotive_row.enabled = True
    db_session.commit()

    res_fail_isolated = sync_sources(db_session, force=True, connector_overrides=overrides)
    status_map = {r.source_slug: r.status for r in res_fail_isolated}
    assert status_map["remotive"] == SyncRunStatus.FAILED.value
    assert status_map["remote_ok"] == SyncRunStatus.SUCCESS.value
    assert remotive_http_calls["count"] >= 1


def test_phase022_classifier_precision_conflicts_and_contract_separation():
    # Estágios legítimos e variações bilíngues
    for title in (
        "Backend Engineering Intern",
        "Estagiário de Desenvolvimento Python",
        "Estágio em Engenharia de Software",
        "Apprentice Software Developer",
        "Marketing Student Assistant",
        "M&A Praktikum Intern",
    ):
        dec = classify_opportunity(title=title, tags=[], description="")
        assert dec.opportunity_type == OpportunityType.INTERNSHIP.value, title
        assert dec.employment_type == EmploymentType.INTERNSHIP.value, title

    # Falsos positivos de substring "intern"
    for title in (
        "Internal Tools Software Engineer",
        "International Technical Support Engineer",
    ):
        dec = classify_opportunity(title=title, tags=[], description="Manage internal systems.")
        assert dec.opportunity_type == OpportunityType.OTHER.value, title
        assert dec.employment_type == EmploymentType.UNKNOWN.value, title

    # Vagas júnior e entrada explícitas (incluindo acentuação e sinal na descrição)
    for title in (
        "Junior Backend Developer",
        "Jr. Python Developer",
        "Desenvolvedor Java Júnior",
        "Entry Level Software Engineer",
        "Graduate Software Engineer",
        "Trainee Tech / Tecnologia",
    ):
        dec = classify_opportunity(title=title, tags=[], description="")
        assert dec.opportunity_type == OpportunityType.JUNIOR.value, title
        assert dec.employment_type == EmploymentType.UNKNOWN.value, title

    dec_jr_desc = classify_opportunity(
        title="UI Developer",
        tags=["dev", "senior", "react"],
        description="Looking for an exceptional Jr. UI Developer to collaborate closely with senior developers. 1-2 years experience.",
    )
    assert dec_jr_desc.opportunity_type == OpportunityType.JUNIOR.value
    assert dec_jr_desc.employment_type == EmploymentType.UNKNOWN.value

    dec_entry_desc = classify_opportunity(
        title="Travel Support Specialist",
        tags=["travel", "customer support"],
        description="This is an entry-level opportunity within the travel industry.",
    )
    assert dec_entry_desc.opportunity_type == OpportunityType.JUNIOR.value

    # Cargos sênior / liderança / suporte genérico / tags conflitantes
    for title, tags, desc in (
        ("Senior Backend Engineer", ["junior"], "Work with Java microservices."),
        ("Staff Software Engineer", ["intern"], "Lead technical architecture."),
        ("Principal Software Engineer", [], "Design core platform API contracts."),
        ("Engineering Manager", [], "Manage distributed backend squads."),
        ("Tech Lead", ["junior", "senior"], "Mentor junior and mid developers."),
        (
            "Team Lead Account Executive",
            ["junior", "sales"],
            "Als Team Lead führst du unser Team und entwickelst insbesondere unsere Junior AEs weiter.",
        ),
        (
            "Telehealth Endocrinologist Evenings Fridays and or Weekends",
            ["medical", "internship"],
            "Hiring board-eligible Endocrinologists (MD or DO). 1099 Contract: independent contractor arrangement.",
        ),
        ("Technical Support Engineer", [], "L2 troubleshooting and customer escalation."),
        ("Software Engineer", [], "Build distributed systems in Python."),
    ):
        dec = classify_opportunity(title=title, tags=tags, description=desc)
        assert dec.opportunity_type == OpportunityType.OTHER.value, title

    # Separação estrita entre opportunity_type e employment_type
    dec_jr_pj = classify_opportunity(
        title="Desenvolvedor Backend Júnior - PJ",
        tags=[],
        description="Contratação PJ 100% remota.",
    )
    assert dec_jr_pj.opportunity_type == OpportunityType.JUNIOR.value
    assert dec_jr_pj.employment_type == EmploymentType.PJ.value

    dec_other_clt = classify_opportunity(
        title="Desenvolvedor Full Stack Sênior",
        tags=[],
        description="Vaga CLT com benefícios.",
    )
    assert dec_other_clt.opportunity_type == OpportunityType.OTHER.value
    assert dec_other_clt.employment_type == EmploymentType.CLT.value

    dec_fulltime_contractor = classify_opportunity(
        title="Software Engineer",
        tags=["dev", "ai"],
        description="Type: Full-time contractor. Typically 1-5 years of experience. Founder is a senior engineer to learn from.",
    )
    assert dec_fulltime_contractor.opportunity_type == OpportunityType.OTHER.value
    assert dec_fulltime_contractor.employment_type == EmploymentType.PJ.value

    # Freelance legítimo vs falsos positivos de "contract"
    dec_freela = classify_opportunity(
        title="Freelance Python Developer",
        tags=["freelance"],
        description="Projeto fechado de automação.",
    )
    assert dec_freela.opportunity_type == OpportunityType.FREELANCE.value
    assert dec_freela.employment_type == EmploymentType.FREELANCE.value

    dec_mojibake_freela = classify_opportunity(
        title="APAC Python",
        tags=["python", "part time"],
        description="Please\u00c2\u00a0note:\u00c2\u00a0This\u00c2\u00a0is\u00c2\u00a0a\u00c2\u00a0part-time\u00c2\u00a0freelance\u00c2\u00a0position.",
    )
    assert dec_mojibake_freela.opportunity_type == OpportunityType.FREELANCE.value
    assert dec_mojibake_freela.employment_type == EmploymentType.FREELANCE.value

    dec_smart_contract = classify_opportunity(
        title="Smart Contract Auditor",
        tags=["web3"],
        description="Audit Solidity smart contract protocols. 4+ years experience.",
    )
    assert dec_smart_contract.opportunity_type == OpportunityType.OTHER.value
    assert dec_smart_contract.employment_type == EmploymentType.UNKNOWN.value

    dec_contracts_mgr = classify_opportunity(
        title="Contracts Manager Federal",
        tags=["exec"],
        description="Manage federal contracts after award. $100,000 - $120,000 a year.",
    )
    assert dec_contracts_mgr.opportunity_type == OpportunityType.OTHER.value
    assert dec_contracts_mgr.employment_type == EmploymentType.UNKNOWN.value

    dec_fixed_term = classify_opportunity(
        title="Platform and Integration Engineer Security Telemetry",
        tags=["golang"],
        description="Hours: Part-time, 32 hours per weekContract: Fixed-termSalary: EUR 53,000.",
    )
    assert dec_fixed_term.opportunity_type == OpportunityType.OTHER.value
    assert dec_fixed_term.employment_type == EmploymentType.TEMPORARY.value

    # Entradas vazias ou ausentes
    dec_empty = classify_opportunity(title="   ", tags=None, description=None)
    assert dec_empty.opportunity_type == OpportunityType.UNKNOWN.value
    assert dec_empty.employment_type == EmploymentType.UNKNOWN.value


def test_phase022_safe_idempotent_reclassification_and_cli(
    db_engine, db_session, monkeypatch, capsys
):
    from sqlalchemy.orm import sessionmaker

    from app.services.opportunities.sync_service import ensure_default_sources

    sources = {s.slug: s for s in ensure_default_sources(db_session)}
    remote_ok_source = sources["remote_ok"]

    user = create_user_account(
        db_session,
        email="reclassify.check@example.com",
        display_name="Reclassify Check",
        password="StrongPassword123!",
        is_admin=False,
    )
    db_session.flush()

    fixed_first_seen = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    fixed_published = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)

    opp_fp_contract = Opportunity(
        source_id=remote_ok_source.id,
        external_id="rk-fp-1",
        title="Contracts Manager Federal",
        company_name="Gov Co",
        description="Manage federal contracts after award.",
        opportunity_type=OpportunityType.FREELANCE.value,
        employment_type=EmploymentType.FREELANCE.value,
        work_mode=WorkMode.REMOTE.value,
        location_text="USA",
        eligible_countries=["USA"],
        technologies=["exec"],
        source_url="https://remoteok.com/remote-jobs/contracts-manager-1",
        application_url="https://apply.example.com/1",
        first_seen_at=fixed_first_seen,
        last_seen_at=fixed_first_seen,
        published_at=fixed_published,
        salary_min=100000.0,
        content_hash="hash-fp-1",
        raw_metadata={"slug": "contracts-manager-1"},
    )
    opp_fn_jr = Opportunity(
        source_id=remote_ok_source.id,
        external_id="rk-fn-2",
        title="UI Developer",
        company_name="RainFocus",
        description="Search of an exceptional Jr. UI Developer. 1-2 years experience.",
        opportunity_type=OpportunityType.OTHER.value,
        employment_type=EmploymentType.OTHER.value,
        work_mode=WorkMode.REMOTE.value,
        location_text="Worldwide",
        eligible_countries=["Worldwide"],
        technologies=["dev", "senior", "react"],
        source_url="https://remoteok.com/remote-jobs/ui-dev-2",
        first_seen_at=fixed_first_seen,
        last_seen_at=fixed_first_seen,
        content_hash="hash-fn-2",
    )
    opp_manual = Opportunity(
        source_id=None,
        created_by_user_id=user.id,
        external_id=None,
        title="Projeto Freelance Manual Especial",
        company_name="Cliente Privado",
        description="Contrato indefinido manual",
        opportunity_type=OpportunityType.FREELANCE.value,
        employment_type=EmploymentType.OTHER.value,
        work_mode=WorkMode.REMOTE.value,
        source_url="https://manual.example.com/projeto-1",
        first_seen_at=fixed_first_seen,
        last_seen_at=fixed_first_seen,
        content_hash="hash-manual-3",
    )
    db_session.add_all([opp_fp_contract, opp_fn_jr, opp_manual])
    db_session.flush()

    user_state = OpportunityUserState(
        user_id=user.id,
        opportunity_id=opp_fn_jr.id,
        is_saved=True,
        last_viewed_at=fixed_first_seen,
    )
    db_session.add(user_state)
    db_session.commit()

    # 1. Dry-run calcula alterações mas NÃO altera o banco
    dry_report = reclassify_opportunities(db_session, source_slug="remote_ok", dry_run=True)
    assert dry_report.evaluated_count == 2
    assert dry_report.updated_count == 2
    db_session.refresh(opp_fp_contract)
    db_session.refresh(opp_fn_jr)
    assert opp_fp_contract.opportunity_type == OpportunityType.FREELANCE.value
    assert opp_fn_jr.opportunity_type == OpportunityType.OTHER.value

    # 2. Execução real via CLI para remote_ok
    TestSession = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr("app.cli.SessionLocal", TestSession)
    exit_code = cli_main(["reclassify-opportunities", "--source", "remote_ok"])
    assert exit_code == 0
    out_text = capsys.readouterr().out
    assert "atualizadas=2" in out_text

    db_session.expire_all()
    refreshed_fp = db_session.get(Opportunity, opp_fp_contract.id)
    refreshed_jr = db_session.get(Opportunity, opp_fn_jr.id)
    refreshed_manual = db_session.get(Opportunity, opp_manual.id)
    refreshed_state = db_session.execute(
        select(OpportunityUserState).where(OpportunityUserState.opportunity_id == opp_fn_jr.id)
    ).scalar_one()

    assert refreshed_fp.opportunity_type == OpportunityType.OTHER.value
    assert refreshed_fp.employment_type == EmploymentType.UNKNOWN.value
    assert refreshed_fp.professional_area == ProfessionalArea.ADMINISTRATION.value
    assert refreshed_fp.first_seen_at.replace(tzinfo=None) == fixed_first_seen.replace(tzinfo=None)
    assert refreshed_fp.published_at.replace(tzinfo=None) == fixed_published.replace(tzinfo=None)
    assert refreshed_fp.source_url == "https://remoteok.com/remote-jobs/contracts-manager-1"
    assert refreshed_fp.application_url == "https://apply.example.com/1"
    assert refreshed_fp.salary_min == 100000.0
    assert refreshed_fp.raw_metadata == {"slug": "contracts-manager-1"}

    assert refreshed_jr.opportunity_type == OpportunityType.JUNIOR.value
    assert refreshed_jr.employment_type == EmploymentType.UNKNOWN.value
    assert refreshed_jr.professional_area == ProfessionalArea.FRONTEND.value
    assert refreshed_state.is_saved is True
    assert refreshed_state.is_dismissed is False
    assert refreshed_state.last_viewed_at.replace(tzinfo=None) == fixed_first_seen.replace(tzinfo=None)

    # Vaga manual NÃO foi modificada
    assert refreshed_manual.employment_type == EmploymentType.OTHER.value

    # 3. Segunda execução é idempotente
    second_report = reclassify_opportunities(db_session, source_slug="remote_ok", dry_run=False)
    assert second_report.updated_count == 0
    assert second_report.unchanged_count == 2

    # 4. Fonte desabilitada (remotive) é recusada
    bad_code = cli_main(["reclassify-opportunities", "--source", "remotive"])
    assert bad_code == 1
    capsys.readouterr()


def test_phase023_professional_area_taxonomy_and_multi_area_classification():
    # 1. Exemplos obrigatórios da Fase 02.3 (separação estrita senioridade x área x contrato)
    jr_be = classify_opportunity(
        title="Junior Backend Developer",
        tags=["python", "fastapi"],
        description="Build REST APIs with Python and FastAPI.",
    )
    assert jr_be.opportunity_type == OpportunityType.JUNIOR.value
    assert jr_be.professional_area == ProfessionalArea.BACKEND.value
    assert ProfessionalArea.SOFTWARE_DEVELOPMENT.value in jr_be.secondary_areas

    sr_py = classify_opportunity(
        title="Senior Python Engineer",
        tags=["python"],
        description="5+ years building distributed backend services.",
    )
    assert sr_py.opportunity_type == OpportunityType.OTHER.value
    assert sr_py.professional_area == ProfessionalArea.BACKEND.value
    assert ProfessionalArea.SOFTWARE_DEVELOPMENT.value in sr_py.secondary_areas

    ai_eng = classify_opportunity(
        title="AI Engineer",
        tags=["python", "pytorch"],
        description="Develop LLM pipelines and AI applications.",
    )
    assert ai_eng.professional_area == ProfessionalArea.ARTIFICIAL_INTELLIGENCE.value
    assert ProfessionalArea.SOFTWARE_DEVELOPMENT.value in ai_eng.secondary_areas

    data_analyst = classify_opportunity(
        title="Data Analyst",
        tags=["sql", "excel"],
        description="Create dashboards and KPI reports.",
    )
    assert data_analyst.professional_area == ProfessionalArea.DATA.value
    assert ProfessionalArea.SOFTWARE_DEVELOPMENT.value not in data_analyst.secondary_areas

    tech_sup = classify_opportunity(
        title="Technical Support Specialist",
        tags=["python", "sql", "backend"],
        description="Handle L1/L2 support tickets in Zendesk. Basic Python or SQL query troubleshooting.",
    )
    assert tech_sup.professional_area == ProfessionalArea.TECHNICAL_SUPPORT.value
    assert ProfessionalArea.SOFTWARE_DEVELOPMENT.value not in tech_sup.secondary_areas
    assert ProfessionalArea.BACKEND.value not in tech_sup.secondary_areas

    cust_sup = classify_opportunity(
        title="Customer Support Representative",
        tags=["customer support", "dev"],
        description="Assist customers via phone and chat.",
    )
    assert cust_sup.professional_area == ProfessionalArea.CUSTOMER_SUPPORT.value
    assert ProfessionalArea.SOFTWARE_DEVELOPMENT.value not in cust_sup.secondary_areas

    mkt_intern = classify_opportunity(
        title="Marketing Student Assistant",
        tags=["marketing", "dev", "golang"],
        description="Student job supporting B2B marketing campaigns, 15-20 hours/week.",
    )
    assert mkt_intern.opportunity_type == OpportunityType.INTERNSHIP.value
    assert mkt_intern.professional_area == ProfessionalArea.MARKETING_SALES.value
    assert ProfessionalArea.SOFTWARE_DEVELOPMENT.value not in mkt_intern.secondary_areas

    api_dev = classify_opportunity(
        title="API Integration Developer",
        tags=["python", "webhooks"],
        description="Develop REST API integrations and automation workflows.",
    )
    assert api_dev.professional_area == ProfessionalArea.API_INTEGRATIONS.value
    assert ProfessionalArea.SOFTWARE_DEVELOPMENT.value in api_dev.secondary_areas

    devops_eng = classify_opportunity(
        title="DevOps Engineer",
        tags=["aws", "terraform", "kubernetes"],
        description="Maintain Kubernetes clusters and CI/CD pipelines.",
    )
    assert devops_eng.professional_area == ProfessionalArea.DEVOPS_CLOUD.value
    assert ProfessionalArea.BACKEND.value not in devops_eng.secondary_areas

    sw_generic = classify_opportunity(
        title="Software Engineer",
        tags=["golang", "dev"],
        description="Remote software engineering position.",
    )
    assert sw_generic.opportunity_type == OpportunityType.OTHER.value
    assert sw_generic.professional_area == ProfessionalArea.SOFTWARE_DEVELOPMENT.value

    # 2. Vaga Full Stack com múltiplas áreas (Java, Spring Boot, React, PostgreSQL)
    fs_multi = classify_opportunity(
        title="Desenvolvedor Full Stack Júnior",
        tags=["java", "spring boot", "react", "postgresql"],
        description="Desenvolvimento Full Stack com Java, Spring Boot, React, TypeScript e PostgreSQL consumindo APIs REST.",
    )
    assert fs_multi.opportunity_type == OpportunityType.JUNIOR.value
    assert fs_multi.professional_area == ProfessionalArea.FULLSTACK.value
    assert set(fs_multi.secondary_areas) >= {
        ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
        ProfessionalArea.BACKEND.value,
        ProfessionalArea.FRONTEND.value,
        ProfessionalArea.API_INTEGRATIONS.value,
    }

    # 3. Vaga sem área identificável -> unknown
    unk_area = classify_opportunity(
        title="General Open Opportunity #402",
        tags=[],
        description="Confidential opportunity. Details upon request.",
    )
    assert unk_area.professional_area == ProfessionalArea.UNKNOWN.value
    assert unk_area.secondary_areas == ()


def test_phase023_matching_relevance_support_exclusion_and_api_area_filter(
    db_session, make_client
):
    import copy

    user = create_user_account(
        db_session,
        email="phase023.dev@example.com",
        display_name="Dev Fase 02.3",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile = get_or_create_profile(db_session, user)
    profile.country = "Brasil"
    prefs = copy.deepcopy(profile.preferences)
    prefs["internships"]["enabled"] = True
    prefs["internships"]["priority_areas"] = [
        "Desenvolvimento Backend",
        "Engenharia de software",
        "APIs e integrações",
    ]
    prefs["internships"]["excluded_areas"] = ["Suporte técnico", "Help desk", "Atendimento de TI"]
    prefs["junior_developer"]["enabled"] = True
    prefs["junior_developer"]["block_clt"] = True
    prefs["junior_developer"]["priority_areas"] = [
        "Desenvolvimento Backend",
        "Full Stack",
        "Inteligência artificial",
    ]
    prefs["junior_developer"]["excluded_areas"] = ["Suporte técnico", "Help desk"]
    prefs["freelance"]["enabled"] = True
    prefs["freelance"]["scopes"] = ["Brasil", "Exterior (Internacional)"]
    prefs["freelance"]["priority_categories"] = ["APIs e integrações", "Python", "Automação"]
    profile.preferences = prefs
    db_session.commit()

    now = datetime.now(UTC)

    # 1. Travel Support Specialist (junior, mas customer_support -> incompatível com dev!)
    opp_travel_jr = Opportunity(
        external_id="p23-1",
        title="Travel Support Specialist",
        description="This is an entry-level opportunity within the travel industry.",
        opportunity_type=OpportunityType.JUNIOR.value,
        employment_type=EmploymentType.UNKNOWN.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.CUSTOMER_SUPPORT.value,
        secondary_areas=[],
        eligible_countries=["Worldwide"],
        source_url="https://example.com/travel-jr",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h-p23-1",
    )
    eval_travel = evaluate_opportunity_for_user(opp_travel_jr, profile)
    assert eval_travel.eligible is False
    assert eval_travel.area_compatibility == "incompatible"

    # 2. Suporte técnico mencionando Python/Java incidentalmente -> incompatível!
    opp_tech_support = Opportunity(
        external_id="p23-2",
        title="Technical Support Specialist",
        description="L1/L2 Help Desk support. Knowledge of Python and Java is a plus.",
        opportunity_type=OpportunityType.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.TECHNICAL_SUPPORT.value,
        secondary_areas=[],
        technologies=["Python", "Java"],
        eligible_countries=["Worldwide"],
        source_url="https://example.com/tech-support",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h-p23-2",
    )
    eval_sup = evaluate_opportunity_for_user(opp_tech_support, profile)
    assert eval_sup.eligible is False
    assert eval_sup.area_compatibility == "incompatible"
    assert eval_sup.matched_technologies == []

    # 3. Vaga Júnior de Backend com employment_type=unknown e block_clt=true -> elegível!
    opp_jr_dev_unknown_contract = Opportunity(
        external_id="p23-3",
        title="Junior Python Backend Developer",
        description="Build FastAPI microservices and PostgreSQL integrations.",
        opportunity_type=OpportunityType.JUNIOR.value,
        employment_type=EmploymentType.UNKNOWN.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        secondary_areas=[
            ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
            ProfessionalArea.API_INTEGRATIONS.value,
        ],
        technologies=["Python", "FastAPI", "PostgreSQL"],
        eligible_countries=["Worldwide"],
        source_url="https://example.com/jr-backend",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h-p23-3",
    )
    eval_jr_dev = evaluate_opportunity_for_user(opp_jr_dev_unknown_contract, profile)
    assert eval_jr_dev.eligible is True
    assert eval_jr_dev.area_compatibility == "compatible"
    assert any("contrato não informado" in n.lower() for n in eval_jr_dev.uncertainty_notes)

    # 4. Estágio de desenvolvimento vs Estágio de marketing
    opp_intern_dev = Opportunity(
        external_id="p23-4",
        title="Estágio em Engenharia de Software Backend",
        description="Desenvolvimento em Java, Spring Boot e APIs REST.",
        opportunity_type=OpportunityType.INTERNSHIP.value,
        employment_type=EmploymentType.INTERNSHIP.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        secondary_areas=[ProfessionalArea.SOFTWARE_DEVELOPMENT.value],
        technologies=["Java", "Spring Boot"],
        eligible_countries=["Brasil"],
        source_url="https://example.com/intern-dev",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h-p23-4",
    )
    opp_intern_mkt = Opportunity(
        external_id="p23-5",
        title="Marketing Student Assistant",
        description="Student job in B2B marketing.",
        opportunity_type=OpportunityType.INTERNSHIP.value,
        employment_type=EmploymentType.INTERNSHIP.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.MARKETING_SALES.value,
        secondary_areas=[ProfessionalArea.ADMINISTRATION.value],
        eligible_countries=["Worldwide"],
        source_url="https://example.com/intern-mkt",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h-p23-5",
    )
    assert evaluate_opportunity_for_user(opp_intern_dev, profile).eligible is True
    assert evaluate_opportunity_for_user(opp_intern_mkt, profile).eligible is False

    # 5. Freelance de desenvolvimento vs Freelance de saúde/outras áreas
    opp_freela_dev = Opportunity(
        external_id="p23-6",
        title="Freelance Python API Automation Developer",
        description="Independent contractor building FastAPI integrations.",
        opportunity_type=OpportunityType.FREELANCE.value,
        employment_type=EmploymentType.FREELANCE.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.API_INTEGRATIONS.value,
        secondary_areas=[
            ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
            ProfessionalArea.BACKEND.value,
        ],
        technologies=["Python", "FastAPI"],
        eligible_countries=["Worldwide"],
        source_url="https://example.com/freela-dev",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h-p23-6",
    )
    opp_freela_med = Opportunity(
        external_id="p23-7",
        title="Freelance Question Reviewers",
        description="OB-GYN medical exam question review.",
        opportunity_type=OpportunityType.FREELANCE.value,
        employment_type=EmploymentType.FREELANCE.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.HEALTHCARE.value,
        secondary_areas=[],
        eligible_countries=["Worldwide"],
        source_url="https://example.com/freela-med",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h-p23-7",
    )
    assert evaluate_opportunity_for_user(opp_freela_dev, profile).eligible is True
    assert evaluate_opportunity_for_user(opp_freela_med, profile).eligible is False

    # 6. Oportunidade sem área identificada (unknown) -> não recomendada como compatível, mas consultável
    opp_unknown_area = Opportunity(
        external_id="p23-8",
        title="Open Remote Opportunity #99",
        description="Apply with resume.",
        opportunity_type=OpportunityType.JUNIOR.value,
        employment_type=EmploymentType.UNKNOWN.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.UNKNOWN.value,
        secondary_areas=[],
        eligible_countries=["Worldwide"],
        source_url="https://example.com/unk-99",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h-p23-8",
    )
    eval_unk = evaluate_opportunity_for_user(opp_unknown_area, profile)
    assert eval_unk.eligible is False
    assert eval_unk.area_compatibility == "unknown"

    from app.services.opportunities.sync_service import ensure_default_sources

    src = {s.slug: s for s in ensure_default_sources(db_session)}["remote_ok"]
    for o in (
        opp_travel_jr,
        opp_tech_support,
        opp_jr_dev_unknown_contract,
        opp_intern_dev,
        opp_intern_mkt,
        opp_freela_dev,
        opp_freela_med,
        opp_unknown_area,
    ):
        o.source_id = src.id
        db_session.add(o)
    db_session.commit()

    client = make_client(("10.10.0.55", 50000))
    login_and_get_csrf(client, "phase023.dev@example.com", "StrongPassword123!")

    # Aba Júnior padrão retorna apenas a vaga de desenvolvimento compatível
    jr_default = client.get("/api/v1/opportunities?type=junior").json()
    assert [i["title"] for i in jr_default["items"]] == ["Junior Python Backend Developer"]
    assert jr_default["items"][0]["professional_area"] == "backend"
    assert "api_integrations" in jr_default["items"][0]["secondary_areas"]

    # Filtro por área secundária (api_integrations) encontra a vaga Junior Python Backend Developer
    jr_api_area = client.get("/api/v1/opportunities?type=junior&area=api_integrations").json()
    assert [i["title"] for i in jr_api_area["items"]] == ["Junior Python Backend Developer"]

    # Vagas sem área ou de atendimento permanecem consultáveis com include_excluded=true e filtro de área
    jr_unk_query = client.get(
        "/api/v1/opportunities?type=junior&area=unknown&include_excluded=true"
    ).json()
    assert [i["title"] for i in jr_unk_query["items"]] == ["Open Remote Opportunity #99"]

    jr_cust_query = client.get(
        "/api/v1/opportunities?type=junior&area=customer_support&include_excluded=true"
    ).json()
    assert [i["title"] for i in jr_cust_query["items"]] == ["Travel Support Specialist"]


def test_phase024_new_connectors_normalization_pii_redaction_and_cross_source_dedup(
    db_session,
):
    future_epoch = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    expired_epoch = int((datetime.now(UTC) - timedelta(days=2)).timestamp())

    # 1. Jobicy: parsing, deduplicação de clones multi-país no mesmo lote e 429 Retry-After
    jobicy_payload = {
        "jobs": [
            {
                "id": 90101,
                "url": "https://jobicy.com/jobs/90101-junior-python-backend-developer",
                "jobSlug": "90101-junior-python-backend-developer",
                "jobTitle": "Junior Python Backend Engineer",
                "companyName": "Acme Cloud",
                "jobIndustry": ["Software Development", "Python"],
                "jobType": ["Contract"],
                "jobGeo": "Anywhere",
                "jobLevel": "Junior",
                "jobDescription": "<p>Build FastAPI and PostgreSQL microservices.</p>",
                "pubDate": "2026-11-14T10:00:00+00:00",
                "salaryMin": 48000,
                "salaryMax": 62000,
                "salaryCurrency": "USD",
                "salaryPeriod": "annual",
            },
            {
                "id": 90102,
                "url": "https://jobicy.com/jobs/90102-senior-fullstack-uk",
                "jobTitle": "Senior Full Stack Engineer | UK | Remote",
                "companyName": "CloneCorp",
                "jobIndustry": ["Software Development"],
                "jobType": ["Full-Time"],
                "jobGeo": "Germany, Ireland, UK",
                "jobLevel": "Senior",
                "jobDescription": "<p>React and Java Spring Boot.</p>",
                "pubDate": "2026-11-14T11:00:00+00:00",
            },
            {
                "id": 90103,
                "url": "https://jobicy.com/jobs/90103-senior-fullstack-de",
                "jobTitle": "Senior Full Stack Engineer | Germany | Remote",
                "companyName": "CloneCorp",
                "jobIndustry": ["Software Development"],
                "jobType": ["Full-Time"],
                "jobGeo": "Germany, Ireland, UK",
                "jobLevel": "Senior",
                "jobDescription": "<p>React and Java Spring Boot.</p>",
                "pubDate": "2026-11-14T11:00:00+00:00",
            },
        ]
    }
    jobicy_sleeps: list[float] = []
    jobicy_calls = {"count": 0}

    def jobicy_handler(_: httpx.Request) -> httpx.Response:
        jobicy_calls["count"] += 1
        if jobicy_calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json=jobicy_payload)

    jobicy_conn = JobicyConnector(
        transport=httpx.MockTransport(jobicy_handler),
        sleep_fn=lambda s: jobicy_sleeps.append(s),
    )
    jobicy_drafts = jobicy_conn.collect()
    assert jobicy_calls["count"] == 2
    assert jobicy_sleeps == [2.0]
    assert len(jobicy_drafts) == 3
    assert jobicy_conn.last_batch.received_count == 3
    assert jobicy_conn.last_batch.rejected_count == 0
    assert jobicy_drafts[0].opportunity_type == OpportunityType.JUNIOR.value
    assert jobicy_drafts[0].employment_type == EmploymentType.PJ.value
    assert jobicy_drafts[0].professional_area == ProfessionalArea.BACKEND.value
    assert jobicy_drafts[0].eligible_countries == ["Worldwide"]

    # 2. Himalayas: preserva applicationLink, descarta vaga expirada e mapeia locationRestrictions=[]
    himalayas_payload = {
        "jobs": [
            {
                "guid": "https://himalayas.app/companies/acme/jobs/ai-integration-intern",
                "title": "AI & API Integration Intern",
                "companyName": "BetaAI",
                "employmentType": "Intern",
                "seniority": ["Entry-level"],
                "locationRestrictions": [],
                "categories": ["Artificial-Intelligence", "Python", "FastAPI"],
                "description": "<p>Paid software engineering internship building LLM API integrations.</p>",
                "pubDate": 1794600000,
                "expiryDate": future_epoch,
                "applicationLink": "https://jobs.example.com/apply/beta-ai-intern",
            },
            {
                "guid": "https://himalayas.app/companies/old/jobs/expired-role",
                "title": "Expired Software Developer",
                "companyName": "OldCo",
                "employmentType": "Full Time",
                "seniority": ["Junior"],
                "locationRestrictions": ["Brazil"],
                "categories": ["Python"],
                "description": "<p>Expired role.</p>",
                "pubDate": 1700000000,
                "expiryDate": expired_epoch,
                "applicationLink": "https://jobs.example.com/apply/expired",
            },
        ]
    }
    himalayas_conn = HimalayasConnector(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=himalayas_payload)),
        sleep_fn=lambda _: None,
    )
    him_drafts = himalayas_conn.collect()
    assert len(him_drafts) == 1
    assert him_drafts[0].opportunity_type == OpportunityType.INTERNSHIP.value
    assert him_drafts[0].employment_type == EmploymentType.INTERNSHIP.value
    assert him_drafts[0].application_url == "https://jobs.example.com/apply/beta-ai-intern"
    assert him_drafts[0].eligible_countries == ["Worldwide"]

    # 3. GitHub Vagas BR: ignora PRs e Stale, redige PII (e-mail/telefone) e extrai Júnior/PJ/CLT
    gh_issues_payload = [
        {
            "number": 12493,
            "state": "open",
            "title": "[Remoto] Desenvolvedor(a) Back-end Júnior - Python & FastAPI - MKdigital",
            "html_url": "https://github.com/backend-br/vagas/issues/12493",
            "created_at": "2026-11-15T10:00:00Z",
            "labels": [
                {"name": "PJ"},
                {"name": "Júnior"},
                {"name": "Python"},
                {"name": "FastAPI"},
                {"name": "PostgreSQL"},
                {"name": "Remoto"},
                {"name": "verificada"},
            ],
            "body": "Envie currículo para recrutador.privado@empresa.com.br ou WhatsApp (11) 98765-4321. Stack Python, FastAPI e PostgreSQL.",
        },
        {
            "number": 12499,
            "state": "open",
            "title": "PR indevido no endpoint de issues",
            "html_url": "https://github.com/backend-br/vagas/pull/12499",
            "pull_request": {"url": "https://api.github.com/repos/backend-br/vagas/pulls/12499"},
            "labels": [],
            "body": "Não deve ser importado.",
        },
        {
            "number": 12000,
            "state": "open",
            "title": "[Remoto] Vaga Antiga Stale",
            "html_url": "https://github.com/backend-br/vagas/issues/12000",
            "labels": [{"name": "Stale"}],
            "body": "Vaga antiga.",
        },
    ]
    gh_back_conn = GitHubBackendBRConnector(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=gh_issues_payload)),
        sleep_fn=lambda _: None,
    )
    gh_drafts = gh_back_conn.collect()
    assert len(gh_drafts) == 1
    gh_jr = gh_drafts[0]
    assert gh_jr.opportunity_type == OpportunityType.JUNIOR.value
    assert gh_jr.employment_type == EmploymentType.PJ.value
    assert gh_jr.professional_area == ProfessionalArea.BACKEND.value
    assert gh_jr.country == "Brasil"
    assert "recrutador.privado@empresa.com.br" not in (gh_jr.description or "")
    assert "98765-4321" not in (gh_jr.description or "")
    assert "[e-mail na issue original]" in (gh_jr.description or "")
    assert "verificada" not in gh_jr.technologies
    assert "FastAPI" in gh_jr.technologies
    assert redact_contact_pii("Contato: Fulano@teste.org / +55 21 99888-7766") == (
        "Contato: [e-mail na issue original] / [contato na issue original]"
    )

    # 4. Deduplicação cross-source + isolamento de falha de uma fonte durante sync_sources
    ok_conn = RemoteOKConnector(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=sample_remote_ok_payload())
        ),
        sleep_fn=lambda _: None,
    )
    failing_fe_conn = GitHubFrontendBRConnector(
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
        max_retries=0,
        sleep_fn=lambda _: None,
    )
    summaries = sync_sources(
        db_session,
        force=True,
        connector_overrides={
            "remote_ok": ok_conn,
            "jobicy": jobicy_conn,
            "himalayas": himalayas_conn,
            "github_backend_br": gh_back_conn,
            "github_frontend_br": failing_fe_conn,
        },
    )
    by_slug = {s.source_slug: s for s in summaries}
    # Por ordem alfabética de slug, jobicy executa antes de remote_ok:
    # jobicy recebe 3 válidas -> insere 2 vagas únicas e vincula 1 clone multi-país (intra_source_duplicate_count=1);
    # remote_ok recebe 2 válidas -> insere 1 ("Backend Engineering Intern") e vincula 1 cross-source contra jobicy!
    assert by_slug["jobicy"].status == SyncRunStatus.SUCCESS.value
    assert by_slug["jobicy"].received_count == 3
    assert by_slug["jobicy"].valid_count == 3
    assert by_slug["jobicy"].inserted_count == 2
    assert by_slug["jobicy"].intra_source_duplicate_count == 1
    assert by_slug["remote_ok"].status == SyncRunStatus.SUCCESS.value
    assert by_slug["remote_ok"].inserted_count == 1
    assert by_slug["remote_ok"].cross_source_duplicate_count == 1
    assert by_slug["remote_ok"].updated_count == 0
    assert by_slug["himalayas"].received_count == 2
    assert by_slug["himalayas"].valid_count == 1
    assert by_slug["himalayas"].rejected_count == 1
    assert by_slug["himalayas"].inserted_count == 1
    assert by_slug["github_backend_br"].received_count == 3
    assert by_slug["github_backend_br"].valid_count == 1
    assert by_slug["github_backend_br"].rejected_count == 2
    assert by_slug["github_backend_br"].inserted_count == 1
    assert by_slug["github_frontend_br"].status == SyncRunStatus.FAILED.value

    deduped_acme = db_session.execute(
        select(Opportunity).where(Opportunity.external_id == "90101")
    ).scalar_one()
    # Preserva URL e atribuição originais da primeira fonte que inseriu (Jobicy) e registra vínculo completo da Remote OK
    assert deduped_acme.source_url == "https://jobicy.com/jobs/90101-junior-python-backend-developer"
    assert "remote_ok" in deduped_acme.raw_metadata.get("also_seen_in_sources", [])
    acme_links = db_session.execute(
        select(OpportunitySourceLink).where(
            OpportunitySourceLink.opportunity_id == deduped_acme.id
        )
    ).scalars().all()
    assert len(acme_links) == 2
    by_ext = {lnk.external_id: lnk for lnk in acme_links}
    assert by_ext["90101"].is_primary is True
    assert by_ext["109001"].is_primary is False
    assert by_ext["109001"].source_url == "https://remoteok.com/remote-jobs/junior-python-backend-109001"
    assert by_ext["109001"].application_url == "https://jobs.example.com/apply/109001"


def test_phase025_traceability_dedup_precision_lifecycle_and_observability(
    db_session, make_client
):
    now = datetime.now(UTC)
    future_epoch = int((now + timedelta(days=20)).timestamp())
    past_epoch = int((now - timedelta(days=1)).timestamp())

    # 1. Precisão de deduplicação: mesmo título e empresa, mas vagas diferentes por senioridade,
    # modalidade, cidade ou país/descrição NÃO podem sofrer merge falso-positivo;
    # enquanto clones multi-país reais da Jobicy devem unir países elegíveis e preservar ambos os links.
    jobicy_batch = {
        "jobs": [
            {
                "id": 7001,
                "url": "https://jobicy.com/jobs/7001-fullstack-uk",
                "jobTitle": "Full Stack Python Engineer | UK | Remote",
                "companyName": "GeoMerge Labs",
                "jobIndustry": ["Python", "React"],
                "jobType": ["Contract"],
                "jobGeo": "UK",
                "jobLevel": "Junior",
                "jobDescription": "<p>Build distributed Python and React services for global telemetry platform with FastAPI and PostgreSQL.</p>",
                "pubDate": "2026-11-15T10:00:00+00:00",
            },
            {
                "id": 7002,
                "url": "https://jobicy.com/jobs/7002-fullstack-br",
                "jobTitle": "Full Stack Python Engineer | Brazil | Remote",
                "companyName": "GeoMerge Labs",
                "jobIndustry": ["Python", "React"],
                "jobType": ["Contract"],
                "jobGeo": "Brazil",
                "jobLevel": "Junior",
                "jobDescription": "<p>Build distributed Python and React services for global telemetry platform with FastAPI and PostgreSQL.</p>",
                "pubDate": "2026-11-15T10:05:00+00:00",
            },
            # Mesma empresa e mesmo título base de outra vaga, mas senioridade Senior e descrição distinta -> NÃO deve unificar com 7001!
            {
                "id": 7003,
                "url": "https://jobicy.com/jobs/7003-fullstack-senior",
                "jobTitle": "Full Stack Python Engineer",
                "companyName": "GeoMerge Labs",
                "jobIndustry": ["Python", "Kubernetes"],
                "jobType": ["Full-Time"],
                "jobGeo": "USA",
                "jobLevel": "Senior",
                "jobDescription": "<p>Architect enterprise billing pipelines and lead 8 engineers in US timezone.</p>",
                "pubDate": "2026-11-15T11:00:00+00:00",
            },
        ]
    }

    # Himalayas: duas empresas diferentes com mesmo slug final "/jobs/software-developer"
    # + uma vaga ativa que irá expirar na 2ª sincronização
    him_state = {"expire_first": False}

    def him_handler(_: httpx.Request) -> httpx.Response:
        exp_val = past_epoch if him_state["expire_first"] else future_epoch
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "guid": "https://himalayas.app/companies/alpha-corp/jobs/software-developer",
                        "title": "Junior Software Developer",
                        "companyName": "Alpha Corp",
                        "employmentType": "Contractor",
                        "seniority": ["Entry-level"],
                        "locationRestrictions": ["Brazil", "United States"],
                        "categories": ["Software-Engineering", "Python"],
                        "description": "<p>Develop backend microservices in Python for Alpha Corp.</p>",
                        "pubDate": 1794600000,
                        "expiryDate": exp_val,
                        "applicationLink": "https://himalayas.app/companies/alpha-corp/jobs/software-developer?utm_source=api",
                    },
                    {
                        "guid": "https://himalayas.app/companies/omega-inc/jobs/software-developer",
                        "title": "Junior Software Developer",
                        "companyName": "Omega Inc",
                        "employmentType": "Contractor",
                        "seniority": ["Entry-level"],
                        "locationRestrictions": ["Brazil"],
                        "categories": ["Software-Engineering", "Python"],
                        "description": "<p>Develop backend APIs in Python for Omega Inc.</p>",
                        "pubDate": 1794600500,
                        "expiryDate": future_epoch,
                        "applicationLink": "https://himalayas.app/companies/omega-inc/jobs/software-developer?utm_source=api",
                    },
                ]
            },
        )

    # GitHub Backend BR e Frontend BR:
    # - Vaga compartilhada entre Backend BR (#501) e Frontend BR (#801)
    # - Duas vagas presenciais na mesma empresa ("Banco Zeta") com mesmo título base mas cidades diferentes (SP vs Curitiba) -> NÃO podem unificar!
    # - Vaga #502 no Backend BR que será fechada via revalidação individual de issue na 2ª sincronização
    gh_state = {"close_502": False, "close_801_in_feed": False}

    def gh_backend_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str.endswith("/issues/502"):
            return httpx.Response(
                200,
                json={
                    "number": 502,
                    "state": "closed" if gh_state["close_502"] else "open",
                    "labels": [{"name": "PJ"}, {"name": "Júnior"}],
                },
            )
        issues = [
            {
                "number": 501,
                "state": "open",
                "title": "[Remoto] Desenvolvedor Full Stack Júnior Python & React na DualStackBR",
                "html_url": "https://github.com/backend-br/vagas/issues/501",
                "created_at": "2026-11-15T10:00:00Z",
                "labels": [{"name": "PJ"}, {"name": "Júnior"}, {"name": "Python"}, {"name": "Remoto"}],
                "body": "Vaga Full Stack Júnior atuando com FastAPI, PostgreSQL e React em arquitetura SaaS.",
            },
            {
                "number": 503,
                "state": "open",
                "title": "[São Paulo/SP] Desenvolvedor Back-end Júnior na Banco Zeta",
                "html_url": "https://github.com/backend-br/vagas/issues/503",
                "created_at": "2026-11-15T10:10:00Z",
                "labels": [{"name": "PJ"}, {"name": "Júnior"}, {"name": "Presencial"}, {"name": "Python"}],
                "body": "Atuação presencial no escritório de São Paulo com Python e SQL.",
            },
            {
                "number": 504,
                "state": "open",
                "title": "[Curitiba/PR] Desenvolvedor Back-end Júnior na Banco Zeta",
                "html_url": "https://github.com/backend-br/vagas/issues/504",
                "created_at": "2026-11-15T10:15:00Z",
                "labels": [{"name": "PJ"}, {"name": "Júnior"}, {"name": "Presencial"}, {"name": "Python"}],
                "body": "Atuação presencial no escritório de Curitiba com Python e SQL.",
            },
        ]
        if not gh_state["close_502"]:
            issues.append(
                {
                    "number": 502,
                    "state": "open",
                    "title": "[Remoto] Engenheiro de Dados Júnior Python na DataPulseBR",
                    "html_url": "https://github.com/backend-br/vagas/issues/502",
                    "created_at": "2026-11-15T10:05:00Z",
                    "labels": [{"name": "PJ"}, {"name": "Júnior"}, {"name": "Python"}, {"name": "Remoto"}],
                    "body": "Pipeline de dados com Python e SQL.",
                }
            )
        return httpx.Response(200, json=issues)

    def gh_frontend_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "number": 801,
                    "state": "closed" if gh_state["close_801_in_feed"] else "open",
                    "title": "[Remoto] Desenvolvedor Full Stack Júnior Python & React na DualStackBR",
                    "html_url": "https://github.com/frontendbr/vagas/issues/801",
                    "created_at": "2026-11-15T10:02:00Z",
                    "labels": [{"name": "PJ"}, {"name": "Júnior"}, {"name": "React"}, {"name": "Remoto"}],
                    "body": "Vaga Full Stack Júnior atuando com FastAPI, PostgreSQL e React em arquitetura SaaS.",
                }
            ],
        )

    overrides = {
        "jobicy": JobicyConnector(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=jobicy_batch)),
            sleep_fn=lambda _: None,
        ),
        "himalayas": HimalayasConnector(
            transport=httpx.MockTransport(him_handler),
            sleep_fn=lambda _: None,
        ),
        "github_backend_br": GitHubBackendBRConnector(
            transport=httpx.MockTransport(gh_backend_handler),
            sleep_fn=lambda _: None,
        ),
        "github_frontend_br": GitHubFrontendBRConnector(
            transport=httpx.MockTransport(gh_frontend_handler),
            sleep_fn=lambda _: None,
        ),
    }

    # 1ª Sincronização
    runs1 = {
        r.source_slug: r
        for r in sync_sources(db_session, force=True, connector_overrides=overrides)
    }

    # Invariante matemática de métricas por fonte
    for r in runs1.values():
        assert r.received_count == r.valid_count + r.rejected_count
        assert r.valid_count == (
            r.inserted_count
            + r.updated_count
            + r.intra_source_duplicate_count
            + r.cross_source_duplicate_count
        )

    assert runs1["jobicy"].received_count == 3
    assert runs1["jobicy"].inserted_count == 2  # 7001 e 7003 (7002 é clone multi-país de 7001)
    assert runs1["jobicy"].intra_source_duplicate_count == 1
    assert runs1["himalayas"].inserted_count == 2  # Alpha Corp e Omega Inc NÃO colidem!
    assert runs1["github_backend_br"].inserted_count == 4  # 501, 502, 503 (SP) e 504 (Curitiba)
    assert runs1["github_frontend_br"].inserted_count == 0
    assert runs1["github_frontend_br"].cross_source_duplicate_count == 1  # 801 unificada com 501

    # Verifica que o clone multi-país 7002 uniu Brasil + UK e preservou ambos os links
    geomerge_jr = db_session.execute(
        select(Opportunity).where(Opportunity.external_id == "7001")
    ).scalar_one()
    assert set(geomerge_jr.eligible_countries) == {"UK", "Brazil"}
    geomerge_links = db_session.execute(
        select(OpportunitySourceLink).where(
            OpportunitySourceLink.opportunity_id == geomerge_jr.id
        )
    ).scalars().all()
    assert len(geomerge_links) == 2
    assert {l.external_id for l in geomerge_links} == {"7001", "7002"}

    # Verifica que a vaga DualStackBR preservou os links de ambos os repositórios GitHub
    dual_opp = db_session.execute(
        select(Opportunity).where(Opportunity.external_id == "gh-backend-br-501")
    ).scalar_one()
    dual_links = db_session.execute(
        select(OpportunitySourceLink).where(
            OpportunitySourceLink.opportunity_id == dual_opp.id
        )
    ).scalars().all()
    assert len(dual_links) == 2
    assert {l.source_url for l in dual_links} == {
        "https://github.com/backend-br/vagas/issues/501",
        "https://github.com/frontendbr/vagas/issues/801",
    }

    # Cria usuário em Curitiba/Brasil e salva a vaga da Alpha Corp antes de ela expirar
    user = create_user_account(
        db_session,
        email="phase025.user@example.com",
        display_name="Phase 025 User",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile = get_or_create_profile(db_session, user)
    profile.city = "Curitiba"
    profile.state = "PR"
    profile.country = "Brasil"
    db_session.commit()

    # Elegibilidade geográfica: GeoMerge Labs (UK + Brazil) é elegível para o candidato brasileiro!
    assert evaluate_opportunity_for_user(geomerge_jr, profile).eligible is True
    # Banco Zeta Curitiba (504) é elegível, enquanto Banco Zeta São Paulo (503) é bloqueada por cidade!
    zeta_sp = db_session.execute(
        select(Opportunity).where(Opportunity.external_id == "gh-backend-br-503")
    ).scalar_one()
    zeta_cwb = db_session.execute(
        select(Opportunity).where(Opportunity.external_id == "gh-backend-br-504")
    ).scalar_one()
    assert evaluate_opportunity_for_user(zeta_sp, profile).eligible is False
    assert evaluate_opportunity_for_user(zeta_cwb, profile).eligible is True

    alpha_opp = db_session.execute(
        select(Opportunity).where(
            Opportunity.external_id == "alpha-corp/jobs/software-developer"
        )
    ).scalar_one()
    assert alpha_opp.application_url == (
        "https://himalayas.app/companies/alpha-corp/jobs/software-developer?utm_source=api"
    )
    db_session.add(
        OpportunityUserState(
            user_id=user.id,
            opportunity_id=alpha_opp.id,
            is_saved=True,
            is_dismissed=False,
        )
    )
    db_session.commit()

    # 2ª Sincronização:
    # - Alpha Corp expira na Himalayas (expiryDate < now)
    # - Issue #502 some do feed aberto do GitHub Backend BR e é revalidada como closed via endpoint individual
    # - Issue #801 fecha no GitHub Frontend BR, mas a vaga DualStackBR continua aberta porque #501 segue aberta no Backend BR!
    him_state["expire_first"] = True
    gh_state["close_502"] = True
    gh_state["close_801_in_feed"] = True

    runs2 = {
        r.source_slug: r
        for r in sync_sources(db_session, force=True, connector_overrides=overrides)
    }
    assert runs2["jobicy"].inserted_count == 0
    assert runs2["jobicy"].updated_count == 2
    assert runs2["jobicy"].intra_source_duplicate_count == 1

    db_session.expire_all()
    alpha_refreshed = db_session.get(Opportunity, alpha_opp.id)
    assert alpha_refreshed.source_status == ExternalSourceStatus.EXPIRED.value
    # Estado salvo pelo usuário é integralmente preservado mesmo após expiração
    saved_state = db_session.execute(
        select(OpportunityUserState).where(
            OpportunityUserState.user_id == user.id,
            OpportunityUserState.opportunity_id == alpha_opp.id,
        )
    ).scalar_one()
    assert saved_state.is_saved is True
    # Vaga expirada não é mais elegível para recomendação ativa
    alpha_eval = evaluate_opportunity_for_user(alpha_refreshed, profile)
    assert alpha_eval.eligible is False
    assert any("expirada" in r.lower() for r in alpha_eval.exclusion_reasons)

    # Issue #502 revalidada via check_publication_status passou para CLOSED
    opp_502 = db_session.execute(
        select(Opportunity).where(Opportunity.external_id == "gh-backend-br-502")
    ).scalar_one()
    assert opp_502.source_status == ExternalSourceStatus.CLOSED.value

    # DualStackBR (#501 aberta + #801 fechada) permanece ACTIVE na oportunidade consolidada
    dual_refreshed = db_session.get(Opportunity, dual_opp.id)
    assert dual_refreshed.source_status == ExternalSourceStatus.ACTIVE.value
    dual_links_refreshed = {
        l.external_id: l.source_status for l in dual_refreshed.source_links
    }
    assert dual_links_refreshed["gh-backend-br-501"] == ExternalSourceStatus.ACTIVE.value
    assert dual_links_refreshed["gh-frontend-br-801"] == ExternalSourceStatus.CLOSED.value

    # Validação via API HTTP: source_links, filtro por fonte secundária e observabilidade
    client = make_client(("10.10.0.88", 50000))
    login_and_get_csrf(client, "phase025.user@example.com", "StrongPassword123!")

    fe_filtered = client.get("/api/v1/opportunities?type=junior&source=github_frontend_br").json()
    assert fe_filtered["total"] == 1
    fe_item = fe_filtered["items"][0]
    assert fe_item["external_id"] == "gh-backend-br-501"
    assert len(fe_item["source_links"]) == 2
    assert fe_item["last_status_check_at"] is not None

    sources_resp = {
        s["slug"]: s for s in client.get("/api/v1/opportunities/sources").json()
    }
    assert sources_resp["github_backend_br"]["unique_opportunities_count"] == 4
    assert sources_resp["github_backend_br"]["open_opportunities_count"] == 3
    assert sources_resp["github_backend_br"]["closed_or_expired_count"] == 1


def test_phase026_seniority_experience_technical_matching_and_reclassification(
    db_session, make_client
):
    from datetime import date
    import copy

    # 1. Classificação independente de senioridade, contrato e experiência
    # Estágio sem experiência
    intern_no_exp = classify_opportunity(
        title="Estagiário de Backend Python",
        tags=["python", "intern"],
        description="Vaga de estágio sem experiência prévia exigida. Aprender APIs REST com a equipe.",
    )
    assert intern_no_exp.opportunity_type == OpportunityType.INTERNSHIP.value
    assert intern_no_exp.seniority_level == SeniorityLevel.INTERNSHIP.value
    assert intern_no_exp.employment_type == EmploymentType.INTERNSHIP.value
    assert (
        intern_no_exp.experience_requirement_mode
        == ExperienceRequirementMode.NONE_REQUIRED.value
    )
    assert intern_no_exp.experience_min_years == 0

    # Desenvolvedor júnior PJ
    jr_pj = classify_opportunity(
        title="Desenvolvedor Java Júnior PJ",
        tags=["java", "spring boot", "pj"],
        description="Requisitos obrigatórios: experiência com Java e Spring Boot.",
    )
    assert jr_pj.opportunity_type == OpportunityType.JUNIOR.value
    assert jr_pj.seniority_level == SeniorityLevel.JUNIOR.value
    assert jr_pj.employment_type == EmploymentType.PJ.value
    assert jr_pj.required_technologies == ("Java", "Spring Boot")

    # Desenvolvedor pleno
    pleno_dec = classify_opportunity(
        title="Desenvolvedor Backend Pleno",
        tags=["python"],
        description="Requisitos: 3+ years of experience with Python.",
    )
    assert pleno_dec.opportunity_type == OpportunityType.OTHER.value
    assert pleno_dec.seniority_level == SeniorityLevel.MID_LEVEL.value
    assert pleno_dec.experience_requirement_mode == ExperienceRequirementMode.REQUIRED.value
    assert pleno_dec.experience_min_years == 3

    # Desenvolvedor sênior / Staff / Principal
    senior_dec = classify_opportunity(
        title="Desenvolvedor Backend Sênior",
        description="Atuação em microsserviços.",
    )
    assert senior_dec.seniority_level == SeniorityLevel.SENIOR.value
    # Não inventa anos de experiência apenas pelo título "Sênior"!
    assert (
        senior_dec.experience_requirement_mode
        == ExperienceRequirementMode.NOT_SPECIFIED.value
    )
    assert senior_dec.experience_min_years is None

    staff_dec = classify_opportunity(title="Staff Engineer - Distributed Systems")
    assert staff_dec.seniority_level == SeniorityLevel.STAFF_PRINCIPAL.value

    principal_dec = classify_opportunity(title="Principal Engineer - Backend Core")
    assert principal_dec.seniority_level == SeniorityLevel.STAFF_PRINCIPAL.value

    # Freelance Júnior vs Freelance Sênior (separação entre frente freelance e nível profissional!)
    freela_jr = classify_opportunity(
        title="Freelance Junior Python Developer",
        description="Freelance remote project with FastAPI. No experience required.",
    )
    assert freela_jr.opportunity_type == OpportunityType.FREELANCE.value
    assert freela_jr.employment_type == EmploymentType.FREELANCE.value
    assert freela_jr.seniority_level == SeniorityLevel.JUNIOR.value
    assert freela_jr.experience_min_years == 0

    freela_sr = classify_opportunity(
        title="Desenvolvedor Sênior Freelance Backend",
        description="Independent contractor role with 5+ years of experience in Go.",
    )
    assert freela_sr.opportunity_type == OpportunityType.FREELANCE.value
    assert freela_sr.employment_type == EmploymentType.FREELANCE.value
    assert freela_sr.seniority_level == SeniorityLevel.SENIOR.value
    assert freela_sr.experience_min_years == 5

    # Vaga sem senioridade NÃO é classificada automaticamente como Sênior
    no_sen = classify_opportunity(
        title="Software Engineer",
        tags=["java", "python", "docker"],
        description="Join our product engineering team building web platforms.",
    )
    assert no_sen.opportunity_type == OpportunityType.OTHER.value
    assert no_sen.seniority_level == SeniorityLevel.UNKNOWN.value
    assert (
        no_sen.experience_requirement_mode
        == ExperienceRequirementMode.NOT_SPECIFIED.value
    )
    # Tags soltas ("java", "python", "docker") NUNCA viram requisitos obrigatórios!
    assert no_sen.required_technologies == ()

    # Experiência obrigatória vs experiência desejável (sem bloquear desejável!)
    exp_pref = classify_experience_requirements(
        title="Backend Developer",
        description=(
            "Responsibilities:\nBuild APIs.\n"
            "Preferred qualifications:\nNice to have: 3+ years of experience with Kubernetes and AWS."
        ),
    )
    assert exp_pref.mode == ExperienceRequirementMode.PREFERRED.value
    assert exp_pref.min_years is None
    assert exp_pref.preferred_years == 3
    assert exp_pref.mandatory_technologies == ()
    assert set(exp_pref.desirable_technologies) >= {"Kubernetes", "AWS"}

    # Menção meramente incidental de tecnologia / colegas não cria requisito obrigatório nem área tech
    support_incidental = classify_opportunity(
        title="Technical Support Analyst",
        tags=["java", "python"],
        description="Help desk N1/N2. Collaborate closely with senior Kubernetes engineers.",
    )
    assert support_incidental.professional_area == ProfessionalArea.TECHNICAL_SUPPORT.value
    assert support_incidental.required_technologies == ()

    # 2. Matching completo com habilidades (incluindo Java), experiência, senioridade e filtros HTTP
    user = create_user_account(
        db_session,
        email="phase026.dev@example.com",
        display_name="Phase 026 Dev",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile = get_or_create_profile(db_session, user)
    profile.country = "Brasil"
    profile.city = "Curitiba"
    profile.state = "PR"
    profile.professional_title = "Desenvolvedor Backend Júnior (Java / Spring Boot)"
    prefs = copy.deepcopy(profile.preferences)
    prefs["internships"]["enabled"] = True
    prefs["internships"]["priority_areas"] = ["Desenvolvimento Backend", "APIs e integrações"]
    prefs["junior_developer"]["enabled"] = True
    prefs["junior_developer"]["block_clt"] = True
    prefs["junior_developer"]["accepted_contract_types"] = ["PJ", "Estágio", "Contrato Freelance"]
    prefs["junior_developer"]["priority_areas"] = ["Desenvolvimento Backend", "Full Stack", "Java", "Python"]
    prefs["freelance"]["enabled"] = True
    prefs["freelance"]["scopes"] = ["Brasil", "Exterior (Internacional)"]
    prefs["freelance"]["priority_categories"] = ["APIs", "Python"]
    profile.preferences = prefs

    # Candidato com skill Java (17/21) + Spring Boot + ~1.8 ano de atuação prática
    sk_java = Skill(
        user_id=user.id,
        name="Java (17/21)",
        category="Linguagens",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
    )
    sk_spring = Skill(
        user_id=user.id,
        name="Spring Boot",
        category="Frameworks",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
    )
    sk_python = Skill(
        user_id=user.id,
        name="Python",
        category="Linguagens",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
    )
    exp_rec = WorkExperience(
        user_id=user.id,
        company="Empresa Local",
        role="Desenvolvedor Backend Júnior",
        description="Integração de APIs REST com Java e Spring Boot.",
        start_date=date(2025, 1, 1),
        is_current=True,
        experience_type=ExperienceType.PJ.value,
        technologies=["Java", "Spring Boot"],
        eligible_as_target_role=True,
    )
    db_session.add_all([sk_java, sk_spring, sk_python, exp_rec])
    db_session.commit()

    from app.services.opportunities.sync_service import ensure_default_sources

    src = {s.slug: s for s in ensure_default_sources(db_session)}["github_backend_br"]
    now = datetime.now(UTC)

    # Conjunto representativo das 12 situações da Fase 02.6
    opp_intern = Opportunity(
        source_id=src.id,
        external_id="p26-intern",
        title="Estágio Desenvolvimento Backend Python",
        description="Sem experiência prévia exigida.",
        opportunity_type=OpportunityType.INTERNSHIP.value,
        seniority_level=SeniorityLevel.INTERNSHIP.value,
        experience_requirement_mode=ExperienceRequirementMode.NONE_REQUIRED.value,
        experience_min_years=0,
        experience_summary="Sem exigência de experiência prévia",
        employment_type=EmploymentType.INTERNSHIP.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        secondary_areas=[ProfessionalArea.SOFTWARE_DEVELOPMENT.value],
        eligible_countries=["Brasil"],
        technologies=["Python"],
        source_url="https://example.com/p26-intern",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-1",
    )
    opp_java_jr = Opportunity(
        source_id=src.id,
        external_id="p26-java-jr",
        title="Desenvolvedor Java Júnior PJ",
        description="Requisitos obrigatórios: 1+ year of experience building REST APIs with Java and Spring Boot.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        experience_requirement_mode=ExperienceRequirementMode.REQUIRED.value,
        experience_min_years=1,
        experience_summary="Obrigatória: 1+ anos de experiência",
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        secondary_areas=[ProfessionalArea.SOFTWARE_DEVELOPMENT.value],
        eligible_countries=["Brasil"],
        technologies=["Java", "Spring Boot"],
        source_url="https://example.com/p26-java-jr",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-2",
    )
    opp_java_clt = Opportunity(
        source_id=src.id,
        external_id="p26-java-clt",
        title="Desenvolvedor Java Júnior CLT",
        description="Contratação CLT.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        experience_requirement_mode=ExperienceRequirementMode.NOT_SPECIFIED.value,
        employment_type=EmploymentType.CLT.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Brasil"],
        technologies=["Java"],
        source_url="https://example.com/p26-java-clt",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-3",
    )
    opp_pleno = Opportunity(
        source_id=src.id,
        external_id="p26-pleno",
        title="Desenvolvedor Backend Pleno",
        description="Preferred qualifications: 2+ years experience with Python.",
        opportunity_type=OpportunityType.OTHER.value,
        seniority_level=SeniorityLevel.MID_LEVEL.value,
        experience_requirement_mode=ExperienceRequirementMode.PREFERRED.value,
        experience_preferred_years=2,
        experience_summary="Desejável: 2+ anos de experiência",
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Worldwide"],
        technologies=["Python"],
        source_url="https://example.com/p26-pleno",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-4",
    )
    opp_senior = Opportunity(
        source_id=src.id,
        external_id="p26-senior",
        title="Senior Backend Software Engineer",
        description="Requirements: 5+ years of experience in backend engineering.",
        opportunity_type=OpportunityType.OTHER.value,
        seniority_level=SeniorityLevel.SENIOR.value,
        experience_requirement_mode=ExperienceRequirementMode.REQUIRED.value,
        experience_min_years=5,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Worldwide"],
        technologies=["Python"],
        source_url="https://example.com/p26-senior",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-5",
    )
    opp_staff = Opportunity(
        source_id=src.id,
        external_id="p26-staff",
        title="Staff Software Engineer",
        description="Lead architecture.",
        opportunity_type=OpportunityType.OTHER.value,
        seniority_level=SeniorityLevel.STAFF_PRINCIPAL.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
        eligible_countries=["Worldwide"],
        source_url="https://example.com/p26-staff",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-6",
    )
    opp_principal = Opportunity(
        source_id=src.id,
        external_id="p26-principal",
        title="Principal Engineer",
        description="Principal backend systems.",
        opportunity_type=OpportunityType.OTHER.value,
        seniority_level=SeniorityLevel.STAFF_PRINCIPAL.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
        eligible_countries=["Worldwide"],
        source_url="https://example.com/p26-principal",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-7",
    )
    opp_freela_sr = Opportunity(
        source_id=src.id,
        external_id="p26-freela-sr",
        title="Freelance Senior Salesforce Developer",
        description="Requirements: 5+ years of experience with Salesforce.",
        opportunity_type=OpportunityType.FREELANCE.value,
        seniority_level=SeniorityLevel.SENIOR.value,
        experience_requirement_mode=ExperienceRequirementMode.REQUIRED.value,
        experience_min_years=5,
        employment_type=EmploymentType.FREELANCE.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
        eligible_countries=["Brazil"],
        technologies=["Salesforce"],
        source_url="https://example.com/p26-freela-sr",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-8",
    )
    opp_freela_jr = Opportunity(
        source_id=src.id,
        external_id="p26-freela-jr",
        title="Freelance Junior Python API Developer",
        description="Build Python integrations.",
        opportunity_type=OpportunityType.FREELANCE.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        experience_requirement_mode=ExperienceRequirementMode.NONE_REQUIRED.value,
        experience_min_years=0,
        employment_type=EmploymentType.FREELANCE.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.API_INTEGRATIONS.value,
        secondary_areas=[ProfessionalArea.BACKEND.value],
        eligible_countries=["Worldwide"],
        technologies=["Python"],
        source_url="https://example.com/p26-freela-jr",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-9",
    )
    opp_unspecified = Opportunity(
        source_id=src.id,
        external_id="p26-unspecified",
        title="Software Engineer",
        description="Build modern web apps.",
        opportunity_type=OpportunityType.OTHER.value,
        seniority_level=SeniorityLevel.UNKNOWN.value,
        experience_requirement_mode=ExperienceRequirementMode.NOT_SPECIFIED.value,
        employment_type=EmploymentType.UNKNOWN.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
        eligible_countries=["Worldwide"],
        technologies=["Python"],
        source_url="https://example.com/p26-unspecified",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-10",
    )
    opp_usa = Opportunity(
        source_id=src.id,
        external_id="p26-usa",
        title="Junior Python Engineer (USA)",
        description="Entry-level backend.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["USA only"],
        source_url="https://example.com/p26-usa",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-11",
    )
    opp_rust_req = Opportunity(
        source_id=src.id,
        external_id="p26-rust-req",
        title="Junior Systems Developer",
        description="Requirements:\nMandatory experience with Rust and Golang.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        experience_requirement_mode=ExperienceRequirementMode.NONE_REQUIRED.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Brasil"],
        technologies=["Rust", "Golang"],
        source_url="https://example.com/p26-rust-req",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-12",
    )
    # Registro antigo que será reclassificado via reclassify_opportunities
    opp_stale_class = Opportunity(
        source_id=src.id,
        external_id="p26-reclassify-me",
        title="Desenvolvedor(a) Back-end Sênior",
        description="Requisitos obrigatórios: 6+ anos de experiência em Java e PostgreSQL.",
        opportunity_type=OpportunityType.OTHER.value,
        seniority_level=SeniorityLevel.UNKNOWN.value,
        experience_requirement_mode=ExperienceRequirementMode.NOT_SPECIFIED.value,
        employment_type=EmploymentType.UNKNOWN.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.UNKNOWN.value,
        eligible_countries=["Brasil"],
        source_url="https://example.com/p26-reclassify",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hp26-13",
    )

    all_opps = [
        opp_intern,
        opp_java_jr,
        opp_java_clt,
        opp_pleno,
        opp_senior,
        opp_staff,
        opp_principal,
        opp_freela_sr,
        opp_freela_jr,
        opp_unspecified,
        opp_usa,
        opp_rust_req,
        opp_stale_class,
    ]
    db_session.add_all(all_opps)
    db_session.commit()

    client = make_client(("10.10.0.99", 50000))
    login_and_get_csrf(client, "phase026.dev@example.com", "StrongPassword123!")

    # API retorna compatíveis (Estágio, Java Jr PJ, Freelance Jr), potenciais (Pleno, Software Engineer s/ nível)
    # e exclui Senior, Staff, Principal, Freelance Senior, CLT bloqueado, USA only e requisito obrigatório de Rust+Golang!
    resp_default = client.get("/api/v1/opportunities?page_size=50").json()
    default_ext_ids = {item["external_id"]: item for item in resp_default["items"]}
    assert "p26-intern" in default_ext_ids
    assert default_ext_ids["p26-intern"]["match"]["overall_compatibility"] == "compatible"
    assert "p26-java-jr" in default_ext_ids
    assert default_ext_ids["p26-java-jr"]["match"]["overall_compatibility"] == "compatible"
    assert default_ext_ids["p26-java-jr"]["match"]["technical_compatibility"] == "compatible"
    assert "Java" in default_ext_ids["p26-java-jr"]["match"]["matched_skills"]
    assert "p26-freela-jr" in default_ext_ids
    assert default_ext_ids["p26-freela-jr"]["match"]["overall_compatibility"] == "compatible"

    assert "p26-pleno" in default_ext_ids
    assert default_ext_ids["p26-pleno"]["match"]["overall_compatibility"] == "potential"
    assert "p26-unspecified" in default_ext_ids
    assert default_ext_ids["p26-unspecified"]["match"]["overall_compatibility"] == "potential"

    for blocked_ext in (
        "p26-senior",
        "p26-staff",
        "p26-principal",
        "p26-freela-sr",
        "p26-java-clt",
        "p26-usa",
        "p26-rust-req",
    ):
        assert blocked_ext not in default_ext_ids

    # Filtros por compatibilidade e senioridade na API
    only_compat = client.get("/api/v1/opportunities?compatibility=compatible&page_size=50").json()
    assert {i["external_id"] for i in only_compat["items"]} == {
        "p26-intern",
        "p26-java-jr",
        "p26-freela-jr",
    }

    only_incompat_sr = client.get(
        "/api/v1/opportunities?compatibility=incompatible&seniority=senior&page_size=50"
    ).json()
    assert {i["external_id"] for i in only_incompat_sr["items"]} >= {"p26-senior", "p26-freela-sr"}

    # Reclassificação idempotente (dry-run e real)
    dry_rep = reclassify_opportunities(db_session, dry_run=True)
    assert dry_rep.updated_count >= 1
    assert db_session.get(Opportunity, opp_stale_class.id).seniority_level == "unknown"

    real_rep = reclassify_opportunities(db_session, dry_run=False)
    assert real_rep.updated_count >= 1
    db_session.expire_all()
    reclassified = db_session.get(Opportunity, opp_stale_class.id)
    assert reclassified.seniority_level == SeniorityLevel.SENIOR.value
    assert reclassified.experience_requirement_mode == ExperienceRequirementMode.REQUIRED.value
    assert reclassified.experience_min_years == 6

    second_rep = reclassify_opportunities(db_session, dry_run=False)
    assert second_rep.updated_count == 0


def test_phase0261_regression_matrix_isolation_independence_and_parsing(
    db_session, make_client
):
    from datetime import date
    import copy

    # 1. Estágio em Desenvolvimento de Software (título literal PT-BR)
    intern_sw_literal = classify_opportunity(
        title="Estágio em Desenvolvimento de Software",
        tags=[],
        description="Apoio em desenvolvimento de APIs e testes.",
    )
    assert intern_sw_literal.seniority_level == SeniorityLevel.INTERNSHIP.value
    assert intern_sw_literal.employment_type == EmploymentType.INTERNSHIP.value
    assert intern_sw_literal.professional_area == ProfessionalArea.SOFTWARE_DEVELOPMENT.value

    # 2. Extração singular/plural e faixas PT/EN sem inferir senioridade apenas por anos
    for phrase, expected_min in (
        ("Requisito: 1 ano de experiência com Python.", 1),
        ("Experiência mínima de 2 anos com APIs REST.", 2),
        ("Requisitos: 3 anos de experiência em backend.", 3),
        ("Necessário 1+ ano de experiência profissional.", 1),
        ("Obrigatório 2+ anos de experiência em desenvolvimento.", 2),
        ("Exige-se 3 a 5 anos de experiência em arquitetura.", 3),
        ("Requisito: 3-5 anos de experiência em sistemas web.", 3),
        ("Requirements: 5+ years of experience in Go.", 5),
        ("Requirements: 1 year of experience building APIs.", 1),
    ):
        exp_dec = classify_opportunity(title="Software Developer", description=phrase)
        assert exp_dec.experience_requirement_mode == ExperienceRequirementMode.REQUIRED.value, phrase
        assert exp_dec.experience_min_years == expected_min, phrase
        # Não infere senioridade apenas pela quantidade de anos exigida!
        assert exp_dec.seniority_level == SeniorityLevel.UNKNOWN.value, phrase

    # 3. Experiência desejável NÃO rebaixa senioridade/opportunity_type para other
    jr_pref_only = classify_opportunity(
        title="Desenvolvedor Python Júnior",
        description="Diferencial: 3 anos de experiência com AWS.",
    )
    assert jr_pref_only.seniority_level == SeniorityLevel.JUNIOR.value
    assert jr_pref_only.experience_requirement_mode == ExperienceRequirementMode.PREFERRED.value
    assert jr_pref_only.experience_preferred_years == 3
    assert jr_pref_only.experience_min_years is None
    assert jr_pref_only.opportunity_type == OpportunityType.JUNIOR.value

    # 4. Experiência técnica com Git/Docker sem tempo profissional NÃO gera falso positivo required
    tech_git_docker = classify_opportunity(
        title="Desenvolvedor Backend Júnior",
        description="Requisitos:\nExperiência com Git ou Docker.",
    )
    assert tech_git_docker.experience_requirement_mode == ExperienceRequirementMode.NOT_SPECIFIED.value
    assert tech_git_docker.experience_min_years is None
    assert tech_git_docker.required_technologies == ()

    tech_docker_pg = classify_opportunity(
        title="Desenvolvedor Backend Júnior",
        description="Requisitos obrigatórios:\nExperiência com PostgreSQL e Docker.",
    )
    assert tech_docker_pg.experience_requirement_mode == ExperienceRequirementMode.NOT_SPECIFIED.value
    assert set(tech_docker_pg.required_technologies) == {"PostgreSQL", "Docker"}

    # 5. Java obrigatório vs Java mencionado incidentalmente
    java_incidental = classify_opportunity(
        title="Frontend React Developer",
        tags=["react", "java"],
        description=(
            "Requirements:\nExperience with React and TypeScript.\n"
            "Collaborate with backend engineers maintaining legacy Java services."
        ),
    )
    assert "React" in java_incidental.required_technologies
    assert "Java" not in java_incidental.required_technologies

    # 6. Cenário real de perfil: suporte de TI CLT/Other com eligible_as_target_role=False + Projetos + Formação
    user = create_user_account(
        db_session,
        email="phase0261.dev@example.com",
        display_name="Phase 02.6.1 Dev",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile = get_or_create_profile(db_session, user)
    profile.country = "Brasil"
    profile.city = "Curitiba"
    profile.state = "PR"
    profile.professional_title = "Estudante de ADS | Java / Spring Boot / React"
    prefs = copy.deepcopy(profile.preferences)
    prefs["internships"]["enabled"] = True
    prefs["internships"]["priority_areas"] = [
        "Desenvolvimento Backend",
        "Engenharia de software",
    ]
    prefs["internships"]["excluded_areas"] = ["Suporte técnico", "Help desk"]
    prefs["junior_developer"]["enabled"] = True
    prefs["junior_developer"]["block_clt"] = True
    prefs["junior_developer"]["accepted_contract_types"] = [
        "Estágio",
        "PJ",
        "Contrato Freelance",
    ]
    prefs["junior_developer"]["priority_areas"] = [
        "Desenvolvimento Backend",
        "Engenharia de software",
        "Full Stack",
        "Frontend",
    ]
    prefs["junior_developer"]["excluded_areas"] = ["Suporte técnico", "Help desk"]
    prefs["freelance"]["enabled"] = True
    prefs["freelance"]["scopes"] = ["Brasil", "Exterior (Internacional)"]
    prefs["freelance"]["priority_categories"] = ["APIs", "Python", "Desenvolvimento de sistemas"]
    profile.preferences = prefs

    sk_java = Skill(
        user_id=user.id,
        name="Java (17/21)",
        category="Linguagens",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
    )
    sk_spring = Skill(
        user_id=user.id,
        name="Spring Boot",
        category="Frameworks",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
    )
    sk_react = Skill(
        user_id=user.id,
        name="React",
        category="Frontend",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
    )
    sk_python = Skill(
        user_id=user.id,
        name="Python",
        category="Linguagens",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
    )
    # Suporte CLT marcado como NÃO elegível + data incompleta NÃO devem contar anos de dev!
    exp_support_clt = WorkExperience(
        user_id=user.id,
        company="Suporte Empresa",
        role="Técnico de TI",
        description="Atendimento de chamados e suporte técnico N1/N2.",
        start_date=date(2024, 1, 1),
        is_current=True,
        experience_type=ExperienceType.CLT.value,
        eligible_as_target_role=False,
    )
    exp_incomplete = WorkExperience(
        user_id=user.id,
        company="Empresa Incompleta",
        role="Desenvolvedor Júnior",
        start_date=date(2023, 1, 1),
        end_date=None,
        is_current=False,
        experience_type=ExperienceType.PJ.value,
        eligible_as_target_role=True,
    )
    edu_ads = Education(
        user_id=user.id,
        institution="Faculdade Tech",
        course="Análise e Desenvolvimento de Sistemas",
        field_of_study="Tecnologia da Informação",
        education_status=EducationStatus.IN_PROGRESS.value,
        start_date=date(2024, 2, 1),
    )
    proj_api = ProfessionalProject(
        user_id=user.id,
        name="API Financeira",
        description="Projeto pessoal com Java e Spring Boot.",
        technologies=["Java", "Spring Boot"],
    )
    db_session.add_all(
        [sk_java, sk_spring, sk_react, sk_python, exp_support_clt, exp_incomplete, edu_ads, proj_api]
    )
    db_session.commit()

    from app.services.opportunities.sync_service import ensure_default_sources

    src = {s.slug: s for s in ensure_default_sources(db_session)}["github_backend_br"]
    now = datetime.now(UTC)

    def _make_opp(
        ext_id: str,
        title: str,
        description: str,
        *,
        opp_type: str | None = None,
        emp_type: str | None = None,
        sen_level: str | None = None,
        eligible_countries: list[str] | None = None,
        technologies: list[str] | None = None,
    ) -> Opportunity:
        dec = classify_opportunity(title=title, tags=technologies or [], description=description)
        return Opportunity(
            source_id=src.id,
            external_id=ext_id,
            title=title,
            description=description,
            opportunity_type=opp_type or dec.opportunity_type,
            seniority_level=sen_level or dec.seniority_level,
            experience_requirement_mode=dec.experience_requirement_mode,
            experience_min_years=dec.experience_min_years,
            experience_preferred_years=dec.experience_preferred_years,
            experience_summary=dec.experience_summary,
            employment_type=emp_type or dec.employment_type,
            work_mode=WorkMode.REMOTE.value,
            professional_area=dec.professional_area,
            secondary_areas=list(dec.secondary_areas),
            eligible_countries=eligible_countries or ["Brasil"],
            technologies=technologies or [],
            source_url=f"https://example.com/{ext_id}",
            first_seen_at=now,
            last_seen_at=now,
            content_hash=f"h-{ext_id}",
        )

    opps_matrix = [
        # 1. Estágio em Desenvolvimento de Software
        _make_opp(
            "m-01-intern-sw",
            "Estágio em Desenvolvimento de Software",
            "Vaga de estágio sem experiência prévia. Aprender APIs REST com Java.",
            technologies=["Java"],
        ),
        # 2. Desenvolvedor Júnior sem experiência
        _make_opp(
            "m-02-jr-noexp",
            "Desenvolvedor Backend Júnior PJ",
            "Experiência profissional anterior não é obrigatória. Stack: Python.",
            technologies=["Python"],
        ),
        # 3. Desenvolvedor Júnior com 1 ano obrigatório (mesmo com Java no perfil -> requer tempo na área-alvo!)
        _make_opp(
            "m-03-jr-1y",
            "Desenvolvedor Java Júnior PJ",
            "Requisitos obrigatórios: 1 ano de experiência com Java e Spring Boot.",
            technologies=["Java", "Spring Boot"],
        ),
        # 4. Júnior com 3 anos desejáveis (não rebaixado)
        _make_opp(
            "m-04-jr-pref3y",
            "Desenvolvedor Python Júnior",
            "Contratação PJ. Diferencial: 3 anos de experiência com AWS.",
            emp_type=EmploymentType.PJ.value,
            technologies=["Python"],
        ),
        # 5. Pleno Mimix AI com 3 anos obrigatórios / nível Pleno (suporte TI NÃO conta!)
        _make_opp(
            "m-05-mimix-pleno",
            "[Remoto] Desenvolvedor(a) Backend Pleno - White Label e Plataforma - Mimix AI",
            "Contratação PJ. **Obrigatórios:** 3 anos de experiência em desenvolvimento backend.",
            emp_type=EmploymentType.PJ.value,
            technologies=["Python"],
        ),
        # 6. Sênior 5 anos
        _make_opp(
            "m-06-senior-5y",
            "Desenvolvedor Backend Sênior",
            "Contratação PJ. Requirements: 5+ years of experience with Python.",
            emp_type=EmploymentType.PJ.value,
            technologies=["Python"],
        ),
        # 7. Staff Engineer
        _make_opp(
            "m-07-staff",
            "Staff Software Engineer",
            "Contratação PJ.",
            emp_type=EmploymentType.PJ.value,
        ),
        # 8. Principal Engineer
        _make_opp(
            "m-08-principal",
            "Principal Engineer",
            "Contratação PJ.",
            emp_type=EmploymentType.PJ.value,
        ),
        # 9. Freelance Júnior (deve aparecer TANTO em seniority=junior QUANTO em employment_type=freelance!)
        _make_opp(
            "m-09-freela-jr",
            "Freelance Junior Python Developer",
            "Projeto freelance remoto sem experiência prévia exigida.",
            opp_type=OpportunityType.FREELANCE.value,
            sen_level=SeniorityLevel.JUNIOR.value,
            emp_type=EmploymentType.FREELANCE.value,
            eligible_countries=["Worldwide"],
            technologies=["Python"],
        ),
        # 10. Freelance Sênior (incompatível para perfil júnior!)
        _make_opp(
            "m-10-freela-sr",
            "Desenvolvedor Sênior Freelance Python",
            "Projeto freelance sênior.",
            opp_type=OpportunityType.FREELANCE.value,
            sen_level=SeniorityLevel.SENIOR.value,
            emp_type=EmploymentType.FREELANCE.value,
            eligible_countries=["Worldwide"],
            technologies=["Python"],
        ),
        # 11. Senioridade desconhecida
        _make_opp(
            "m-11-unknown-sen",
            "Software Engineer",
            "Remoto Worldwide. Build web apps.",
            eligible_countries=["Worldwide"],
            technologies=["Python"],
        ),
        # 15. Java mencionado incidentalmente
        _make_opp(
            "m-15-java-incidental",
            "Frontend React Developer Junior",
            "Contratação PJ. Requirements:\nExperience with React.\nCollaborate closely with backend teams maintaining legacy Java microservices.",
            emp_type=EmploymentType.PJ.value,
            technologies=["React", "Java"],
        ),
        # 16. Git ou Docker sem exigir tempo profissional
        _make_opp(
            "m-16-git-docker",
            "Desenvolvedor Backend Júnior PJ",
            "Contratação PJ. Requisitos:\nExperiência com Git ou Docker.",
            emp_type=EmploymentType.PJ.value,
            technologies=["Git", "Docker"],
        ),
    ]
    db_session.add_all(opps_matrix)
    db_session.commit()

    client = make_client(("10.10.0.100", 50000))
    login_and_get_csrf(client, "phase0261.dev@example.com", "StrongPassword123!")

    # Aba Estágios (governada por seniority=internship)
    intern_res = client.get("/api/v1/opportunities?seniority=internship&page_size=50").json()
    intern_map = {item["external_id"]: item for item in intern_res["items"]}
    assert "m-01-intern-sw" in intern_map
    assert intern_map["m-01-intern-sw"]["professional_area"] == "software_development"
    assert intern_map["m-01-intern-sw"]["employment_type"] == "internship"
    assert intern_map["m-01-intern-sw"]["match"]["overall_compatibility"] == "compatible"

    # Aba Desenvolvedor Júnior (seniority=junior):
    # - inclui m-02-jr-noexp, m-04-jr-pref3y (desejável 3 anos não rebaixa!), m-09-freela-jr, m-15-java-incidental, m-16-git-docker
    # - NÃO inclui m-03-jr-1y (1 ano obrigatório > 0 dev years mesmo com skill Java!) nem m-10-freela-sr
    jr_res = client.get("/api/v1/opportunities?seniority=junior&page_size=50").json()
    jr_map = {item["external_id"]: item for item in jr_res["items"]}
    for expected_jr in ("m-02-jr-noexp", "m-04-jr-pref3y", "m-09-freela-jr", "m-15-java-incidental", "m-16-git-docker"):
        assert expected_jr in jr_map, expected_jr
    assert "m-03-jr-1y" not in jr_map
    assert "m-10-freela-sr" not in jr_map
    assert jr_map["m-04-jr-pref3y"]["experience_requirement_mode"] == "preferred"
    assert jr_map["m-04-jr-pref3y"]["experience_preferred_years"] == 3
    assert jr_map["m-04-jr-pref3y"]["match"]["overall_compatibility"] == "compatible"
    assert jr_map["m-16-git-docker"]["experience_requirement_mode"] == "not_specified"
    assert jr_map["m-16-git-docker"]["match"]["experience_compatibility"] == "compatible"
    assert jr_map["m-16-git-docker"]["match"]["overall_compatibility"] == "potential"

    # Aba Freelancers (employment_type=freelance):
    # - inclui m-09-freela-jr (visível NAS DUAS buscas!)
    # - exclui m-10-freela-sr por padrão, mas exibe em compatibility=incompatible!
    freela_res = client.get("/api/v1/opportunities?employment_type=freelance&page_size=50").json()
    freela_ids = {item["external_id"] for item in freela_res["items"]}
    assert "m-09-freela-jr" in freela_ids
    assert "m-10-freela-sr" not in freela_ids

    freela_incompat = client.get(
        "/api/v1/opportunities?employment_type=freelance&compatibility=incompatible&page_size=50"
    ).json()
    assert "m-10-freela-sr" in {i["external_id"] for i in freela_incompat["items"]}

    # Combinação independente seniority=junior + employment_type=freelance + paginação exata
    combo_res = client.get(
        "/api/v1/opportunities?seniority=junior&employment_type=freelance&page=1&page_size=1"
    ).json()
    assert combo_res["total"] == 1
    assert combo_res["total_pages"] == 1
    assert combo_res["items"][0]["external_id"] == "m-09-freela-jr"

    # Verifica paginação em página 2 para seniority=junior
    page1 = client.get("/api/v1/opportunities?seniority=junior&page=1&page_size=2").json()
    page2 = client.get("/api/v1/opportunities?seniority=junior&page=2&page_size=2").json()
    assert page1["total"] == 5
    assert page1["total_pages"] == 3
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert {i["external_id"] for i in page1["items"]}.isdisjoint(
        {i["external_id"] for i in page2["items"]}
    )

    # Suporte CLT com eligible_as_target_role=False NÃO promove Mimix AI (Pleno) nem m-03-jr-1y!
    incompat_res = client.get("/api/v1/opportunities?compatibility=incompatible&page_size=50").json()
    incompat_map = {item["external_id"]: item for item in incompat_res["items"]}
    for must_incompat in ("m-03-jr-1y", "m-05-mimix-pleno", "m-06-senior-5y", "m-07-staff", "m-08-principal", "m-10-freela-sr"):
        assert must_incompat in incompat_map, must_incompat
    assert incompat_map["m-05-mimix-pleno"]["match"]["seniority_compatibility"] == "incompatible"
    assert incompat_map["m-03-jr-1y"]["match"]["experience_compatibility"] == "incompatible"
    assert incompat_map["m-03-jr-1y"]["match"]["technical_compatibility"] == "compatible"

    # Senioridade desconhecida permanece potential (sem transformar ausência em incompatível)
    pot_res = client.get("/api/v1/opportunities?compatibility=potential&page_size=50").json()
    assert "m-11-unknown-sen" in {i["external_id"] for i in pot_res["items"]}

    # Cenário 13: Experiências sobrepostas NÃO somam meses duplicados
    # [2024-01-01..2024-07-01] (6m) + [2024-04-01..2024-10-01] (6m) -> união = 9m (~0.75 ano, < 1 ano!)
    exp_overlap_1 = WorkExperience(
        user_id=user.id,
        company="Startup A",
        role="Desenvolvedor Júnior",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 7, 1),
        is_current=False,
        experience_type=ExperienceType.PJ.value,
        eligible_as_target_role=True,
    )
    exp_overlap_2 = WorkExperience(
        user_id=user.id,
        company="Startup B",
        role="Desenvolvedor Júnior",
        start_date=date(2024, 4, 1),
        end_date=date(2024, 10, 1),
        is_current=False,
        experience_type=ExperienceType.FREELANCE.value,
        eligible_as_target_role=True,
    )
    db_session.add_all([exp_overlap_1, exp_overlap_2])
    db_session.commit()

    overlap_pot = client.get("/api/v1/opportunities?seniority=junior&compatibility=potential&page_size=50").json()
    overlap_pot_ids = {i["external_id"] for i in overlap_pot["items"]}
    # Com ~0.75 ano real (e não 1.0 ano duplicado!), m-03-jr-1y (1 ano obrigatório) é potential e NÃO compatible!
    assert "m-03-jr-1y" in overlap_pot_ids
    overlap_compat = client.get("/api/v1/opportunities?seniority=junior&compatibility=compatible&page_size=50").json()
    assert "m-03-jr-1y" not in {i["external_id"] for i in overlap_compat["items"]}

    # Quando atinge >= 1.0 ano na área-alvo, m-03-jr-1y passa a compatible!
    exp_extra = WorkExperience(
        user_id=user.id,
        company="Startup C",
        role="Desenvolvedor Java Júnior",
        start_date=date(2024, 10, 1),
        end_date=date(2025, 3, 1),
        is_current=False,
        experience_type=ExperienceType.PJ.value,
        eligible_as_target_role=True,
    )
    db_session.add(exp_extra)
    db_session.commit()

    after_1y_compat = client.get("/api/v1/opportunities?seniority=junior&compatibility=compatible&page_size=50").json()
    assert "m-03-jr-1y" in {i["external_id"] for i in after_1y_compat["items"]}

    # Cenário 14 & 15 (segundo candidato SEM Java):
    # - falha technical_compatibility em m-03-jr-1y (Java obrigatório ausente)
    # - passa em m-15-java-incidental (React obrigatório presente; Java era apenas incidental)
    user_no_java = create_user_account(
        db_session,
        email="phase0261.reactonly@example.com",
        display_name="Phase 02.6.1 React Only",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile_no_java = get_or_create_profile(db_session, user_no_java)
    profile_no_java.country = "Brasil"
    prefs_nj = copy.deepcopy(profile_no_java.preferences)
    prefs_nj["junior_developer"]["enabled"] = True
    prefs_nj["junior_developer"]["block_clt"] = True
    prefs_nj["junior_developer"]["accepted_contract_types"] = ["PJ", "Estágio", "Contrato Freelance"]
    prefs_nj["junior_developer"]["priority_areas"] = ["Frontend", "Backend", "Full Stack"]
    profile_no_java.preferences = prefs_nj
    sk_react_only = Skill(
        user_id=user_no_java.id,
        name="React",
        category="Frontend",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
    )
    exp_react_2y = WorkExperience(
        user_id=user_no_java.id,
        company="React Studio",
        role="Desenvolvedor Frontend Júnior",
        start_date=date(2024, 1, 1),
        end_date=date(2025, 6, 1),
        is_current=False,
        experience_type=ExperienceType.PJ.value,
        eligible_as_target_role=True,
    )
    db_session.add_all([sk_react_only, exp_react_2y])
    db_session.commit()

    client_nj = make_client(("10.10.0.101", 50000))
    login_and_get_csrf(client_nj, "phase0261.reactonly@example.com", "StrongPassword123!")

    nj_compat_ids = {
        i["external_id"]
        for i in client_nj.get("/api/v1/opportunities?seniority=junior&compatibility=compatible&page_size=50").json()["items"]
    }
    assert "m-15-java-incidental" in nj_compat_ids
    assert "m-03-jr-1y" not in nj_compat_ids

    nj_incompat = {
        i["external_id"]: i
        for i in client_nj.get("/api/v1/opportunities?seniority=junior&compatibility=incompatible&page_size=50").json()["items"]
    }
    assert nj_incompat["m-03-jr-1y"]["match"]["technical_compatibility"] == "incompatible"
    assert "Java" in nj_incompat["m-03-jr-1y"]["match"]["missing_required_technologies"]




