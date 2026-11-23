"""
Suíte dedicada DX-02.1 + DX-02.2:
- DX-F01: aba Júnior (`junior` + `entry_level`) e visão `unknown` + `potential`
- DX-F07: parsing conservador e matching geográfico de múltiplas cidades
- DX-F08: expiração em tempo real por `deadline_at` (UTC, naive/aware, SQLite e PostgreSQL 16)
- DX-F09: coerência estrita entre `opportunity_type` e `seniority_level`
- DX-F10: reparo conservador e idempotente de mojibake
- DX-F11: rotas GET realmente sem escrita, `init-sources` e inicialização multiworker
- Seção 3.8: `sync-opportunities --dry-run` verdadeiramente sem escrita
- DX-02.2: expansão de Jobicy (`/api/jobs` + `/api/jobs/status`), Himalayas (`/jobs/api` + `/jobs/api/search` + API key opcional + timezones), Remote OK (tags com deduplicação) e GitHub Vagas BR (`per_page=100` + `Link` + `GITHUB_TOKEN` opcional)
- Segurança: ausência de vazamento de tokens em logs/erros, preservação de regras de matching e defaults de IA/fontes desabilitadas.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone
import logging
import threading

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.cli import main as cli_main
from app.core.config import Settings
from app.models.opportunity import (
    EmploymentType,
    ExperienceRequirementMode,
    ExternalSourceStatus,
    Opportunity,
    OpportunitySource,
    OpportunitySourceLink,
    OpportunitySyncRun,
    OpportunityType,
    ProfessionalArea,
    SeniorityLevel,
    SyncRunStatus,
    WorkMode,
)
from app.services.auth_service import create_user_account
from app.services.opportunities.classification import (
    classify_opportunity,
    reconcile_structured_classification,
)
from app.services.opportunities.connectors.base import (
    ConnectorFetchError,
    ConnectorPayloadError,
)
from app.services.opportunities.connectors.github_vagas import (
    GitHubBackendBRConnector,
    GitHubFrontendBRConnector,
    parse_github_next_link,
)
from app.services.opportunities.connectors.himalayas import (
    DEFAULT_HIMALAYAS_SEARCH_QUERIES,
    HimalayasConnector,
)
from app.services.opportunities.connectors.jobicy import (
    JobicyConnector,
)
from app.services.opportunities.connectors.remote_ok import (
    RemoteOKConnector,
)
from app.services.opportunities.connectors.remotive import RemotiveConnector
from app.services.opportunities.matching import (
    evaluate_opportunity_for_user,
    is_deadline_expired,
    parse_location_cities,
    resolve_effective_source_status,
)
from app.services.opportunities.opportunity_service import (
    get_opportunity_for_user,
    list_opportunities,
    list_public_sources,
)
from app.services.opportunities.sanitization import (
    repair_mojibake,
    sanitize_external_html_text,
    sanitize_plain_text,
)
from app.services.opportunities.sync_service import (
    ensure_default_sources,
    reclassify_opportunities,
    sync_sources,
)
from app.services.profile_service import get_or_create_profile


def _login_and_get_csrf(client, email: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _snapshot_opportunity_tables(db: Session) -> dict[str, list[tuple]]:
    sources = [
        (s.id, s.slug, s.enabled, s.last_synced_at, s.last_error_summary)
        for s in db.execute(select(OpportunitySource).order_by(OpportunitySource.slug)).scalars().all()
    ]
    opps = [
        (o.id, o.external_id, o.title, o.source_status, o.missing_sync_count, o.deadline_at)
        for o in db.execute(select(Opportunity).order_by(Opportunity.id)).scalars().all()
    ]
    links = [
        (l.id, l.external_id, l.source_status, l.missing_sync_count)
        for l in db.execute(select(OpportunitySourceLink).order_by(OpportunitySourceLink.id)).scalars().all()
    ]
    runs = [
        (r.id, r.source_id, r.status, r.fetched_count)
        for r in db.execute(select(OpportunitySyncRun).order_by(OpportunitySyncRun.id)).scalars().all()
    ]
    return {
        "sources": sources,
        "opps": opps,
        "links": links,
        "runs": runs,
    }


# ==============================================================================
# DX-F01 + DX-F01 complementar: Aba Júnior (junior + entry_level) e visão unknown
# ==============================================================================


def test_dx021_f01_junior_tab_includes_entry_level_and_unknown_potential_view(
    db_session: Session, make_client
):
    user = create_user_account(
        db_session,
        email="dx021.f01@example.com",
        display_name="DX021 User",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile = get_or_create_profile(db_session, user)
    profile.country = "Brasil"
    profile.city = "São Paulo"
    profile.state = "SP"
    prefs = copy.deepcopy(profile.preferences)
    prefs["junior_developer"]["enabled"] = True
    prefs["junior_developer"]["block_clt"] = True
    prefs["junior_developer"]["accepted_contract_types"] = ["PJ", "Estágio", "Contrato Freelance"]
    prefs["junior_developer"]["priority_areas"] = ["Desenvolvimento Backend", "Full Stack", "Python"]
    prefs["junior_developer"]["excluded_areas"] = ["Suporte técnico"]
    profile.preferences = prefs
    db_session.commit()

    src = {s.slug: s for s in ensure_default_sources(db_session)}["himalayas"]
    now = datetime.now(UTC)

    def _opp(ext_id: str, **kwargs) -> Opportunity:
        base = dict(
            source_id=src.id,
            external_id=ext_id,
            title=f"Opportunity {ext_id}",
            description="Build Python FastAPI services.",
            opportunity_type=OpportunityType.JUNIOR.value,
            seniority_level=SeniorityLevel.JUNIOR.value,
            experience_requirement_mode=ExperienceRequirementMode.NONE_REQUIRED.value,
            employment_type=EmploymentType.PJ.value,
            work_mode=WorkMode.REMOTE.value,
            professional_area=ProfessionalArea.BACKEND.value,
            secondary_areas=[ProfessionalArea.SOFTWARE_DEVELOPMENT.value],
            eligible_countries=["Worldwide"],
            technologies=["Python", "FastAPI"],
            source_url=f"https://example.com/{ext_id}",
            first_seen_at=now,
            last_seen_at=now,
            content_hash=f"hash-{ext_id}",
            source_status=ExternalSourceStatus.ACTIVE.value,
        )
        base.update(kwargs)
        return Opportunity(**base)

    opps = [
        _opp("dx-jr", title="Junior Python Backend Developer", seniority_level=SeniorityLevel.JUNIOR.value),
        _opp("dx-entry", title="Entry-Level Python Backend Engineer", seniority_level=SeniorityLevel.ENTRY_LEVEL.value),
        # Entry-level CLT bloqueada pela regra block_clt (preservação Seção 6)
        _opp(
            "dx-entry-clt",
            title="Entry-Level Python Engineer CLT",
            seniority_level=SeniorityLevel.ENTRY_LEVEL.value,
            employment_type=EmploymentType.CLT.value,
        ),
        # Entry-level exigindo 1+ ano obrigatório (preservação Seção 6)
        _opp(
            "dx-entry-1y",
            title="Entry-Level Python Developer",
            description="Requirements: 1+ year of experience with Python.",
            seniority_level=SeniorityLevel.ENTRY_LEVEL.value,
            experience_requirement_mode=ExperienceRequirementMode.REQUIRED.value,
            experience_min_years=1,
        ),
        # Níveis superiores nunca entram na aba Júnior
        _opp("dx-mid", title="Mid-level Python Developer", opportunity_type=OpportunityType.OTHER.value, seniority_level=SeniorityLevel.MID_LEVEL.value),
        _opp("dx-senior", title="Senior Python Developer", opportunity_type=OpportunityType.OTHER.value, seniority_level=SeniorityLevel.SENIOR.value),
        _opp("dx-staff", title="Staff Engineer", opportunity_type=OpportunityType.OTHER.value, seniority_level=SeniorityLevel.STAFF_PRINCIPAL.value),
        _opp("dx-mgmt", title="Engineering Manager", opportunity_type=OpportunityType.OTHER.value, seniority_level=SeniorityLevel.MANAGEMENT.value),
        # Unknown potencialmente compatível (deve aparecer apenas na visão unknown + potential)
        _opp(
            "dx-unk-pot",
            title="Software Engineer Python",
            opportunity_type=OpportunityType.OTHER.value,
            seniority_level=SeniorityLevel.UNKNOWN.value,
            experience_requirement_mode=ExperienceRequirementMode.NOT_SPECIFIED.value,
            employment_type=EmploymentType.UNKNOWN.value,
        ),
        # Unknown incompatível (suporte técnico) -> nunca entra na visão unknown + potential
        _opp(
            "dx-unk-incompat",
            title="Technical Support Specialist",
            opportunity_type=OpportunityType.OTHER.value,
            seniority_level=SeniorityLevel.UNKNOWN.value,
            professional_area=ProfessionalArea.TECHNICAL_SUPPORT.value,
            secondary_areas=[],
        ),
        # Unknown expirada em tempo real (deadline passado, mas source_status=active no DB!)
        _opp(
            "dx-unk-expired",
            title="Python API Developer",
            opportunity_type=OpportunityType.OTHER.value,
            seniority_level=SeniorityLevel.UNKNOWN.value,
            experience_requirement_mode=ExperienceRequirementMode.NOT_SPECIFIED.value,
            employment_type=EmploymentType.UNKNOWN.value,
            deadline_at=now - timedelta(hours=2),
            source_status=ExternalSourceStatus.ACTIVE.value,
        ),
    ]
    db_session.add_all(opps)
    db_session.commit()

    client = make_client(("10.20.0.1", 50000))
    _login_and_get_csrf(client, "dx021.f01@example.com", "StrongPassword123!")

    # 1. Consulta combinada da aba Júnior: ?seniority=junior&seniority=entry_level
    jr_combo = client.get(
        "/api/v1/opportunities?seniority=junior&seniority=entry_level&page_size=50"
    )
    assert jr_combo.status_code == 200
    combo_items = {i["external_id"]: i for i in jr_combo.json()["items"]}
    assert set(combo_items.keys()) == {"dx-jr", "dx-entry"}
    # Preserva classificação original sem mascarar entry_level como junior
    assert combo_items["dx-jr"]["seniority_level"] == "junior"
    assert combo_items["dx-entry"]["seniority_level"] == "entry_level"

    # 2. Retrocompatibilidade com único parâmetro ?seniority=junior
    jr_only = client.get("/api/v1/opportunities?seniority=junior&page_size=50").json()
    assert {i["external_id"] for i in jr_only["items"]} == {"dx-jr"}

    # 3. Filtros independentes combinados com múltiplas senioridades
    jr_pj_backend = client.get(
        "/api/v1/opportunities?seniority=junior&seniority=entry_level&area=backend&employment_type=pj&page_size=50"
    ).json()
    assert {i["external_id"] for i in jr_pj_backend["items"]} == {"dx-jr", "dx-entry"}

    # 4. Visão separada: seniority=unknown + compatibility=potential
    unk_pot = client.get(
        "/api/v1/opportunities?seniority=unknown&compatibility=potential&page_size=50"
    )
    assert unk_pot.status_code == 200
    unk_items = {i["external_id"]: i for i in unk_pot.json()["items"]}
    assert set(unk_items.keys()) == {"dx-unk-pot"}
    assert unk_items["dx-unk-pot"]["seniority_level"] == "unknown"
    assert unk_items["dx-unk-pot"]["match"]["overall_compatibility"] == "potential"
    assert unk_items["dx-unk-pot"]["match"]["eligible"] is True


# ==============================================================================
# DX-F07: Parsing e matching de múltiplas cidades
# ==============================================================================


def test_dx021_f07_multi_city_parsing_and_geographic_matching(db_session: Session):
    assert parse_location_cities("Belo Horizonte ou São Paulo, Brasil") == (
        ["Belo Horizonte", "São Paulo"],
        None,
    )
    assert parse_location_cities("Curitiba / São Paulo") == (
        ["Curitiba", "São Paulo"],
        None,
    )
    assert parse_location_cities("Curitiba/PR ou São Paulo/SP") == (
        ["Curitiba", "São Paulo"],
        None,
    )
    assert parse_location_cities("São Paulo, Campinas ou Sorocaba - SP") == (
        ["São Paulo", "Campinas", "Sorocaba"],
        "SP",
    )
    assert parse_location_cities("Campinas, São Paulo, Brasil") == (["Campinas"], None)
    assert parse_location_cities("Rio de Janeiro, RJ") == (["Rio de Janeiro"], "RJ")
    assert parse_location_cities("São José dos Campos / Jacareí - SP") == (
        ["São José dos Campos", "Jacareí"],
        "SP",
    )
    assert parse_location_cities("Híbrido - Porto Alegre, RS") == (["Porto Alegre"], "RS")
    assert parse_location_cities("Brasil") == ([], None)

    # Verifica extração no conector GitHub preservando location_text original
    gh = GitHubBackendBRConnector(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    drafts = gh.parse_payload(
        [
            {
                "number": 9001,
                "state": "open",
                "title": "[Belo Horizonte ou São Paulo, Brasil] Desenvolvedor Backend Júnior na Empresa X",
                "html_url": "https://github.com/backend-br/vagas/issues/9001",
                "created_at": "2026-11-15T10:00:00Z",
                "labels": [{"name": "Híbrido"}, {"name": "Júnior"}, {"name": "PJ"}, {"name": "Python"}],
                "body": "Atuação híbrida em BH ou SP com Python.",
            }
        ]
    )
    assert len(drafts) == 1
    assert drafts[0].location_text == "Belo Horizonte ou São Paulo, Brasil"
    assert drafts[0].raw_metadata["cities"] == ["Belo Horizonte", "São Paulo"]

    # Matching para perfis em São Paulo (compatível), Belo Horizonte (compatível),
    # Curitiba (excluído) e prefixo parcial "São" (sem fuzzy matching -> excluído)
    user = create_user_account(
        db_session,
        email="dx021.f07@example.com",
        display_name="Geo User",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile = get_or_create_profile(db_session, user)
    profile.country = "Brasil"
    profile.city = "São Paulo"
    profile.state = "SP"
    db_session.commit()

    # Testa inclusive registro legado salvo com city="Belo Horizonte ou São Paulo" e sem raw_metadata["cities"]
    legacy_multi_opp = Opportunity(
        external_id="legacy-multi-city",
        title="Desenvolvedor Python Júnior",
        description="Python backend.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.HYBRID.value,
        professional_area=ProfessionalArea.BACKEND.value,
        location_text="Belo Horizonte ou São Paulo, Brasil",
        city="Belo Horizonte ou São Paulo",
        country="Brasil",
        eligible_countries=["Brasil"],
        technologies=["Python"],
        source_url="https://example.com/multi-city",
        content_hash="h-mc",
    )

    assert evaluate_opportunity_for_user(legacy_multi_opp, profile).geographic_eligibility == "eligible"

    profile.city = "Belo Horizonte"
    assert evaluate_opportunity_for_user(legacy_multi_opp, profile).geographic_eligibility == "eligible"

    profile.city = "Curitiba"
    ev_cwb = evaluate_opportunity_for_user(legacy_multi_opp, profile)
    assert ev_cwb.geographic_eligibility == "excluded"
    assert ev_cwb.eligible is False

    # Sem fuzzy matching genérico
    profile.city = "Paulo"
    assert evaluate_opportunity_for_user(legacy_multi_opp, profile).geographic_eligibility == "excluded"


# ==============================================================================
# DX-F08: Expiração em tempo real por deadline_at (sem escrita em GET)
# ==============================================================================


def test_dx021_f08_realtime_deadline_expiration_and_no_db_mutation(
    db_session: Session, make_client
):
    ref_now = datetime(2026, 11, 22, 18, 0, 0, tzinfo=UTC)

    # Testes unitários diretos de comparação temporal
    assert is_deadline_expired(ref_now + timedelta(seconds=1), now=ref_now) is False
    assert is_deadline_expired(ref_now, now=ref_now) is True
    assert is_deadline_expired(ref_now - timedelta(seconds=1), now=ref_now) is True
    # Datetime naive (sem timezone) tratado como UTC
    assert is_deadline_expired(datetime(2026, 11, 22, 17, 59, 59), now=ref_now) is True
    assert is_deadline_expired(datetime(2026, 11, 22, 18, 0, 0), now=ref_now) is True
    assert is_deadline_expired(datetime(2026, 11, 22, 18, 0, 1), now=ref_now) is False
    # Datetime com offset -03:00 (15:00-03:00 == 18:00 UTC)
    brt = timezone(timedelta(hours=-3))
    assert is_deadline_expired(datetime(2026, 11, 22, 15, 0, 0, tzinfo=brt), now=ref_now) is True
    assert is_deadline_expired(datetime(2026, 11, 22, 15, 0, 1, tzinfo=brt), now=ref_now) is False

    user = create_user_account(
        db_session,
        email="dx021.f08@example.com",
        display_name="Deadline User",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile = get_or_create_profile(db_session, user)
    profile.country = "Brasil"
    db_session.commit()

    src = {s.slug: s for s in ensure_default_sources(db_session)}["himalayas"]
    real_now = datetime.now(UTC)

    opp_future = Opportunity(
        source_id=src.id,
        external_id="dl-future",
        title="Junior Python Developer Future",
        description="Python FastAPI.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Worldwide"],
        technologies=["Python"],
        source_url="https://example.com/dl-future",
        first_seen_at=real_now,
        last_seen_at=real_now,
        deadline_at=real_now + timedelta(days=5),
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-dl-future",
    )
    opp_past = Opportunity(
        source_id=src.id,
        external_id="dl-past",
        title="Junior Python Developer Expired",
        description="Python FastAPI.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Worldwide"],
        technologies=["Python"],
        source_url="https://example.com/dl-past",
        first_seen_at=real_now,
        last_seen_at=real_now,
        deadline_at=real_now - timedelta(hours=3),
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-dl-past",
    )
    opp_equal = Opportunity(
        source_id=src.id,
        external_id="dl-equal",
        title="Junior Python Developer Exact",
        description="Python FastAPI.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Worldwide"],
        technologies=["Python"],
        source_url="https://example.com/dl-equal",
        first_seen_at=real_now,
        last_seen_at=real_now,
        deadline_at=ref_now,
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-dl-equal",
    )
    db_session.add_all([opp_future, opp_past, opp_equal])
    db_session.commit()

    # Avaliação determinística com relógio injetado para deadline == ref_now
    eval_eq = evaluate_opportunity_for_user(opp_equal, profile, now=ref_now)
    assert eval_eq.eligible is False
    assert eval_eq.overall_compatibility == "incompatible"
    assert resolve_effective_source_status(opp_equal, now=ref_now) == ExternalSourceStatus.EXPIRED.value

    # Consulta via API (listagem, detalhe e fontes) não pode alterar source_status persistido
    client = make_client(("10.20.0.2", 50000))
    _login_and_get_csrf(client, "dx021.f08@example.com", "StrongPassword123!")

    active_list = client.get("/api/v1/opportunities?seniority=junior&page_size=50").json()
    assert {i["external_id"] for i in active_list["items"]} == {"dl-future"}

    detail_past = client.get(f"/api/v1/opportunities/{opp_past.id}").json()
    assert detail_past["source_status"] == ExternalSourceStatus.EXPIRED.value
    assert detail_past["match"]["eligible"] is False
    assert detail_past["match"]["overall_compatibility"] == "incompatible"

    sources_map = {s["slug"]: s for s in client.get("/api/v1/opportunities/sources").json()}
    assert sources_map["himalayas"]["open_opportunities_count"] == 1
    assert sources_map["himalayas"]["closed_or_expired_count"] == 2

    # Registro no banco continua estritamente intacto (nenhum UPDATE implícito em GET)
    db_session.expire_all()
    persisted_past = db_session.get(Opportunity, opp_past.id)
    assert persisted_past is not None
    assert persisted_past.source_status == ExternalSourceStatus.ACTIVE.value


# ==============================================================================
# DX-F09: Coerência entre opportunity_type e seniority_level
# ==============================================================================


def test_dx021_f09_coherence_between_opportunity_type_and_seniority_level(db_session: Session):
    # 1. Jobicy: jobLevel="Entry-level" com título genérico -> entry_level + junior
    jobicy = JobicyConnector(
        industries=("engineering",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"jobs": []})),
    )
    jobicy_drafts = jobicy.parse_payload(
        {
            "jobs": [
                {
                    "id": 1001,
                    "url": "https://jobicy.com/jobs/1001-dev",
                    "jobTitle": "Software Developer",
                    "companyName": "EntryCo",
                    "jobIndustry": ["Engineering"],
                    "jobType": ["Contract"],
                    "jobGeo": "Anywhere",
                    "jobLevel": "Entry-level",
                    "jobDescription": "<p>Build Python APIs.</p>",
                },
                # Conflito: título Sênior com jobLevel Junior -> nível superior vence!
                {
                    "id": 1002,
                    "url": "https://jobicy.com/jobs/1002-sr",
                    "jobTitle": "Senior Backend Engineer",
                    "companyName": "ConflictCo",
                    "jobIndustry": ["Engineering"],
                    "jobType": ["Full-Time"],
                    "jobGeo": "Anywhere",
                    "jobLevel": "Junior",
                    "jobDescription": "<p>Lead backend architecture.</p>",
                },
                # Substring perigosa: Internal Tools com tipo não-estágio
                {
                    "id": 1003,
                    "url": "https://jobicy.com/jobs/1003-internal",
                    "jobTitle": "Internal Platform Engineer",
                    "companyName": "InternalCo",
                    "jobIndustry": ["Engineering"],
                    "jobType": ["Internal"],
                    "jobGeo": "Anywhere",
                    "jobLevel": "Any",
                    "jobDescription": "<p>Manage internal tooling.</p>",
                },
            ]
        }
    )
    by_id = {d.external_id: d for d in jobicy_drafts}
    assert by_id["1001"].opportunity_type == OpportunityType.JUNIOR.value
    assert by_id["1001"].seniority_level == SeniorityLevel.ENTRY_LEVEL.value
    assert by_id["1002"].opportunity_type == OpportunityType.OTHER.value
    assert by_id["1002"].seniority_level == SeniorityLevel.SENIOR.value
    assert by_id["1003"].opportunity_type == OpportunityType.OTHER.value
    assert by_id["1003"].seniority_level == SeniorityLevel.UNKNOWN.value

    # 2. Himalayas: seniority=["Entry-level"] mantém entry_level; ["Mid-level", "Junior"] não rebaixa
    future_epoch = int((datetime.now(UTC) + timedelta(days=15)).timestamp())
    him = HimalayasConnector(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"jobs": []})),
    )
    him_drafts = him.parse_payload(
        {
            "jobs": [
                {
                    "guid": "https://himalayas.app/companies/c1/jobs/dev-1",
                    "title": "Software Engineer",
                    "companyName": "C1",
                    "employmentType": "Full Time",
                    "seniority": ["Entry-level"],
                    "locationRestrictions": [],
                    "categories": ["Backend"],
                    "description": "<p>Build backend services.</p>",
                    "expiryDate": future_epoch,
                },
                {
                    "guid": "https://himalayas.app/companies/c2/jobs/dev-2",
                    "title": "Software Engineer",
                    "companyName": "C2",
                    "employmentType": "Full Time",
                    "seniority": ["Mid-level", "Junior"],
                    "locationRestrictions": [],
                    "categories": ["Backend"],
                    "description": "<p>Build backend services.</p>",
                    "expiryDate": future_epoch,
                },
                {
                    "guid": "https://himalayas.app/companies/c3/jobs/internal-tool",
                    "title": "Internal Systems Developer",
                    "companyName": "C3",
                    "employmentType": "Internal",
                    "seniority": [],
                    "locationRestrictions": [],
                    "categories": ["Backend"],
                    "description": "<p>Internal tools.</p>",
                    "expiryDate": future_epoch,
                },
            ]
        }
    )
    him_by_id = {d.external_id: d for d in him_drafts}
    assert him_by_id["c1/jobs/dev-1"].opportunity_type == OpportunityType.JUNIOR.value
    assert him_by_id["c1/jobs/dev-1"].seniority_level == SeniorityLevel.ENTRY_LEVEL.value
    assert him_by_id["c2/jobs/dev-2"].opportunity_type == OpportunityType.OTHER.value
    assert him_by_id["c2/jobs/dev-2"].seniority_level == SeniorityLevel.MID_LEVEL.value
    assert him_by_id["c3/jobs/internal-tool"].opportunity_type == OpportunityType.OTHER.value
    assert him_by_id["c3/jobs/internal-tool"].seniority_level == SeniorityLevel.UNKNOWN.value

    # 3. GitHub BR + reclassify_opportunities: label "Júnior" sem texto júnior no título sincroniza ambos os campos
    gh = GitHubBackendBRConnector(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    gh_drafts = gh.parse_payload(
        [
            {
                "number": 777,
                "state": "open",
                "title": "[Remoto] Desenvolvedor Backend Python na AcmeBR",
                "html_url": "https://github.com/backend-br/vagas/issues/777",
                "created_at": "2026-11-15T10:00:00Z",
                "labels": [{"name": "Júnior"}, {"name": "PJ"}, {"name": "Python"}],
                "body": "Atuação com FastAPI.",
            },
            {
                "number": 778,
                "state": "open",
                "title": "[Remoto] Desenvolvedor Backend Sênior na AcmeBR",
                "html_url": "https://github.com/backend-br/vagas/issues/778",
                "created_at": "2026-11-15T10:00:00Z",
                "labels": [{"name": "Júnior"}, {"name": "PJ"}, {"name": "Python"}],
                "body": "Atuação com FastAPI.",
            },
        ]
    )
    gh_by_id = {d.external_id: d for d in gh_drafts}
    assert gh_by_id["gh-backend-br-777"].opportunity_type == OpportunityType.JUNIOR.value
    assert gh_by_id["gh-backend-br-777"].seniority_level == SeniorityLevel.JUNIOR.value
    assert gh_by_id["gh-backend-br-778"].opportunity_type == OpportunityType.OTHER.value
    assert gh_by_id["gh-backend-br-778"].seniority_level == SeniorityLevel.SENIOR.value

    # Reclassificação corrige registro legado incoerente (opportunity_type=junior, seniority_level=unknown)
    src = {s.slug: s for s in ensure_default_sources(db_session)}["jobicy"]
    now = datetime.now(UTC)
    incoherent = Opportunity(
        source_id=src.id,
        external_id="incoh-1",
        title="Backend Developer",
        description="Build APIs in Python.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.UNKNOWN.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Worldwide"],
        source_url="https://jobicy.com/jobs/incoh-1",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="h-incoh",
        raw_metadata={"job_level": "Entry-level"},
    )
    db_session.add(incoherent)
    db_session.commit()

    rep = reclassify_opportunities(db_session, source_slug="jobicy", dry_run=False)
    assert rep.updated_count == 1
    db_session.expire_all()
    fixed = db_session.get(Opportunity, incoherent.id)
    assert fixed is not None
    assert fixed.opportunity_type == OpportunityType.JUNIOR.value
    assert fixed.seniority_level == SeniorityLevel.ENTRY_LEVEL.value

    # Garantia direta do helper de reconciliação
    dec_gen = classify_opportunity(title="Software Engineer", description="Build APIs.")
    assert reconcile_structured_classification(dec_gen, metadata_levels=["Intern"]) == (
        OpportunityType.INTERNSHIP.value,
        EmploymentType.INTERNSHIP.value,
        SeniorityLevel.INTERNSHIP.value,
    )


def test_dx02_aud01_reconcile_structured_classification_canonical_entry_level_and_variants():
    """
    Regressão pós-auditoria (DX02-AUD-01): garante reconhecimento do token canônico
    `entry_level` (com underscore) e variantes, preservando coerência e precedência.
    """
    dec_unknown = classify_opportunity(title="Software Engineer", description="Build Python APIs.")
    assert dec_unknown.opportunity_type == OpportunityType.OTHER.value
    assert dec_unknown.seniority_level == SeniorityLevel.UNKNOWN.value

    # 1, 2, 3, 5, 6. Variantes de entry_level -> (junior, unknown, entry_level)
    for token in ("entry_level", "entry-level", "entry level", "graduate", "trainee"):
        opp_type, emp_type, sen_level = reconcile_structured_classification(
            dec_unknown,
            metadata_levels=[token],
        )
        assert opp_type == OpportunityType.JUNIOR.value, f"falhou para token={token}"
        assert emp_type == EmploymentType.UNKNOWN.value, f"falhou para token={token}"
        assert sen_level == SeniorityLevel.ENTRY_LEVEL.value, f"falhou para token={token}"

    # Token canônico `entry_level` também reconhecido diretamente via classify_opportunity
    dec_direct_entry = classify_opportunity(
        title="Software Engineer",
        description="Build Python APIs.",
        metadata_levels=["entry_level"],
    )
    assert dec_direct_entry.opportunity_type == OpportunityType.JUNIOR.value
    assert dec_direct_entry.seniority_level == SeniorityLevel.ENTRY_LEVEL.value

    # 4. Token `junior` -> (junior, unknown, junior)
    assert reconcile_structured_classification(dec_unknown, metadata_levels=["junior"]) == (
        OpportunityType.JUNIOR.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.JUNIOR.value,
    )

    # 7. Classificação previamente conhecida não é degradada
    dec_known_junior = classify_opportunity(
        title="Junior Backend Developer",
        description="Build Python APIs.",
    )
    assert dec_known_junior.opportunity_type == OpportunityType.JUNIOR.value
    assert dec_known_junior.seniority_level == SeniorityLevel.JUNIOR.value
    assert reconcile_structured_classification(
        dec_known_junior,
        metadata_levels=["entry_level"],
    ) == (
        OpportunityType.JUNIOR.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.JUNIOR.value,
    )

    # 8. Precedência de evidências explícitas de senioridade superior
    dec_senior = classify_opportunity(
        title="Senior Backend Engineer",
        description="Architect distributed services.",
    )
    assert reconcile_structured_classification(
        dec_senior,
        metadata_levels=["entry_level"],
    ) == (
        OpportunityType.OTHER.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.SENIOR.value,
    )

    dec_mid = classify_opportunity(
        title="Mid-level Backend Engineer",
        description="Build distributed services.",
    )
    assert reconcile_structured_classification(
        dec_mid,
        metadata_levels=["entry_level"],
    ) == (
        OpportunityType.OTHER.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.MID_LEVEL.value,
    )

    # Conflito nos próprios metadados estruturados: nível superior prevalece
    assert reconcile_structured_classification(
        dec_unknown,
        metadata_levels=["senior", "entry_level"],
    ) == (
        OpportunityType.OTHER.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.UNKNOWN.value,
    )

    # Exigência explícita de >= 3 anos impede promoção para entry_level
    dec_exp_required = classify_opportunity(
        title="Backend Developer",
        description="Requirements: 4+ years of experience in Python required.",
    )
    assert reconcile_structured_classification(
        dec_exp_required,
        metadata_levels=["entry_level"],
    ) == (
        OpportunityType.OTHER.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.UNKNOWN.value,
    )

    # 9. Coerência entre opportunity_type=junior e seniority_level=entry_level
    # mesmo quando a decisão intermediária chegou com opportunity_type=junior e seniority_level=unknown
    from dataclasses import replace

    dec_incoherent_junior = replace(
        dec_unknown,
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.UNKNOWN.value,
    )
    assert reconcile_structured_classification(
        dec_incoherent_junior,
        metadata_levels=["entry_level"],
    ) == (
        OpportunityType.JUNIOR.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.ENTRY_LEVEL.value,
    )

    # 10. Entrada já classificada como estágio permanece estágio
    dec_internship = classify_opportunity(
        title="Estágio em Desenvolvimento Backend",
        description="Atuação com Python e SQL.",
    )
    assert dec_internship.opportunity_type == OpportunityType.INTERNSHIP.value
    assert dec_internship.seniority_level == SeniorityLevel.INTERNSHIP.value
    assert reconcile_structured_classification(
        dec_internship,
        metadata_levels=["entry_level"],
    ) == (
        OpportunityType.INTERNSHIP.value,
        EmploymentType.INTERNSHIP.value,
        SeniorityLevel.INTERNSHIP.value,
    )


# ==============================================================================
# DX-F10: Reparo conservador de mojibake
# ==============================================================================


def test_dx021_f10_conservative_mojibake_repair_and_multilingual_safety():
    # Casos reais corrompidos
    assert repair_mojibake("MÃ¼nchen") == "München"
    assert repair_mojibake("Ciudad de MÃ©xico") == "Ciudad de México"
    assert repair_mojibake("SÃ£o Paulo") == "São Paulo"
    assert repair_mojibake("EstÃ¡gio em ProgramaÃ§Ã£o") == "Estágio em Programação"
    assert repair_mojibake("Desenvolvedor JÃºnior â€” Remoto") == "Desenvolvedor Júnior — Remoto"

    # Integração com sanitize_plain_text e sanitize_external_html_text
    assert sanitize_plain_text("MÃ¼nchen / Ciudad de MÃ©xico") == "München / Ciudad de México"
    assert sanitize_plain_text("Please\u00c2\u00a0note:\u00c2\u00a0SÃ£o Paulo") == "Please note: São Paulo"
    assert (
        sanitize_external_html_text("<p>EstÃ¡gio em ProgramaÃ§Ã£o &mdash; SÃ£o Paulo</p>")
        == "Estágio em Programação — São Paulo"
    )

    # Textos válidos em PT, EN, ES, DE e símbolos NÃO podem ser corrompidos
    valid_samples = [
        "São Paulo, Florianópolis, ação, coração, programação, estágio júnior",
        "München, Zürich, Straße, Größe, Überprüfung",
        "Ciudad de México, España, niño, ¡Hola! ¿Cómo estás?",
        "Remote Software Engineer — $60,000 – €55,000 • 100% online, 20m², nº 10",
    ]
    for sample in valid_samples:
        assert repair_mojibake(sample) == sample
        assert repair_mojibake(repair_mojibake(sample)) == sample
        assert sanitize_plain_text(sample) == sample

    # Idempotência para entradas previamente corrompidas
    repaired = repair_mojibake("MÃ¼nchen — SÃ£o Paulo — Ciudad de MÃ©xico")
    assert repair_mojibake(repaired) == repaired


# ==============================================================================
# DX-F11 & Seção 3.8: GET sem escrita, init-sources, multiworker e dry-run sem escrita
# ==============================================================================


def test_dx021_f11_get_routes_are_strictly_readonly_and_init_sources_is_concurrency_safe(
    db_engine, db_session: Session, make_client, monkeypatch
):
    user = create_user_account(
        db_session,
        email="dx021.f11@example.com",
        display_name="ReadOnly User",
        password="StrongPassword123!",
        is_admin=False,
    )
    db_session.commit()

    # Banco sem fontes inicializadas e sem perfil persistido para o usuário
    before_snap = _snapshot_opportunity_tables(db_session)
    assert before_snap["sources"] == []

    commit_calls = {"count": 0}
    flush_calls = {"count": 0}
    orig_commit = Session.commit
    orig_flush = Session.flush

    def tracked_commit(self, *args, **kwargs):
        commit_calls["count"] += 1
        return orig_commit(self, *args, **kwargs)

    def tracked_flush(self, *args, **kwargs):
        flush_calls["count"] += 1
        return orig_flush(self, *args, **kwargs)

    # 1. Chamadas diretas de serviço GET nunca fazem commit/flush
    monkeypatch.setattr(Session, "commit", tracked_commit)
    monkeypatch.setattr(Session, "flush", tracked_flush)

    sources_empty = list_public_sources(db_session)
    assert sources_empty == []
    opps_empty = list_opportunities(db_session, user)
    assert opps_empty.total == 0
    assert commit_calls["count"] == 0
    assert flush_calls["count"] == 0

    # 2. Rotas HTTP GET /sources e GET /opportunities nunca gravam nem comitam
    monkeypatch.undo()
    client = make_client(("10.20.0.3", 50000))
    _login_and_get_csrf(client, "dx021.f11@example.com", "StrongPassword123!")

    commit_calls["count"] = 0
    flush_calls["count"] = 0
    monkeypatch.setattr(Session, "commit", tracked_commit)
    monkeypatch.setattr(Session, "flush", tracked_flush)

    resp_sources = client.get("/api/v1/opportunities/sources")
    assert resp_sources.status_code == 200
    assert resp_sources.json() == []

    resp_opps = client.get("/api/v1/opportunities")
    assert resp_opps.status_code == 200
    assert resp_opps.json()["total"] == 0

    assert commit_calls["count"] == 0
    assert flush_calls["count"] == 0
    monkeypatch.undo()

    after_snap = _snapshot_opportunity_tables(db_session)
    assert after_snap == before_snap

    # 3. Inicialização explícita via CLI `init-sources` é idempotente e mantém Remotive desabilitada
    TestSession = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr("app.cli.SessionLocal", TestSession)
    assert cli_main(["init-sources"]) == 0
    assert cli_main(["init-sources"]) == 0  # idempotência

    sources_after = {s["slug"]: s for s in client.get("/api/v1/opportunities/sources").json()}
    assert set(sources_after.keys()) == {
        "remote_ok",
        "jobicy",
        "himalayas",
        "github_backend_br",
        "github_frontend_br",
        "remotive",
    }
    assert sources_after["remotive"]["enabled"] is False

    # 4. Concorrência multiworker em ensure_default_sources (2 threads sincronizadas)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def _worker():
        sess = TestSession()
        try:
            barrier.wait()
            ensure_default_sources(sess)
        except Exception as exc:
            errors.append(exc)
        finally:
            sess.close()

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert errors == []


def test_dx021_dry_run_performs_zero_persistent_writes(
    db_engine, db_session: Session, monkeypatch, capsys
):
    # 1. Sem fontes inicializadas: erro claro solicitando init-sources e zero escrita
    with pytest.raises(ValueError, match="init-sources"):
        sync_sources(db_session, dry_run=True)
    assert _snapshot_opportunity_tables(db_session)["sources"] == []

    # 2. Inicializa fontes explicitamente
    ensure_default_sources(db_session)
    snap_before = _snapshot_opportunity_tables(db_session)

    # Intercepta commit, flush e add para provar zero escrita no dry-run
    writes = {"commit": 0, "flush": 0, "add": 0}
    orig_commit = Session.commit
    orig_flush = Session.flush
    orig_add = Session.add

    def _forbid_commit(self, *a, **kw):
        writes["commit"] += 1
        return orig_commit(self, *a, **kw)

    def _forbid_flush(self, *a, **kw):
        writes["flush"] += 1
        return orig_flush(self, *a, **kw)

    def _forbid_add(self, *a, **kw):
        writes["add"] += 1
        return orig_add(self, *a, **kw)

    monkeypatch.setattr(Session, "commit", _forbid_commit)
    monkeypatch.setattr(Session, "flush", _forbid_flush)
    monkeypatch.setattr(Session, "add", _forbid_add)

    mock_remote_ok = RemoteOKConnector(
        tags=("dev",),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json=[
                    {"legal": "Remote OK"},
                    {
                        "id": "dry-1",
                        "position": "Junior Python Developer",
                        "company": "DryCo",
                        "tags": ["python"],
                        "location": "Worldwide",
                        "url": "https://remoteok.com/remote-jobs/dry-1",
                    },
                ],
            )
        ),
        sleep_fn=lambda _: None,
    )
    mock_failing_jobicy = JobicyConnector(
        industries=("engineering",),
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
        max_retries=0,
        sleep_fn=lambda _: None,
    )

    # Dry-run de fonte específica
    res_single = sync_sources(
        db_session,
        source_slug="remote_ok",
        dry_run=True,
        connector_overrides={"remote_ok": mock_remote_ok},
    )
    assert len(res_single) == 1
    assert res_single[0].status == SyncRunStatus.DRY_RUN.value
    assert res_single[0].valid_count == 1
    assert res_single[0].inserted_count == 0

    # Dry-run de todas as fontes habilitadas (incluindo falha simulada de uma fonte)
    res_all = sync_sources(
        db_session,
        dry_run=True,
        connector_overrides={
            "remote_ok": mock_remote_ok,
            "jobicy": mock_failing_jobicy,
        },
    )
    by_slug = {r.source_slug: r for r in res_all}
    assert by_slug["remote_ok"].status == SyncRunStatus.DRY_RUN.value
    assert by_slug["jobicy"].status == SyncRunStatus.FAILED.value

    assert writes == {"commit": 0, "flush": 0, "add": 0}
    monkeypatch.undo()

    snap_after = _snapshot_opportunity_tables(db_session)
    assert snap_after == snap_before

    # Também testa CLI dry-run sem alterar tabelas
    TestSession = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr("app.cli.SessionLocal", TestSession)

    class _MockROK(RemoteOKConnector):
        def __init__(self):
            super().__init__(
                tags=("dev",),
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        200,
                        json=[
                            {"legal": "Remote OK"},
                            {
                                "id": "dry-cli-1",
                                "position": "Junior Python Dev",
                                "company": "CliCo",
                                "tags": ["python"],
                                "location": "Worldwide",
                                "url": "https://remoteok.com/remote-jobs/dry-cli-1",
                            },
                        ],
                    )
                ),
                sleep_fn=lambda _: None,
            )

    monkeypatch.setattr(
        "app.services.opportunities.sync_service.CONNECTOR_CLASSES",
        {"remote_ok": _MockROK},
    )
    assert cli_main(["sync-opportunities", "--source", "remote_ok", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "[DRY_RUN] fonte=remote_ok" in out
    assert _snapshot_opportunity_tables(db_session) == snap_before


# ==============================================================================
# DX-02.2: Jobicy (`/api/jobs` + cursor + segmentos + `/api/jobs/status`)
# ==============================================================================


def test_dx022_jobicy_cursor_pagination_segments_dedup_throttling_and_status(db_session: Session):
    requested_urls: list[str] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested_urls.append(url)
        if "/api/jobs/status" in url:
            return httpx.Response(
                200,
                json={"statuses": {"201": "active", "202": "closed", "203": "unknown"}},
            )
        if "industry=engineering" in url and "cursor=" not in url:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 201,
                            "url": "https://jobicy.com/jobs/201-py",
                            "jobTitle": "Junior Python Engineer",
                            "companyName": "EngCo",
                            "jobIndustry": ["Engineering"],
                            "jobType": ["Contract"],
                            "jobGeo": "Anywhere",
                            "jobLevel": "Junior",
                            "jobDescription": "<p>Python APIs.</p>",
                        }
                    ],
                    "nextCursor": "cur-eng-2",
                    "hasMore": True,
                },
            )
        if "industry=engineering" in url and "cursor=cur-eng-2" in url:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        # ID 201 repetido deve ser deduplicado localmente
                        {
                            "id": 201,
                            "url": "https://jobicy.com/jobs/201-py",
                            "jobTitle": "Junior Python Engineer",
                            "companyName": "EngCo",
                            "jobIndustry": ["Engineering"],
                            "jobType": ["Contract"],
                            "jobGeo": "Anywhere",
                            "jobLevel": "Junior",
                        },
                        {
                            "id": 202,
                            "url": "https://jobicy.com/jobs/202-go",
                            "jobTitle": "Entry-Level Go Developer",
                            "companyName": "EngCo",
                            "jobIndustry": ["Engineering"],
                            "jobType": ["Full-Time"],
                            "jobGeo": "Brazil",
                            "jobLevel": "Entry-level",
                        },
                    ],
                    "nextCursor": "should-stop-because-hasMore-false",
                    "hasMore": False,
                },
            )
        if "industry=data-science" in url:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        # Repetido entre segmentos -> deduplicado
                        {
                            "id": 202,
                            "url": "https://jobicy.com/jobs/202-go",
                            "jobTitle": "Entry-Level Go Developer",
                            "companyName": "EngCo",
                            "jobIndustry": ["Data Science"],
                            "jobType": ["Full-Time"],
                            "jobGeo": "Brazil",
                            "jobLevel": "Entry-level",
                        },
                        {
                            "id": 203,
                            "url": "https://jobicy.com/jobs/203-data",
                            "jobTitle": "Junior Data Engineer",
                            "companyName": "DataCo",
                            "jobIndustry": ["Data Science"],
                            "jobType": ["Contract"],
                            "jobGeo": "LATAM",
                            "jobLevel": "Junior",
                        },
                    ],
                    "nextCursor": None,
                    "hasMore": False,
                },
            )
        return httpx.Response(200, json={"jobs": [], "nextCursor": None, "hasMore": False})

    conn = JobicyConnector(
        industries=("engineering", "data-science"),
        max_pages=5,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda s: sleeps.append(s),
    )
    drafts = conn.collect()
    assert [d.external_id for d in drafts] == ["201", "202", "203"]
    assert all(url.startswith("https://jobicy.com/api/jobs?") for url in requested_urls)
    assert "count=100" in requested_urls[0]
    assert len(requested_urls) == 3
    # Pausa mínima >= 1.0s entre páginas/segmentos
    assert len(sleeps) == 2
    assert all(s >= 1.0 for s in sleeps)

    # Teto máximo de páginas (max_pages=1 interrompe mesmo com hasMore=True)
    capped = JobicyConnector(
        industries=("engineering", "data-science"),
        max_pages=1,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    capped_drafts = capped.collect()
    assert [d.external_id for d in capped_drafts] == ["201"]

    # Endpoint de status em lote: 201 active, 202 closed, 203 unknown (conservador -> sem sinal de fechamento)
    signals = conn.check_publications_status_batch(
        [
            ("201", "https://jobicy.com/jobs/201-py", None),
            ("202", "https://jobicy.com/jobs/202-go", None),
            ("203", "https://jobicy.com/jobs/203-data", None),
        ]
    )
    assert signals["201"].status == ExternalSourceStatus.ACTIVE.value
    assert signals["202"].status == ExternalSourceStatus.CLOSED.value
    assert "203" not in signals

    # Resposta vazia, payload inválido, 429, timeout e limite de bytes
    empty_conn = JobicyConnector(
        industries=("engineering",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"jobs": [], "hasMore": False})),
        sleep_fn=lambda _: None,
    )
    assert empty_conn.collect() == []

    bad_conn = JobicyConnector(
        industries=("engineering",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"unexpected": True})),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ConnectorPayloadError):
        bad_conn.collect()

    def timeout_handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout simulado")

    timeout_conn = JobicyConnector(
        industries=("engineering",),
        max_retries=0,
        transport=httpx.MockTransport(timeout_handler),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ConnectorFetchError):
        timeout_conn.collect()

    oversized_conn = JobicyConnector(
        industries=("engineering",),
        max_response_bytes=64,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b'{"jobs":[' + b"x" * 200 + b"]}")),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ConnectorFetchError):
        oversized_conn.collect()

    # Integração com sync_sources: vaga que sai do feed só fecha quando /api/jobs/status confirma closed
    ensure_default_sources(db_session)
    sync_sources(db_session, source_slug="jobicy", force=True, connector_overrides={"jobicy": conn})

    # Segunda sincronização onde 202 e 203 sumiram do feed: /api/jobs/status confirma 202 closed e 203 unknown (fica active)
    def second_sync_handler(request: httpx.Request) -> httpx.Response:
        if "/api/jobs/status" in str(request.url):
            return httpx.Response(200, json={"statuses": {"202": "closed", "203": "unknown"}})
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 201,
                        "url": "https://jobicy.com/jobs/201-py",
                        "jobTitle": "Junior Python Engineer",
                        "companyName": "EngCo",
                        "jobIndustry": ["Engineering"],
                        "jobType": ["Contract"],
                        "jobGeo": "Anywhere",
                        "jobLevel": "Junior",
                    }
                ],
                "hasMore": False,
            },
        )

    conn2 = JobicyConnector(
        industries=("engineering",),
        transport=httpx.MockTransport(second_sync_handler),
        sleep_fn=lambda _: None,
    )
    sync_sources(db_session, source_slug="jobicy", force=True, connector_overrides={"jobicy": conn2})
    db_session.expire_all()
    opp_202 = db_session.execute(select(Opportunity).where(Opportunity.external_id == "202")).scalar_one()
    opp_203 = db_session.execute(select(Opportunity).where(Opportunity.external_id == "203")).scalar_one()
    assert opp_202.source_status == ExternalSourceStatus.CLOSED.value
    assert opp_203.source_status == ExternalSourceStatus.ACTIVE.value


# ==============================================================================
# DX-02.2: Himalayas (`/jobs/api` + `/jobs/api/search` + API Key + Timezone)
# ==============================================================================


def test_dx022_himalayas_cursor_search_dedup_timezone_and_optional_api_key(
    db_session: Session, caplog
):
    future_epoch = int((datetime.now(UTC) + timedelta(days=20)).timestamp())
    expired_epoch = int((datetime.now(UTC) - timedelta(days=1)).timestamp())
    seen_requests: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen_requests.append((url, request.headers.get("Authorization")))
        if "/jobs/api/search" in url:
            if "q=junior" in url:
                return httpx.Response(
                    200,
                    json={
                        "jobs": [
                            # Repetido do browse -> deduplicado
                            {
                                "guid": "https://himalayas.app/companies/c1/jobs/jr-py",
                                "title": "Junior Python Developer",
                                "companyName": "C1",
                                "employmentType": "Contractor",
                                "seniority": ["Junior"],
                                "locationRestrictions": ["Brazil"],
                                "timezoneRestrictions": [-3, -4],
                                "categories": ["Python"],
                                "expiryDate": future_epoch,
                                "applicationLink": "https://himalayas.app/companies/c1/jobs/jr-py?utm_source=api",
                            },
                            # Novo vindo da busca segmentada (timezone compatível mas país restrito a USA!)
                            {
                                "guid": "https://himalayas.app/companies/c2/jobs/us-only-tz",
                                "title": "Junior Backend Developer",
                                "companyName": "C2",
                                "employmentType": "Contractor",
                                "seniority": ["Junior"],
                                "locationRestrictions": ["United States"],
                                "timezoneRestrictions": [-5, -4, -3],
                                "categories": ["Python"],
                                "expiryDate": future_epoch,
                                "applicationLink": "https://apply.c2.example/us-only",
                            },
                        ]
                    },
                )
            return httpx.Response(200, json={"jobs": []})

        # Browse /jobs/api paginado por cursor
        if "cursor=" not in url:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "guid": "https://himalayas.app/companies/c1/jobs/jr-py",
                            "title": "Junior Python Developer",
                            "companyName": "C1",
                            "employmentType": "Contractor",
                            "seniority": ["Junior"],
                            "locationRestrictions": ["Brazil"],
                            "timezoneRestrictions": [-3, -4],
                            "categories": ["Python"],
                            "expiryDate": future_epoch,
                            "applicationLink": "https://himalayas.app/companies/c1/jobs/jr-py?utm_source=api",
                        },
                        {
                            "guid": "https://himalayas.app/companies/old/jobs/exp-1",
                            "title": "Expired Junior Dev",
                            "companyName": "Old",
                            "employmentType": "Contractor",
                            "seniority": ["Junior"],
                            "locationRestrictions": [],
                            "expiryDate": expired_epoch,
                        },
                    ],
                    "nextCursor": "him-cur-2",
                },
            )
        if "cursor=him-cur-2" in url:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "guid": "https://himalayas.app/companies/c3/jobs/apac-tz",
                            "title": "Entry-Level Python Engineer",
                            "companyName": "C3",
                            "employmentType": "Contractor",
                            "seniority": ["Entry-level"],
                            "locationRestrictions": [],
                            "timezoneRestrictions": [8, 9, 10],
                            "categories": ["Python"],
                            "expiryDate": future_epoch,
                            "applicationLink": "https://apply.c3.example/apac",
                        }
                    ],
                    "nextCursor": None,
                },
            )
        return httpx.Response(200, json={"jobs": [], "nextCursor": None})

    # Confirma cobertura mínima dos 10 conceitos no default
    for required_term in (
        "software developer",
        "intern",
        "internship",
        "entry-level",
        "junior",
        "backend",
        "frontend",
        "data",
        "artificial intelligence",
        "qa",
    ):
        assert required_term in DEFAULT_HIMALAYAS_SEARCH_QUERIES

    # 1. Sem API key: nenhum header Authorization
    conn_no_key = HimalayasConnector(
        api_key="",
        max_pages=3,
        search_queries=("junior", "backend"),
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    drafts = conn_no_key.collect()
    assert len(drafts) == 3
    assert all(auth is None for _, auth in seen_requests)
    by_id = {d.external_id: d for d in drafts}
    assert by_id["c1/jobs/jr-py"].application_url == "https://himalayas.app/companies/c1/jobs/jr-py?utm_source=api"
    assert by_id["c1/jobs/jr-py"].raw_metadata["timezone_restrictions"] == [-3, -4]
    assert conn_no_key.last_batch.rejected_count == 1
    assert len(conn_no_key.last_batch.lifecycle_signals) == 1

    # 2. Com API key: envia Bearer token, nunca vaza em logs, erros ou raw_metadata
    secret_key = "him_secret_test_key_987654321"
    seen_requests.clear()
    with caplog.at_level(logging.DEBUG):
        conn_with_key = HimalayasConnector(
            api_key=secret_key,
            max_pages=1,
            search_queries=(),
            transport=httpx.MockTransport(handler),
            sleep_fn=lambda _: None,
        )
        drafts_key = conn_with_key.collect()
    assert len(seen_requests) == 1
    assert seen_requests[0][1] == f"Bearer {secret_key}"
    assert secret_key not in caplog.text
    for d in drafts_key:
        assert secret_key not in str(d.raw_metadata)

    # 3. Erro 429 com API key NÃO expõe a chave na mensagem da exceção
    err_conn = HimalayasConnector(
        api_key=secret_key,
        max_retries=0,
        search_queries=(),
        transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "4"})),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ConnectorFetchError) as exc_info:
        err_conn.collect()
    assert secret_key not in str(exc_info.value)

    # 4. Interpretação de timezone no matching:
    # - Brazil + timezone [-3, -4] -> elegível
    # - United States + timezone [-5, -4, -3] -> EXCLUÍDO (timezone nunca substitui autorização legal de país!)
    # - Worldwide + timezone [8, 9, 10] (APAC) -> EXCLUÍDO por fuso incompatível com Brasil
    user = create_user_account(
        db_session,
        email="dx022.tz@example.com",
        display_name="TZ User",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile = get_or_create_profile(db_session, user)
    profile.country = "Brasil"
    db_session.commit()

    def _to_opp(d) -> Opportunity:
        now = datetime.now(UTC)
        return Opportunity(
            external_id=d.external_id,
            title=d.title,
            description=d.description,
            opportunity_type=d.opportunity_type,
            seniority_level=d.seniority_level,
            employment_type=d.employment_type,
            work_mode=d.work_mode,
            professional_area=d.professional_area,
            secondary_areas=d.secondary_areas,
            country=d.country,
            eligible_countries=d.eligible_countries,
            eligibility_unknown=d.eligibility_unknown,
            technologies=d.technologies,
            source_url=d.source_url,
            first_seen_at=now,
            last_seen_at=now,
            content_hash=f"h-{d.external_id}",
            raw_metadata=d.raw_metadata,
        )

    ev_br_tz = evaluate_opportunity_for_user(_to_opp(by_id["c1/jobs/jr-py"]), profile)
    assert ev_br_tz.geographic_eligibility == "eligible"
    assert any("fuso" in r.lower() for r in ev_br_tz.inclusion_reasons)

    ev_us_tz = evaluate_opportunity_for_user(_to_opp(by_id["c2/jobs/us-only-tz"]), profile)
    assert ev_us_tz.geographic_eligibility == "excluded"
    assert ev_us_tz.eligible is False

    ev_apac_tz = evaluate_opportunity_for_user(_to_opp(by_id["c3/jobs/apac-tz"]), profile)
    assert ev_apac_tz.geographic_eligibility == "excluded"
    assert ev_apac_tz.eligible is False


# ==============================================================================
# DX-02.2: Remote OK (tags segmentadas + deduplicação + limite de consultas)
# ==============================================================================


def test_dx022_remote_ok_tech_tags_dedup_limit_and_fallback():
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        if "tag=dev" in url:
            return httpx.Response(
                200,
                json=[
                    {"legal": "Remote OK attribution"},
                    {
                        "id": "rk-1",
                        "position": "Junior Python Developer",
                        "company": "PyCo",
                        "tags": ["dev", "python"],
                        "location": "Worldwide",
                        "url": "https://remoteok.com/remote-jobs/rk-1",
                    },
                    {
                        "id": "rk-non-tech",
                        "position": "Customer Support Representative",
                        "company": "HelpCo",
                        "tags": ["dev", "support"],
                        "location": "Worldwide",
                        "url": "https://remoteok.com/remote-jobs/rk-non-tech",
                    },
                ],
            )
        if "tag=python" in url:
            return httpx.Response(
                200,
                json=[
                    {"legal": "Remote OK attribution"},
                    # Repetido de tag=dev -> deduplicado
                    {
                        "id": "rk-1",
                        "position": "Junior Python Developer",
                        "company": "PyCo",
                        "tags": ["dev", "python"],
                        "location": "Worldwide",
                        "url": "https://remoteok.com/remote-jobs/rk-1",
                    },
                    {
                        "id": "rk-2",
                        "position": "Junior Data Engineer",
                        "company": "DataCo",
                        "tags": ["python", "data"],
                        "location": "LATAM",
                        "url": "https://remoteok.com/remote-jobs/rk-2",
                    },
                ],
            )
        return httpx.Response(200, json=[{"legal": "Remote OK"}])

    conn = RemoteOKConnector(
        tags=("dev", "python", "react", "java"),
        max_queries=2,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    drafts = conn.collect()
    # Respeita max_queries=2 (consulta somente dev e python)
    assert requested == [
        "https://remoteok.com/api?tag=dev",
        "https://remoteok.com/api?tag=python",
    ]
    assert [d.external_id for d in drafts] == ["rk-1", "rk-non-tech", "rk-2"]
    # Classificação global não é distorcida: vaga de suporte continua customer_support!
    by_id = {d.external_id: d for d in drafts}
    assert by_id["rk-non-tech"].professional_area == ProfessionalArea.CUSTOMER_SUPPORT.value
    assert by_id["rk-1"].source_url == "https://remoteok.com/remote-jobs/rk-1"

    # Ausência de tags faz fallback limpo para endpoint base
    requested.clear()
    conn_no_tags = RemoteOKConnector(
        tags=(),
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    conn_no_tags.collect()
    assert requested == ["https://remoteok.com/api"]

    # Payload inválido lança ConnectorPayloadError
    bad_conn = RemoteOKConnector(
        tags=("dev",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"not": "a list"})),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ConnectorPayloadError):
        bad_conn.collect()


# ==============================================================================
# DX-02.2: GitHub Vagas BR (`per_page=100` + `Link` + `GITHUB_TOKEN` + 403/429)
# ==============================================================================


def test_dx022_github_vagas_pagination_link_header_token_and_rate_limit(caplog):
    assert "per_page=100" in GitHubBackendBRConnector.definition.base_url
    assert "per_page=100" in GitHubFrontendBRConnector.definition.base_url

    # Validação anti-SSRF de parse_github_next_link
    assert (
        parse_github_next_link(
            '<https://api.github.com/repos/backend-br/vagas/issues?state=open&per_page=100&page=2>; rel="next", '
            '<https://api.github.com/repos/backend-br/vagas/issues?state=open&per_page=100&page=5>; rel="last"'
        )
        == "https://api.github.com/repos/backend-br/vagas/issues?state=open&per_page=100&page=2"
    )
    assert parse_github_next_link('<https://evil.example.com/issues?page=2>; rel="next"') is None
    assert parse_github_next_link('<http://127.0.0.1/issues?page=2>; rel="next"') is None
    assert parse_github_next_link('<https://api.github.com/repos/backend-br/vagas/issues?page=1>; rel="prev"') is None

    seen_calls: list[tuple[str, str | None]] = []

    def paginated_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen_calls.append((url, request.headers.get("Authorization")))
        if "page=2" in url:
            return httpx.Response(
                200,
                headers={
                    "Link": '<https://api.github.com/repos/backend-br/vagas/issues?state=open&per_page=100&page=3>; rel="next"'
                },
                json=[
                    # Issue 101 repetida entre páginas -> deduplicada
                    {
                        "number": 101,
                        "state": "open",
                        "title": "[Remoto] Dev Python Júnior na Empresa A",
                        "html_url": "https://github.com/backend-br/vagas/issues/101",
                        "created_at": "2026-11-15T10:00:00Z",
                        "labels": [{"name": "Júnior"}, {"name": "PJ"}, {"name": "Python"}],
                        "body": "Contato: rh@empresa.com ou (11) 99999-8888",
                    },
                    {
                        "number": 102,
                        "state": "open",
                        "title": "[Curitiba / São Paulo] Dev Java Júnior na Empresa B",
                        "html_url": "https://github.com/backend-br/vagas/issues/102",
                        "created_at": "2026-11-14T10:00:00Z",
                        "labels": [{"name": "Júnior"}, {"name": "Híbrido"}, {"name": "PJ"}, {"name": "Java"}],
                        "body": "Vaga híbrida em Curitiba ou São Paulo.",
                    },
                ],
            )
        if "page=3" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 103,
                        "state": "open",
                        "title": "[Remoto] Estágio Backend na Empresa C",
                        "html_url": "https://github.com/backend-br/vagas/issues/103",
                        "created_at": "2026-11-13T10:00:00Z",
                        "labels": [{"name": "Estágio"}, {"name": "Python"}],
                        "body": "Estágio remoto.",
                    }
                ],
            )
        # Página 1
        return httpx.Response(
            200,
            headers={
                "Link": '<https://api.github.com/repos/backend-br/vagas/issues?state=open&per_page=100&page=2>; rel="next"'
            },
            json=[
                {
                    "number": 101,
                    "state": "open",
                    "title": "[Remoto] Dev Python Júnior na Empresa A",
                    "html_url": "https://github.com/backend-br/vagas/issues/101",
                    "created_at": "2026-11-15T10:00:00Z",
                    "labels": [{"name": "Júnior"}, {"name": "PJ"}, {"name": "Python"}],
                    "body": "Contato: rh@empresa.com ou (11) 99999-8888",
                }
            ],
        )

    # 1. Sem token: percorre todas as 3 páginas, deduplica 101 e redige PII
    conn_no_tok = GitHubBackendBRConnector(
        github_token="",
        max_pages=5,
        transport=httpx.MockTransport(paginated_handler),
        sleep_fn=lambda _: None,
    )
    drafts = conn_no_tok.collect()
    assert len(seen_calls) == 3
    assert all(auth is None for _, auth in seen_calls)
    assert [d.external_id for d in drafts] == [
        "gh-backend-br-101",
        "gh-backend-br-102",
        "gh-backend-br-103",
    ]
    assert "rh@empresa.com" not in (drafts[0].description or "")
    assert "99999-8888" not in (drafts[0].description or "")
    assert drafts[1].raw_metadata["cities"] == ["Curitiba", "São Paulo"]

    # 2. Limite max_pages=2 interrompe na página 2
    seen_calls.clear()
    conn_capped = GitHubBackendBRConnector(
        github_token="",
        max_pages=2,
        transport=httpx.MockTransport(paginated_handler),
        sleep_fn=lambda _: None,
    )
    assert [d.external_id for d in conn_capped.collect()] == [
        "gh-backend-br-101",
        "gh-backend-br-102",
    ]
    assert len(seen_calls) == 2

    # 3. Com token: envia Authorization Bearer, nunca vaza em logs, raw_metadata ou exceções
    secret_pat = "github_pat_secret_readonly_123456"
    seen_calls.clear()
    with caplog.at_level(logging.DEBUG):
        conn_with_tok = GitHubBackendBRConnector(
            github_token=secret_pat,
            max_pages=1,
            transport=httpx.MockTransport(paginated_handler),
            sleep_fn=lambda _: None,
        )
        tok_drafts = conn_with_tok.collect()
    assert seen_calls[0][1] == f"Bearer {secret_pat}"
    assert secret_pat not in caplog.text
    for d in tok_drafts:
        assert secret_pat not in str(d.raw_metadata)

    # 4. Rate limit 403 com X-RateLimit-Remaining=0 e Retry-After + 429
    sleep_calls: list[float] = []
    attempts = {"n": 0}

    def rate_limit_handler(_: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(
                403,
                headers={"X-RateLimit-Remaining": "0", "Retry-After": "2"},
            )
        if attempts["n"] == 2:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json=[])

    conn_rl = GitHubBackendBRConnector(
        github_token=secret_pat,
        max_retries=2,
        transport=httpx.MockTransport(rate_limit_handler),
        sleep_fn=lambda s: sleep_calls.append(s),
    )
    assert conn_rl.collect() == []
    assert sleep_calls == [2.0, 3.0]

    # Erro 403 exaurido não expõe token
    conn_rl_fail = GitHubBackendBRConnector(
        github_token=secret_pat,
        max_retries=0,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(403, headers={"X-RateLimit-Remaining": "0", "Retry-After": "5"})
        ),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ConnectorFetchError) as exc_info:
        conn_rl_fail.collect()
    assert secret_pat not in str(exc_info.value)


# ==============================================================================
# Segurança e defaults operacionais (Seções 5 e 8.4)
# ==============================================================================


def test_dx02_security_defaults_and_disabled_sources_preserved():
    cfg = Settings(_env_file=None)
    assert cfg.ai_assisted_enabled is False
    assert cfg.ai_provider == "disabled"
    assert cfg.github_token == ""
    assert cfg.himalayas_api_key == ""
    assert RemotiveConnector.definition.enabled_by_default is False
