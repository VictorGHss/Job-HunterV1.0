"""
Testes de regressão DX-03.1.3 — Conflitos de senioridade em tags/metadados:
Garante simetria entre as regras de estágio, júnior e entry-level quando
tags/metadados contêm simultaneamente sinais de entrada e sinais superiores
conflitantes (`_STRUCTURED_UPPER_TOKENS`), preservando precedência textual
explícita, requisitos de experiência, geografia e comportamento de outras fontes.
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
from app.services.opportunities.classification import (
    classify_opportunity,
    reconcile_structured_classification,
)
from app.services.opportunities.connectors.github_vagas import GitHubBackendBRConnector
from app.services.opportunities.connectors.himalayas import HimalayasConnector
from app.services.opportunities.connectors.remote_ok import RemoteOKConnector
from app.services.opportunities.sync_service import (
    ensure_default_sources,
    reclassify_opportunities,
)

_SPAM_REMOTE_OK_TAGS = [
    "design",
    "sys admin",
    "vfx",
    "designer",
    "marketing",
    "exec",
    "web dev",
    "video",
    "cloud",
    "content writing",
    "medical",
    "digital nomad",
    "customer support",
    "testing",
    "ops",
    "recruiter",
    "junior",
    "hr",
    "education",
    "finance",
    "internship",
    "admin",
    "analyst",
]


# ==============================================================================
# Cenários negativos (1 a 7): sinais conflitantes em tags não promovem senioridade
# ==============================================================================


@pytest.mark.parametrize(
    ("tags", "case_label"),
    [
        (["python", "junior", "exec"], "1_junior_plus_exec"),
        (["python", "junior", "senior"], "2_junior_plus_senior"),
        (["python", "junior", "mid-level"], "3_junior_plus_mid_level"),
        (["python", "junior", "executive"], "4_junior_plus_executive"),
        (["python", "internship", "junior", "exec"], "5_internship_plus_junior_plus_exec"),
        (["python", "entry_level", "exec"], "6_entry_level_plus_exec"),
        (["python", "trainee", "senior"], "7a_trainee_plus_senior"),
        (["python", "graduate", "senior"], "7b_graduate_plus_senior"),
    ],
)
def test_dx0313_negative_conflicting_tags_do_not_promote_entry_or_junior(
    tags: list[str], case_label: str
):
    decision = classify_opportunity(
        title="Backend Developer",
        tags=tags,
        description="Build and maintain scalable Python APIs.",
    )
    reconciled = reconcile_structured_classification(decision)

    assert decision.opportunity_type == OpportunityType.OTHER.value, case_label
    assert decision.seniority_level == SeniorityLevel.UNKNOWN.value, case_label
    assert decision.employment_type == EmploymentType.UNKNOWN.value, case_label
    assert reconciled == (
        OpportunityType.OTHER.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.UNKNOWN.value,
    ), case_label


# ==============================================================================
# Cenário negativo (8): reprodução fiel dos 7 registros investigados do Remote OK
# ==============================================================================


@pytest.mark.parametrize(
    ("title", "description", "expected_exp_mode", "expected_exp_min"),
    [
        (
            "Human Resources Generalist",
            "Remote (US-based, W-2 — all US states considered). Compensation: $65,000 - $90,000.",
            ExperienceRequirementMode.NOT_SPECIFIED.value,
            None,
        ),
        (
            "Biologists",
            "Biology / Environmental Science Evaluator Remote. Hourly Contract $80-$120/hour.",
            ExperienceRequirementMode.NOT_SPECIFIED.value,
            None,
        ),
        (
            "Business Development Executive",
            "This is a remote position supporting business operations.",
            ExperienceRequirementMode.NOT_SPECIFIED.value,
            None,
        ),
        (
            "Full Stack Developer",
            "Requirements:\nBS Graduate.\nProven work experience as a Software Developer or similar role.\nExtensive experience with mobile development.",
            ExperienceRequirementMode.REQUIRED.value,
            None,
        ),
        (
            "Full Stack Developer",
            "Requirements:\n1-3 years of hands-on experience in JavaScript/TypeScript and React.js.\nWork closely with experienced developers.",
            ExperienceRequirementMode.REQUIRED.value,
            1,
        ),
        (
            "YouTube Video Editor Fresher",
            "Requirements:\n1+ years of experience in video editing (Adobe Suite) OR college students good at editing welcome.",
            ExperienceRequirementMode.REQUIRED.value,
            1,
        ),
        (
            "Human Resources Coordinator",
            "Requirements: 2-4+ years experience in an HR Coordinator, People Operations, or similar role.",
            ExperienceRequirementMode.REQUIRED.value,
            2,
        ),
    ],
)
def test_dx0313_seven_investigated_remote_ok_cases_resolve_to_other_unknown(
    title: str,
    description: str,
    expected_exp_mode: str,
    expected_exp_min: int | None,
):
    conn = RemoteOKConnector(
        tags=("dev",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    drafts = conn.parse_payload(
        [
            {"legal": "Remote OK API"},
            {
                "id": 999100,
                "position": title,
                "company": "SampleCo",
                "location": "United States",
                "tags": list(_SPAM_REMOTE_OK_TAGS),
                "url": "https://remoteok.com/remote-jobs/999100",
                "description": f"<p>{description}</p>",
            },
        ]
    )
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.opportunity_type == OpportunityType.OTHER.value
    assert draft.seniority_level == SeniorityLevel.UNKNOWN.value
    assert draft.employment_type == EmploymentType.UNKNOWN.value
    assert draft.experience_requirement_mode == expected_exp_mode
    assert draft.experience_min_years == expected_exp_min
    assert draft.eligible_countries == ["United States"]


# ==============================================================================
# Cenários positivos de preservação (9 a 15)
# ==============================================================================


def test_dx0313_positive_explicit_title_description_and_clean_tags_preserved():
    # 9. Título explícito Junior com tags ruidosas exec + junior
    dec_title_jr = classify_opportunity(
        title="Junior Python Developer",
        tags=["python", "exec", "junior"],
        description="Build FastAPI services.",
    )
    assert reconcile_structured_classification(dec_title_jr) == (
        OpportunityType.JUNIOR.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.JUNIOR.value,
    )

    # 10. Título genérico com declaração explícita Junior Backend Developer na descrição
    dec_body_jr = classify_opportunity(
        title="Backend Developer",
        tags=["python", "exec", "senior"],
        description="We are looking for a Junior Backend Developer to build Python APIs.",
    )
    assert reconcile_structured_classification(dec_body_jr) == (
        OpportunityType.JUNIOR.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.JUNIOR.value,
    )

    # 11. Título Entry-Level com tags superiores conflitantes
    dec_title_entry = classify_opportunity(
        title="Entry-Level Software Engineer",
        tags=["python", "exec", "senior"],
        description="Work on backend systems.",
    )
    assert reconcile_structured_classification(dec_title_entry) == (
        OpportunityType.JUNIOR.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.ENTRY_LEVEL.value,
    )

    # 12. Descrição com declaração explícita de estágio, mesmo com tags superiores conflitantes
    dec_body_intern = classify_opportunity(
        title="Backend Developer",
        tags=["python", "exec", "senior"],
        description="This is a paid software internship working with Python and PostgreSQL.",
    )
    assert reconcile_structured_classification(dec_body_intern) == (
        OpportunityType.INTERNSHIP.value,
        EmploymentType.INTERNSHIP.value,
        SeniorityLevel.INTERNSHIP.value,
    )

    # 13. Tag junior limpa sem conflito com sinal superior
    dec_clean_jr = classify_opportunity(
        title="Backend Developer",
        tags=["python", "junior"],
        description="Build Python APIs.",
    )
    assert reconcile_structured_classification(dec_clean_jr) == (
        OpportunityType.JUNIOR.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.JUNIOR.value,
    )

    # 14. Tag entry_level limpa sem conflito
    dec_clean_entry = classify_opportunity(
        title="Backend Developer",
        tags=["python", "entry_level"],
        description="Build Python APIs.",
    )
    assert reconcile_structured_classification(dec_clean_entry) == (
        OpportunityType.JUNIOR.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.ENTRY_LEVEL.value,
    )

    # 15. Tags sem sinais de entrada não alteram comportamento
    dec_neutral = classify_opportunity(
        title="Backend Developer",
        tags=["python", "fastapi", "postgresql"],
        description="Build Python APIs.",
    )
    assert reconcile_structured_classification(dec_neutral) == (
        OpportunityType.OTHER.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.UNKNOWN.value,
    )

    # 19. Senioridade explicitamente declarada no título não é afetada
    dec_senior = classify_opportunity(
        title="Senior Backend Developer",
        tags=["python", "junior", "exec"],
        description="Lead backend architecture.",
    )
    assert reconcile_structured_classification(dec_senior) == (
        OpportunityType.OTHER.value,
        EmploymentType.UNKNOWN.value,
        SeniorityLevel.SENIOR.value,
    )


# ==============================================================================
# Cenários de integridade (16 a 20): experiência, geografia, outras fontes e dry-run
# ==============================================================================


def test_dx0313_other_sources_and_reclassify_dry_run_integrity(db_session: Session):
    # 18. Outras fontes (GitHub BR e Himalayas) mantêm comportamento preservado
    gh = GitHubBackendBRConnector(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    gh_drafts = gh.parse_payload(
        [
            {
                "number": 9001,
                "state": "open",
                "title": "[Remoto] Desenvolvedor Backend Python na StartupBR",
                "html_url": "https://github.com/backend-br/vagas/issues/9001",
                "created_at": "2026-11-20T10:00:00Z",
                "labels": [{"name": "Júnior"}, {"name": "PJ"}, {"name": "Python"}],
                "body": "Atuação com FastAPI.",
            }
        ]
    )
    assert gh_drafts[0].opportunity_type == OpportunityType.JUNIOR.value
    assert gh_drafts[0].seniority_level == SeniorityLevel.JUNIOR.value
    assert gh_drafts[0].employment_type == EmploymentType.PJ.value

    him = HimalayasConnector(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    him_drafts = him.parse_payload(
        {
            "jobs": [
                {
                    "guid": "https://himalayas.app/companies/acme/jobs/entry-dev",
                    "title": "Software Engineer",
                    "companyName": "Acme",
                    "employmentType": "Full Time",
                    "seniority": ["Entry-level"],
                    "locationRestrictions": ["Brazil"],
                    "categories": ["Backend"],
                    "description": "<p>Build backend services.</p>",
                }
            ]
        }
    )
    assert him_drafts[0].opportunity_type == OpportunityType.JUNIOR.value
    assert him_drafts[0].seniority_level == SeniorityLevel.ENTRY_LEVEL.value

    # 16, 17, 20. reclassify_opportunities(..., dry_run=True) com tags conflitantes:
    # não promove a júnior, preserva experiência e geografia, e não persiste escrita.
    src = {s.slug: s for s in ensure_default_sources(db_session)}["remote_ok"]
    now = datetime.now(UTC)
    opp_conflict = Opportunity(
        source_id=src.id,
        external_id="dx0313-dryrun-1",
        title="Full Stack Developer",
        company_name="Fastlane",
        description="Requirements: 1-3 years of hands-on experience in TypeScript and React.",
        opportunity_type=OpportunityType.INTERNSHIP.value,
        seniority_level=SeniorityLevel.INTERNSHIP.value,
        employment_type=EmploymentType.INTERNSHIP.value,
        experience_requirement_mode=ExperienceRequirementMode.REQUIRED.value,
        experience_min_years=1,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.FULLSTACK.value,
        location_text="Petaling Jaya, Malaysia",
        country="Malaysia",
        eligible_countries=["Petaling Jaya", "Malaysia"],
        eligibility_unknown=False,
        technologies=list(_SPAM_REMOTE_OK_TAGS),
        source_url="https://remoteok.com/remote-jobs/dx0313-dryrun-1",
        first_seen_at=now,
        last_seen_at=now,
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-dx0313-1",
        raw_metadata={"source": "remote_ok"},
    )
    db_session.add(opp_conflict)
    db_session.commit()

    report = reclassify_opportunities(db_session, source_slug="remote_ok", dry_run=True)
    assert report.evaluated_count == 1
    assert report.updated_count == 1
    change = report.changes[0]

    # Não promovido para júnior nem mantido como estágio
    assert change.new_opportunity_type == OpportunityType.OTHER.value
    assert change.new_seniority_level == SeniorityLevel.UNKNOWN.value
    assert change.new_employment_type == EmploymentType.UNKNOWN.value
    # Experiência preservada integralmente
    assert change.old_experience_mode == change.new_experience_mode == ExperienceRequirementMode.REQUIRED.value
    assert change.old_experience_min_years == change.new_experience_min_years == 1
    # Geografia preservada integralmente
    assert change.old_eligible_countries == change.new_eligible_countries == ("Petaling Jaya", "Malaysia")
    assert change.old_country == change.new_country == "Malaysia"
    assert change.old_eligibility_unknown is False
    assert change.new_eligibility_unknown is False
    assert "geo:normalized_remote_non_country_token" not in change.reasons

    # Imutabilidade após dry-run
    db_session.expire_all()
    persisted = db_session.get(Opportunity, opp_conflict.id)
    assert persisted is not None
    assert persisted.opportunity_type == OpportunityType.INTERNSHIP.value
    assert persisted.seniority_level == SeniorityLevel.INTERNSHIP.value
    assert persisted.eligible_countries == ["Petaling Jaya", "Malaysia"]
