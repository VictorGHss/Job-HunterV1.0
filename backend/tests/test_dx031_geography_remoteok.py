"""
Testes de regressão DX-03.1:
- DX-03.1-A: Normalização canônica de países e eliminação do falso positivo por substring `br`
  (Brunei, British Columbia, Canada, etc.).
- DX-03.1-B: Interpretação conservadora de `Remote` / `Remote,` como não-país (`eligibility_unknown=True`)
  no Remote OK e no motor de matching.
- DX-03.1-C: Consistência de classificação no Remote OK (fixtures fiéis aos 3 registros inconsistentes:
  Frontend Engineer com tags conflitantes e Scrum Master com 3+ anos obrigatórios) e simulação
  `reclassify_opportunities(..., dry_run=True)` sem escrita persistente.
"""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from app.models.opportunity import (
    EmploymentType,
    ExperienceRequirementMode,
    ExternalSourceStatus,
    Opportunity,
    OpportunityType,
    ProfessionalArea,
    SeniorityLevel,
    WorkMode,
)
from app.models.profile import ProfessionalProfile, default_career_preferences
from app.services.opportunities.classification import (
    classify_opportunity,
    reconcile_structured_classification,
)
from app.services.opportunities.connectors.base import parse_geo_eligibility
from app.services.opportunities.connectors.remote_ok import RemoteOKConnector
from app.services.opportunities.matching import (
    classify_geographic_token,
    evaluate_opportunity_for_user,
    resolve_canonical_country,
)
from app.services.opportunities.sync_service import (
    ensure_default_sources,
    reclassify_opportunities,
)


def _make_brazil_profile(*, city: str = "Campinas", state: str = "SP") -> ProfessionalProfile:
    return ProfessionalProfile(
        full_name="Perfil Teste",
        professional_email="perfil@example.com",
        city=city,
        state=state,
        country="Brasil",
        preferences=default_career_preferences(),
    )


def _make_opp(
    *,
    title: str = "Junior Python Developer",
    description: str = "Build Python APIs.",
    opportunity_type: str = OpportunityType.JUNIOR.value,
    seniority_level: str = SeniorityLevel.JUNIOR.value,
    employment_type: str = EmploymentType.PJ.value,
    work_mode: str = WorkMode.REMOTE.value,
    professional_area: str = ProfessionalArea.BACKEND.value,
    location_text: str | None = None,
    country: str | None = None,
    city: str | None = None,
    state: str | None = None,
    eligible_countries: list[str] | None = None,
    eligibility_unknown: bool = False,
) -> Opportunity:
    now = datetime.now(UTC)
    return Opportunity(
        external_id="dx031-opp",
        title=title,
        company_name="Acme",
        description=description,
        opportunity_type=opportunity_type,
        seniority_level=seniority_level,
        employment_type=employment_type,
        work_mode=work_mode,
        professional_area=professional_area,
        location_text=location_text,
        country=country,
        city=city,
        state=state,
        eligible_countries=list(eligible_countries or []),
        eligibility_unknown=eligibility_unknown,
        technologies=["Python"],
        source_url="https://example.com/dx031",
        first_seen_at=now,
        last_seen_at=now,
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-dx031",
    )


# ==============================================================================
# DX-03.1-A: Normalização canônica de países e eliminação do falso positivo "br"
# ==============================================================================


@pytest.mark.parametrize(
    ("raw_value", "expected_canonical", "expected_kind"),
    [
        ("Brasil", "Brazil", "country"),
        ("Brazil", "Brazil", "country"),
        ("BR", "Brazil", "country"),
        ("br", "Brazil", "country"),
        ("Brunei", "Brunei", "country"),
        ("Brunei-Muara District", "Brunei", "country"),
        ("British Columbia, Canada", "Canada", "country"),
        ("British Columbia", None, "unknown"),
        ("Toronto, Canada", "Canada", "country"),
        ("São Paulo, Brasil", "Brazil", "country"),
        ("Remote", None, "non_country"),
        ("Remote,", None, "non_country"),
        ("Worldwide", "Worldwide", "worldwide"),
        ("LATAM", "LATAM", "region"),
    ],
)
def test_dx031_a_canonical_country_and_region_classification(
    raw_value: str, expected_canonical: str | None, expected_kind: str
):
    canonical, kind = classify_geographic_token(raw_value)
    assert (canonical, kind) == (expected_canonical, expected_kind)
    if expected_kind == "country":
        assert resolve_canonical_country(raw_value) == expected_canonical
    else:
        assert resolve_canonical_country(raw_value) is None


def test_dx031_a_brunei_and_british_columbia_never_match_brazil():
    profile = _make_brazil_profile()

    # Falso positivo real #1: The Flex (Brunei)
    opp_brunei = _make_opp(
        title="Founding Software Engineer",
        opportunity_type=OpportunityType.OTHER.value,
        seniority_level=SeniorityLevel.UNKNOWN.value,
        employment_type=EmploymentType.UNKNOWN.value,
        professional_area=ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
        location_text="Bandar Seri Begawan, Bandar Seri Begawan, Brunei-Muara District, Brunei",
        eligible_countries=[
            "Bandar Seri Begawan",
            "Bandar Seri Begawan",
            "Brunei-Muara District",
            "Brunei",
        ],
    )
    ev_brunei = evaluate_opportunity_for_user(opp_brunei, profile)
    assert ev_brunei.geographic_eligibility == "excluded"
    assert ev_brunei.eligible is False
    assert ev_brunei.overall_compatibility == "incompatible"

    # Falso positivo real #2: Acro Commerce (British Columbia, Canada)
    opp_bc = _make_opp(
        title="Front End Developer",
        opportunity_type=OpportunityType.OTHER.value,
        seniority_level=SeniorityLevel.UNKNOWN.value,
        employment_type=EmploymentType.UNKNOWN.value,
        professional_area=ProfessionalArea.FRONTEND.value,
        location_text="Kelowna, Kelowna, British Columbia, Canada",
        eligible_countries=["Kelowna", "Kelowna", "British Columbia", "Canada"],
    )
    ev_bc = evaluate_opportunity_for_user(opp_bc, profile)
    assert ev_bc.geographic_eligibility == "excluded"
    assert ev_bc.eligible is False
    assert ev_bc.overall_compatibility == "incompatible"

    # Bridgetown também nunca casa com Brasil
    opp_bridgetown = _make_opp(
        location_text="Bridgetown",
        eligible_countries=["Bridgetown"],
    )
    assert evaluate_opportunity_for_user(opp_bridgetown, profile).geographic_eligibility == "excluded"

    # Brasil / Brazil / BR isolado / São Paulo, Brasil / LATAM continuam elegíveis
    for ec in (["Brasil"], ["Brazil"], ["BR"], ["São Paulo, Brasil"], ["LATAM"], ["Worldwide"]):
        opp_ok = _make_opp(eligible_countries=ec)
        assert evaluate_opportunity_for_user(opp_ok, profile).geographic_eligibility == "eligible", ec

    # Conflito entre Worldwide e país restrito explícito não promove automaticamente para Brasil
    opp_conflict = _make_opp(eligible_countries=["Worldwide", "USA"])
    assert evaluate_opportunity_for_user(opp_conflict, profile).geographic_eligibility == "excluded"

    # Múltiplos países incluindo Brasil continuam elegíveis
    opp_multi = _make_opp(eligible_countries=["Argentina", "Brazil", "Colombia"])
    assert evaluate_opportunity_for_user(opp_multi, profile).geographic_eligibility == "eligible"

    # Regra de múltiplas cidades presenciais no Brasil permanece preservada
    opp_onsite_br = _make_opp(
        work_mode=WorkMode.ONSITE.value,
        country="Brasil",
        city="Belo Horizonte / São Paulo",
        location_text="Belo Horizonte ou São Paulo, Brasil",
        eligible_countries=["Brasil"],
    )
    assert evaluate_opportunity_for_user(opp_onsite_br, profile).geographic_eligibility == "excluded"
    profile_bh = _make_brazil_profile(city="Belo Horizonte", state="MG")
    assert evaluate_opportunity_for_user(opp_onsite_br, profile_bh).geographic_eligibility == "eligible"


# ==============================================================================
# DX-03.1-B: Interpretação conservadora de "Remote" / "Remote,"
# ==============================================================================


def test_dx031_b_parse_geo_eligibility_and_matching_for_remote():
    # "Remote" e "Remote," sem país -> eligible_countries=[], eligibility_unknown=True
    assert parse_geo_eligibility("Remote") == ([], None, True)
    assert parse_geo_eligibility("Remote,") == ([], None, True)
    assert parse_geo_eligibility("  Remote ; ") == ([], None, True)

    # "Remote, USA" -> preserva restrição explícita de país sem "Remote"
    assert parse_geo_eligibility("Remote, USA") == (["USA"], "USA", False)
    assert parse_geo_eligibility("Remote, EST United States") == (
        ["EST United States"],
        "EST United States",
        False,
    )

    # "Brazil, Remote" -> preserva Brazil sem "Remote"
    assert parse_geo_eligibility("Brazil, Remote") == (["Brazil"], "Brazil", False)

    # "Worldwide" -> região global explícita
    assert parse_geo_eligibility("Worldwide") == (["Worldwide"], None, False)
    assert parse_geo_eligibility("Remote, Worldwide") == (["Worldwide"], None, False)

    # País desconhecido (vazio) -> eligibility_unknown=True
    assert parse_geo_eligibility("") == ([], None, True)
    assert parse_geo_eligibility(None) == ([], None, True)

    profile = _make_brazil_profile()

    # Registro legado com eligible_countries=["Remote"] não é excluído nem vira Brasil
    opp_legacy_remote = _make_opp(
        title="Junior Python Developer",
        location_text="Remote,",
        eligible_countries=["Remote"],
        eligibility_unknown=False,
    )
    ev_legacy = evaluate_opportunity_for_user(opp_legacy_remote, profile)
    assert ev_legacy.geographic_eligibility == "unknown"
    assert ev_legacy.eligible is True
    assert ev_legacy.overall_compatibility == "potential"
    assert any("Elegibilidade geográfica" in n for n in ev_legacy.uncertainty_notes)

    # "Remote, USA" permanece excluída para perfil no Brasil
    ec_usa, c_usa, unk_usa = parse_geo_eligibility("Remote, USA")
    opp_remote_usa = _make_opp(
        location_text="Remote, USA",
        country=c_usa,
        eligible_countries=ec_usa,
        eligibility_unknown=unk_usa,
    )
    ev_usa = evaluate_opportunity_for_user(opp_remote_usa, profile)
    assert ev_usa.geographic_eligibility == "excluded"
    assert ev_usa.eligible is False

    # ["Brazil", "Remote"] permanece elegível para Brasil
    opp_br_remote = _make_opp(
        location_text="Brazil, Remote",
        eligible_countries=["Brazil", "Remote"],
        eligibility_unknown=False,
    )
    ev_br = evaluate_opportunity_for_user(opp_br_remote, profile)
    assert ev_br.geographic_eligibility == "eligible"

    # RemoteOKConnector preserva location_text="Remote," e work_mode="remote",
    # mas não persiste "Remote" em eligible_countries
    conn = RemoteOKConnector(
        tags=("dev",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    drafts = conn.parse_payload(
        [
            {"legal": "Remote OK API"},
            {
                "id": 1134925,
                "position": "Junior Python Developer",
                "company": "RemoteCo",
                "location": "Remote,",
                "tags": ["dev", "python", "junior"],
                "url": "https://remoteok.com/remote-jobs/1134925",
                "description": "<p>Build Python APIs.</p>",
            },
        ]
    )
    assert len(drafts) == 1
    assert drafts[0].work_mode == WorkMode.REMOTE.value
    assert drafts[0].location_text == "Remote,"
    assert drafts[0].eligible_countries == []
    assert drafts[0].country is None
    assert drafts[0].eligibility_unknown is True


# ==============================================================================
# DX-03.1-C: Consistência de classificação no Remote OK e reclassify --dry-run
# ==============================================================================


def test_dx031_c_remote_ok_inconsistent_records_and_precedence():
    conn = RemoteOKConnector(
        tags=("dev",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    payload = [
        {"legal": "Remote OK API"},
        # Fixture 1 (fiel a external_id=1136165 / 1133416):
        # Frontend Engineer com tags conflitantes ("senior", "exec", "internship")
        {
            "id": 1136165,
            "position": "Frontend Engineer",
            "company": "GamingPlatform",
            "location": "Greater Toronto Area,",
            "tags": [
                "front end",
                "react",
                "typescript",
                "exec",
                "senior",
                "internship",
                "digital nomad",
            ],
            "url": "https://remoteok.com/remote-jobs/1136165",
            "description": (
                "<p>Location: Toronto, ON, Canada | Team: Frontend | Level: Post Grad</p>"
                "<p>We are looking for a Post Grad Frontend Engineer with strong fundamentals in React and TypeScript.</p>"
            ),
        },
        # Fixture 2 (fiel a external_id=1133092):
        # Scrum Master com experiência obrigatória de 3+ anos e tags ruidosas ("exec", "junior", "internship")
        {
            "id": 1133092,
            "position": "Scrum Master",
            "company": "DeliveryCo",
            "location": "Malibu, California, United States",
            "tags": ["exec", "junior", "internship", "admin", "analyst"],
            "url": "https://remoteok.com/remote-jobs/1133092",
            "description": (
                "<p>Facilitates Agile delivery for assigned development teams.</p>"
                "<p>Requirements: 3+ years of experience as a Scrum Master required.</p>"
            ),
        },
        # Fixture 3: Frontend Engineer explicitamente confirmado como estágio (sem conflito)
        {
            "id": 999001,
            "position": "Frontend Engineer Intern",
            "company": "CampusTech",
            "location": "Remote,",
            "tags": ["front end", "react", "internship"],
            "url": "https://remoteok.com/remote-jobs/999001",
            "description": "<p>Software engineering internship working with React and TypeScript.</p>",
        },
        # Fixture 4: Frontend Engineer com tag internship limpa e sem conflito de senioridade/anos
        {
            "id": 999002,
            "position": "Frontend Engineer",
            "company": "CleanInternCo",
            "location": "Brazil",
            "tags": ["front end", "react", "internship"],
            "url": "https://remoteok.com/remote-jobs/999002",
            "description": "<p>Work with React and TypeScript components.</p>",
        },
        # Fixture 5: Senioridade já confirmada no título (Senior) não é rebaixada por tag internship
        {
            "id": 999003,
            "position": "Senior Frontend Engineer",
            "company": "SeniorCo",
            "location": "Worldwide",
            "tags": ["front end", "react", "internship", "junior"],
            "url": "https://remoteok.com/remote-jobs/999003",
            "description": "<p>Lead frontend architecture.</p>",
        },
    ]

    drafts = {d.external_id: d for d in conn.parse_payload(payload)}

    # 1. Frontend Engineer com tags conflitantes -> other / unknown (coerente, sem estágio falso)
    fe_conflict = drafts["1136165"]
    assert fe_conflict.opportunity_type == OpportunityType.OTHER.value
    assert fe_conflict.seniority_level == SeniorityLevel.UNKNOWN.value
    assert fe_conflict.employment_type == EmploymentType.UNKNOWN.value

    # 2. Scrum Master com 3+ anos obrigatórios -> other / unknown, preserva 3+ anos obrigatórios
    sm = drafts["1133092"]
    assert sm.opportunity_type == OpportunityType.OTHER.value
    assert sm.seniority_level == SeniorityLevel.UNKNOWN.value
    assert sm.experience_requirement_mode == ExperienceRequirementMode.REQUIRED.value
    assert sm.experience_min_years == 3

    # 3. Estágio explícito no título -> internship nos 3 campos
    fe_intern = drafts["999001"]
    assert fe_intern.opportunity_type == OpportunityType.INTERNSHIP.value
    assert fe_intern.employment_type == EmploymentType.INTERNSHIP.value
    assert fe_intern.seniority_level == SeniorityLevel.INTERNSHIP.value

    # 4. Tag internship sem conflito -> coerente nos 3 campos
    fe_clean_tag = drafts["999002"]
    assert fe_clean_tag.opportunity_type == OpportunityType.INTERNSHIP.value
    assert fe_clean_tag.employment_type == EmploymentType.INTERNSHIP.value
    assert fe_clean_tag.seniority_level == SeniorityLevel.INTERNSHIP.value

    # 5. Senior no título nunca é rebaixado
    fe_senior = drafts["999003"]
    assert fe_senior.opportunity_type == OpportunityType.OTHER.value
    assert fe_senior.seniority_level == SeniorityLevel.SENIOR.value

    # Garantia direta em reconcile_structured_classification com 3+ anos obrigatórios
    dec_exp = classify_opportunity(
        title="Scrum Master",
        description="Requirements: 3+ years of experience required.",
    )
    assert reconcile_structured_classification(dec_exp, metadata_levels=["internship"]) == (
        OpportunityType.OTHER.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.UNKNOWN.value,
    )


def test_dx031_reclassify_opportunities_dry_run_and_apply_on_remote_ok_fixtures(
    db_session: Session,
):
    src = {s.slug: s for s in ensure_default_sources(db_session)}["remote_ok"]
    now = datetime.now(UTC)

    opp_fe = Opportunity(
        source_id=src.id,
        external_id="1136165",
        title="Frontend Engineer",
        company_name="GamingPlatform",
        description="Location: Toronto, ON, Canada | Level: Post Grad. React and TypeScript.",
        opportunity_type=OpportunityType.INTERNSHIP.value,
        seniority_level=SeniorityLevel.UNKNOWN.value,
        employment_type=EmploymentType.INTERNSHIP.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.FRONTEND.value,
        location_text="Greater Toronto Area,",
        eligible_countries=["Greater Toronto Area"],
        eligibility_unknown=False,
        technologies=["front end", "react", "typescript", "exec", "senior", "internship"],
        source_url="https://remoteok.com/remote-jobs/1136165",
        first_seen_at=now,
        last_seen_at=now,
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-fe-1136165",
        raw_metadata={"source": "remote_ok"},
    )
    opp_sm = Opportunity(
        source_id=src.id,
        external_id="1133092",
        title="Scrum Master",
        company_name="DeliveryCo",
        description="Requirements: 3+ years of experience required.",
        opportunity_type=OpportunityType.OTHER.value,
        seniority_level=SeniorityLevel.INTERNSHIP.value,
        employment_type=EmploymentType.UNKNOWN.value,
        experience_requirement_mode=ExperienceRequirementMode.REQUIRED.value,
        experience_min_years=3,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.UNKNOWN.value,
        location_text="Malibu, California, United States",
        eligible_countries=["Malibu", "California", "United States"],
        eligibility_unknown=False,
        technologies=["exec", "junior", "internship", "admin"],
        source_url="https://remoteok.com/remote-jobs/1133092",
        first_seen_at=now,
        last_seen_at=now,
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-sm-1133092",
        raw_metadata={"source": "remote_ok"},
    )
    opp_remote_only = Opportunity(
        source_id=src.id,
        external_id="1134925",
        title="Junior Python Developer",
        company_name="RemoteCo",
        description="Build Python FastAPI services.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.UNKNOWN.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        location_text="Remote,",
        country="Remote",
        eligible_countries=["Remote"],
        eligibility_unknown=False,
        technologies=["python", "backend", "junior"],
        source_url="https://remoteok.com/remote-jobs/1134925",
        first_seen_at=now,
        last_seen_at=now,
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-rem-1134925",
        raw_metadata={"source": "remote_ok"},
    )
    db_session.add_all([opp_fe, opp_sm, opp_remote_only])
    db_session.commit()

    # 1. Dry-run detecta todas as 3 correções sem modificar o banco
    dry_report = reclassify_opportunities(db_session, source_slug="remote_ok", dry_run=True)
    assert dry_report.evaluated_count == 3
    assert dry_report.updated_count == 3
    db_session.expire_all()
    assert db_session.get(Opportunity, opp_fe.id).opportunity_type == OpportunityType.INTERNSHIP.value
    assert db_session.get(Opportunity, opp_sm.id).seniority_level == SeniorityLevel.INTERNSHIP.value
    assert db_session.get(Opportunity, opp_remote_only.id).eligible_countries == ["Remote"]

    # 2. Execução real no SQLite temporário corrige classificação e geografia "Remote"
    apply_report = reclassify_opportunities(db_session, source_slug="remote_ok", dry_run=False)
    assert apply_report.updated_count == 3
    db_session.expire_all()

    fe_fixed = db_session.get(Opportunity, opp_fe.id)
    sm_fixed = db_session.get(Opportunity, opp_sm.id)
    rem_fixed = db_session.get(Opportunity, opp_remote_only.id)

    assert fe_fixed.opportunity_type == OpportunityType.OTHER.value
    assert fe_fixed.seniority_level == SeniorityLevel.UNKNOWN.value
    assert fe_fixed.employment_type == EmploymentType.UNKNOWN.value

    assert sm_fixed.opportunity_type == OpportunityType.OTHER.value
    assert sm_fixed.seniority_level == SeniorityLevel.UNKNOWN.value
    assert sm_fixed.experience_requirement_mode == ExperienceRequirementMode.REQUIRED.value
    assert sm_fixed.experience_min_years == 3

    assert rem_fixed.eligible_countries == []
    assert rem_fixed.country is None
    assert rem_fixed.eligibility_unknown is True
    assert rem_fixed.location_text == "Remote,"
