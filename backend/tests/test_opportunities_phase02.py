from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.cli import main as cli_main
from app.models.opportunity import (
    EmploymentType,
    ExternalSourceStatus,
    Opportunity,
    OpportunitySource,
    OpportunitySyncRun,
    OpportunityType,
    SyncRunStatus,
    WorkMode,
)
from app.services.auth_service import create_user_account
from app.services.opportunities.connectors.base import (
    ConnectorFetchError,
    ConnectorPayloadError,
)
from app.services.opportunities.connectors.remote_ok import RemoteOKConnector
from app.services.opportunities.connectors.remotive import RemotiveConnector
from app.services.opportunities.matching import evaluate_opportunity_for_user
from app.services.opportunities.sanitization import (
    normalize_canonical_url,
    sanitize_external_html_text,
    validate_safe_external_url,
)
from app.services.opportunities.sync_service import sync_sources
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
    remotive_data = sample_remotive_payload()

    def build_connectors(ok_payload=None, rem_payload=None, fail_ok=False):
        def ok_handler(_):
            if fail_ok:
                return httpx.Response(503)
            return httpx.Response(200, json=ok_payload if ok_payload is not None else remote_data)

        return {
            "remote_ok": RemoteOKConnector(
                transport=httpx.MockTransport(ok_handler),
                max_retries=0,
                sleep_fn=lambda _: None,
            ),
            "remotive": RemotiveConnector(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        200, json=rem_payload if rem_payload is not None else remotive_data
                    )
                ),
                max_retries=0,
                sleep_fn=lambda _: None,
            ),
        }

    # Dry-run não persiste oportunidades
    dry_results = sync_sources(
        db_session,
        dry_run=True,
        connector_overrides=build_connectors(),
    )
    assert all(r.fetched_count == 2 and r.inserted_count == 0 for r in dry_results)
    assert db_session.execute(select(Opportunity)).scalars().all() == []

    # 1a sincronização real
    first_results = sync_sources(
        db_session,
        connector_overrides=build_connectors(),
    )
    assert all(r.status == SyncRunStatus.SUCCESS.value and r.inserted_count == 2 for r in first_results)
    opps = db_session.execute(select(Opportunity).order_by(Opportunity.external_id)).scalars().all()
    assert len(opps) == 4
    first_seen_snapshot = opps[0].first_seen_at

    # Respeito ao intervalo mínimo sem --force
    skipped_results = sync_sources(
        db_session,
        force=False,
        connector_overrides=build_connectors(),
    )
    assert all(r.status == SyncRunStatus.SKIPPED.value for r in skipped_results)

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

    # Falha isolada da fonte NÃO encerra vagas existentes nem derruba a outra fonte
    partial_failure = sync_sources(
        db_session,
        force=True,
        connector_overrides=build_connectors(fail_ok=True),
    )
    status_by_slug = {r.source_slug: r.status for r in partial_failure}
    assert status_by_slug["remote_ok"] == SyncRunStatus.FAILED.value
    assert status_by_slug["remotive"] == SyncRunStatus.SUCCESS.value

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

    # Sincroniza 4 vagas públicas usando transporte mockado
    sync_sources(
        db_session,
        connector_overrides={
            "remote_ok": RemoteOKConnector(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, json=sample_remote_ok_payload())
                ),
                sleep_fn=lambda _: None,
            ),
            "remotive": RemotiveConnector(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, json=sample_remotive_payload())
                ),
                sleep_fn=lambda _: None,
            ),
        },
    )

    client_a = make_client(("10.10.0.1", 50000))
    client_b = make_client(("10.10.0.2", 50000))

    # Sem autenticação -> 401
    assert client_a.get("/api/v1/opportunities").status_code == 401

    csrf_a = login_and_get_csrf(client_a, "user.a@example.com", "StrongPasswordA123!")
    csrf_b = login_and_get_csrf(client_b, "user.b@example.com", "StrongPasswordB123!")

    # Fontes públicas sem exposição de segredos
    sources_resp = client_a.get("/api/v1/opportunities/sources")
    assert sources_resp.status_code == 200
    sources_json = sources_resp.json()
    assert {s["slug"] for s in sources_json} == {"remote_ok", "remotive"}

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
