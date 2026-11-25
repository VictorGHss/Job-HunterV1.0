"""
Suíte DX-03.2.1 — Preservação de Proveniência e Normalização Semântica de Tecnologias.

Cobre:
- Normalização semântica, aliases canônicos, deduplicação case-insensitive, termos ambíguos
  (C, R, Go, AI, .NET, C++, C#) e tecnologias de nicho.
- Preservação integral da taxonomia original por fonte (Remote OK `raw_tags`, Himalayas
  `categories` sem truncamento, Jobicy `job_industry` com estrutura preservada, GitHub BR
  `labels` completas) em `OpportunitySourceLink.raw_metadata` e `Opportunity.raw_metadata`.
- Extração conservadora a partir do título no GitHub Frontend BR sem varrer descrições.
- Mesclagem cross-source sem contaminação, sem sobrescrever metadados primários e sem
  apagar dados legados.
- Compatibilidade da reclassificação (`reclassify_opportunities`) com `raw_tags` e regras
  DX-03.1 / DX-03.1.2 / DX-03.1.3, incluindo isolamento por fonte primária e fallback legado.
- Matching com tecnologias normalizadas, preservação de competências técnicas curadas e
  manutenção de oportunidades manuais e `content_hash`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.opportunity import (
    EmploymentType,
    ExperienceRequirementMode,
    ExternalSourceStatus,
    Opportunity,
    OpportunitySourceLink,
    OpportunityType,
    ProfessionalArea,
    SeniorityLevel,
    WorkMode,
)
from app.models.profile import Skill, SkillProficiency
from app.schemas.opportunity import ManualOpportunityCreate
from app.services.auth_service import create_user_account
from app.services.opportunities.connectors.github_vagas import (
    GitHubBackendBRConnector,
    GitHubFrontendBRConnector,
)
from app.services.opportunities.connectors.himalayas import HimalayasConnector
from app.services.opportunities.connectors.jobicy import JobicyConnector
from app.services.opportunities.connectors.remote_ok import RemoteOKConnector
from app.services.opportunities.matching import evaluate_opportunity_for_user
from app.services.opportunities.opportunity_service import create_manual_opportunity
from app.services.opportunities.sanitization import compute_opportunity_content_hash
from app.services.opportunities.sync_service import (
    ensure_default_sources,
    reclassify_opportunities,
    sync_sources,
)
from app.services.opportunities.technology_normalization import (
    extract_technologies_from_title,
    merge_normalized_technologies,
    normalize_technologies,
)
from app.services.profile_service import get_or_create_profile


# ==============================================================================
# 1. Normalização semântica compartilhada
# ==============================================================================


def test_dx0321_semantic_normalization_valid_aliases_dedup_and_order():
    raw = [
        "python",
        "PYTHON",
        "nodejs",
        "Node.js",
        "React.js",
        "react",
        "react-native",
        "postgres",
        "PostgreSQL",
        "k8s",
        "docker",
        "aws",
        "terraform",
        "kafka",
        "snowflake",
        "typescript",
        "javascript",
        "dotnet",
        "c++",
        "c#",
    ]
    normalized = normalize_technologies(raw, source_context="remote_ok")
    assert normalized == [
        "Python",
        "Node.js",
        "React",
        "React Native",
        "PostgreSQL",
        "Kubernetes",
        "Docker",
        "AWS",
        "Terraform",
        "Kafka",
        "Snowflake",
        "TypeScript",
        "JavaScript",
        ".NET",
        "C++",
        "C#",
    ]


def test_dx0321_semantic_normalization_rejects_non_tech_categories():
    non_tech = [
        # Cargos
        "Software Engineer",
        "Backend Engineer",
        "Data Entry Clerk",
        "Administrative Assistant",
        # Setores
        "Finance",
        "Education",
        "Healthcare",
        "Software Engineering",
        "Data Science & Analytics",
        # Senioridade
        "junior",
        "senior",
        "exec",
        "internship",
        "mid-level",
        # Modalidades
        "remote",
        "hybrid",
        "onsite",
        # Lifestyle e vínculos
        "digital nomad",
        "travel",
        "full time",
        "part time",
        # Funções genéricas
        "customer support",
        "recruiter",
        "marketing",
        "virtual assistant",
        # Labels administrativas
        "link-quebrado",
        "em-triagem",
        "duplicada",
        "pausada",
        "spam",
        "invalid",
    ]
    assert normalize_technologies(non_tech, source_context="remote_ok") == []
    assert normalize_technologies(non_tech, source_context="github_curated") == []


def test_dx0321_ambiguous_tokens_and_niche_technologies():
    # C isolado em vaga de RH nunca vira linguagem C
    assert (
        normalize_technologies(
            ["c", "hr", "recruiter", "finance"],
            source_context="remote_ok",
            context_title="Human Resources Generalist",
        )
        == []
    )
    # R e AI isolados não viram tecnologias automaticamente
    assert (
        normalize_technologies(
            ["r", "ai", "marketing"],
            source_context="remote_ok",
            context_title="Marketing Analyst",
        )
        == []
    )
    # Go sem contexto técnico (ex.: Go-to-Market) é rejeitado
    assert (
        normalize_technologies(
            ["go", "marketing", "sales"],
            source_context="remote_ok",
            context_title="Go-to-Market Manager",
        )
        == []
    )
    # Go com contexto técnico real ou via "golang" é reconhecido como Go
    assert (
        normalize_technologies(
            ["go", "docker", "kubernetes"],
            source_context="remote_ok",
            context_title="Backend Engineer",
        )
        == ["Go", "Docker", "Kubernetes"]
    )
    assert normalize_technologies(["golang"], source_context="remote_ok") == ["Go"]
    # .NET, C++, C# e C/C++ preservam identidades
    assert normalize_technologies(
        [".net", "C++", "C#", "C/C++"],
        source_context="remote_ok",
    ) == [".NET", "C++", "C#", "C"]
    # RStudio / R Language explícitos são reconhecidos
    assert normalize_technologies(
        ["RStudio", "R Language"],
        source_context="remote_ok",
    ) == ["RStudio", "R"]
    # Tecnologias de nicho reconhecidas sem whitelist arbitrariamente pequena
    niche = ["Elixir", "Haskell", "Zig", "ClickHouse", "DuckDB", "Pulumi", "ArgoCD", "dbt", "Solidity"]
    assert normalize_technologies(niche, source_context="remote_ok") == niche


def test_dx0321_extract_technologies_from_title_conservative_cases():
    assert extract_technologies_from_title("React Native Developer") == ["React Native"]
    assert extract_technologies_from_title("Back-end Engineer .NET") == [".NET"]
    assert extract_technologies_from_title(
        "Full-stack Engineer React.js • UX Design • Node.js"
    ) == ["React", "Node.js"]
    assert extract_technologies_from_title("Go-to-Market Manager") == []
    assert extract_technologies_from_title("Ready to Go Sales Coordinator") == []
    assert extract_technologies_from_title("Backend Go Engineer (PostgreSQL / Docker)") == [
        "Go",
        "PostgreSQL",
        "Docker",
    ]
    assert extract_technologies_from_title("Senior C++ / C# Systems Engineer") == ["C++", "C#"]
    assert extract_technologies_from_title("Human Resources C-Level Coordinator") == []


# ==============================================================================
# 2. Preservação de proveniência e comportamento por conector
# ==============================================================================


def test_dx0321_remote_ok_preserves_raw_tags_normalizes_techs_and_keeps_dx0313():
    raw_tags = [
        "Python",
        "FASTAPI",
        "postgres",
        "c",
        "exec",
        "junior",
        "internship",
        "digital nomad",
        "finance",
        "medical",
        "travel",
        "customer support",
        "UnknownCustomBadge",
        "Snowflake",
    ]
    conn = RemoteOKConnector(
        tags=("dev",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    drafts = conn.parse_payload(
        [
            {"legal": "Remote OK"},
            {
                "id": "rok-321",
                "slug": "backend-dev-rok-321",
                "position": "Backend Developer",
                "company": "Acme",
                "location": "Worldwide",
                "tags": raw_tags,
                "url": "https://remoteok.com/remote-jobs/rok-321",
                "description": "<p>Build distributed Python APIs with FastAPI and PostgreSQL.</p>",
            },
        ]
    )
    assert len(drafts) == 1
    draft = drafts[0]
    # Proveniência integral preservada sem perda de capitalização, ordem ou desconhecidos
    assert draft.raw_metadata["raw_tags"] == raw_tags
    assert draft.raw_metadata["source"] == "remote_ok"
    # Technologies contém apenas tecnologias reais normalizadas (sem spam e sem "c" isolado)
    assert draft.technologies == ["Python", "FastAPI", "PostgreSQL", "Snowflake"]
    # Proteção DX-03.1.3 preservada mesmo após limpeza de technologies
    assert draft.opportunity_type == OpportunityType.OTHER.value
    assert draft.seniority_level == SeniorityLevel.UNKNOWN.value
    assert draft.employment_type == EmploymentType.UNKNOWN.value


def test_dx0321_himalayas_preserves_all_categories_without_truncation_and_clean_techs():
    twelve_categories = [
        "Software-Engineer",
        "Data-Entry-Clerk",
        "Administrative-Assistant",
        "Backend",
        "Full-Stack",
        "Customer-Support",
        "Operations",
        "Finance",
        "Healthcare",
        "Category-Nine",
        "Category-Ten",
        "Category-Twelve",
    ]
    future_epoch = int((datetime.now(UTC) + timedelta(days=20)).timestamp())
    conn = HimalayasConnector(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"jobs": []})),
    )
    drafts = conn.parse_payload(
        {
            "jobs": [
                {
                    "guid": "https://himalayas.app/companies/acme/jobs/him-321",
                    "title": "Software Engineer",
                    "companyName": "Acme",
                    "employmentType": "Full Time",
                    "seniority": ["Entry-level"],
                    "locationRestrictions": ["Brazil"],
                    "categories": twelve_categories,
                    "description": "<p>Build backend systems.</p>",
                    "expiryDate": future_epoch,
                }
            ]
        }
    )
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.raw_metadata["categories"] == twelve_categories
    assert len(draft.raw_metadata["categories"]) == 12
    assert draft.technologies == []
    assert draft.opportunity_type == OpportunityType.JUNIOR.value
    assert draft.seniority_level == SeniorityLevel.ENTRY_LEVEL.value


def test_dx0321_jobicy_preserves_job_industry_structure_and_keeps_technologies_clean():
    conn = JobicyConnector(
        industries=("engineering",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"jobs": []})),
    )
    drafts = conn.parse_payload(
        {
            "jobs": [
                {
                    "id": 32101,
                    "url": "https://jobicy.com/jobs/32101-list",
                    "jobTitle": "Software Engineer",
                    "companyName": "JobicyCo",
                    "jobIndustry": ["Software Engineering", "Data Science & Analytics"],
                    "jobType": ["Full-Time"],
                    "jobGeo": "Anywhere",
                    "jobLevel": "Entry-level",
                    "jobDescription": "<p>Develop backend systems.</p>",
                },
                {
                    "id": 32102,
                    "url": "https://jobicy.com/jobs/32102-str",
                    "jobTitle": "Data Analyst",
                    "companyName": "JobicyCo",
                    "jobIndustry": "Data Science & Analytics",
                    "jobType": ["Contract"],
                    "jobGeo": "Anywhere",
                    "jobLevel": "Any",
                    "jobDescription": "<p>Analyze metrics.</p>",
                },
            ]
        }
    )
    by_id = {d.external_id: d for d in drafts}
    assert by_id["32101"].raw_metadata["job_industry"] == [
        "Software Engineering",
        "Data Science & Analytics",
    ]
    assert by_id["32101"].technologies == []
    assert by_id["32101"].opportunity_type == OpportunityType.JUNIOR.value
    assert by_id["32101"].seniority_level == SeniorityLevel.ENTRY_LEVEL.value

    assert by_id["32102"].raw_metadata["job_industry"] == "Data Science & Analytics"
    assert by_id["32102"].technologies == []


def test_dx0321_github_backend_br_preserves_labels_excludes_admin_and_keeps_curated_techs():
    raw_labels = [
        "Remoto",
        "PJ",
        "Júnior",
        "link-quebrado",
        "em-triagem",
        "duplicada",
        "pausada",
        "spam",
        "invalid",
        "python",
        "FastAPI",
        "postgres",
        "DDD",
        "SOLID",
        "Clean Architecture",
        "Testes automatizados",
        "Quarkus",
        "VRaptor",
    ]
    conn = GitHubBackendBRConnector(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    drafts = conn.parse_payload(
        [
            {
                "number": 3210,
                "state": "open",
                "title": "[Remoto] Desenvolvedor Backend Python na AcmeBR",
                "html_url": "https://github.com/backend-br/vagas/issues/3210",
                "created_at": "2026-11-20T10:00:00Z",
                "labels": [{"name": lb} for lb in raw_labels],
                "body": "Atuação com FastAPI, PostgreSQL e boas práticas de arquitetura.",
            }
        ]
    )
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.raw_metadata["labels"] == raw_labels
    assert draft.technologies == [
        "Python",
        "FastAPI",
        "PostgreSQL",
        "DDD",
        "SOLID",
        "Clean Architecture",
        "Testes automatizados",
        "Quarkus",
        "VRaptor",
    ]
    for excluded in ("link-quebrado", "em-triagem", "duplicada", "pausada", "spam", "invalid", "Remoto", "PJ", "Júnior"):
        assert excluded not in draft.technologies
    assert draft.opportunity_type == OpportunityType.JUNIOR.value
    assert draft.seniority_level == SeniorityLevel.JUNIOR.value
    assert draft.employment_type == EmploymentType.PJ.value


def test_dx0321_github_frontend_br_extracts_explicit_title_techs_only():
    conn = GitHubFrontendBRConnector(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    drafts = conn.parse_payload(
        [
            {
                "number": 4101,
                "state": "open",
                "title": "[Remoto] React Native Developer na StudioApp",
                "html_url": "https://github.com/frontendbr/vagas/issues/4101",
                "created_at": "2026-11-20T10:00:00Z",
                "labels": [{"name": "Remoto"}, {"name": "PJ"}],
                "body": "Diferencial: Docker, Kubernetes, AWS, Terraform, Ruby, Rust.",
            },
            {
                "number": 4102,
                "state": "open",
                "title": "[Remoto] Back-end Engineer .NET na TechCorp",
                "html_url": "https://github.com/frontendbr/vagas/issues/4102",
                "created_at": "2026-11-20T10:00:00Z",
                "labels": [],
                "body": "Vaga com foco em sistemas corporativos.",
            },
            {
                "number": 4103,
                "state": "open",
                "title": "[Remoto] Full-stack Engineer React.js • UX Design • Node.js na DesignTech",
                "html_url": "https://github.com/frontendbr/vagas/issues/4103",
                "created_at": "2026-11-20T10:00:00Z",
                "labels": [{"name": "em-triagem"}, {"name": "Remoto"}],
                "body": "Também utilizamos Python e Kafka em outros times da empresa.",
            },
        ]
    )
    by_id = {d.external_id: d for d in drafts}

    assert by_id["gh-frontend-br-4101"].technologies == ["React Native"]
    assert by_id["gh-frontend-br-4101"].raw_metadata["labels"] == ["Remoto", "PJ"]
    # Nunca extrai lista genérica da descrição
    assert "Docker" not in by_id["gh-frontend-br-4101"].technologies
    assert "Kubernetes" not in by_id["gh-frontend-br-4101"].technologies

    assert by_id["gh-frontend-br-4102"].technologies == [".NET"]
    assert by_id["gh-frontend-br-4102"].raw_metadata["labels"] == []

    assert by_id["gh-frontend-br-4103"].technologies == ["React", "Node.js"]
    assert by_id["gh-frontend-br-4103"].raw_metadata["labels"] == ["em-triagem", "Remoto"]
    assert "UX Design" not in by_id["gh-frontend-br-4103"].technologies
    assert "Python" not in by_id["gh-frontend-br-4103"].technologies


# ==============================================================================
# 3. Mesclagem cross-source e preservação de proveniência por OpportunitySourceLink
# ==============================================================================


def test_dx0321_cross_source_merge_preserves_provenance_and_blocks_contamination(
    db_session: Session,
):
    shared_apply_url = "https://careers.acme-global.example/jobs/backend-py-321"
    future_epoch = int((datetime.now(UTC) + timedelta(days=30)).timestamp())

    rok_payload = [
        {"legal": "Remote OK"},
        {
            "id": "rok-dup-321",
            "slug": "python-backend-rok-321",
            "position": "Python Backend Engineer na Acme Global",
            "company": "Acme Global",
            "location": "Worldwide",
            "tags": ["python", "FASTAPI", "exec", "finance", "digital nomad"],
            "url": "https://remoteok.com/remote-jobs/rok-dup-321",
            "apply_url": shared_apply_url,
            "description": "<p>Build scalable Python and FastAPI microservices.</p>",
        },
    ]
    him_payload = {
        "jobs": [
            {
                "guid": "https://himalayas.app/companies/acme-global/jobs/backend-py-321",
                "title": "Python Backend Engineer na Acme Global",
                "companyName": "Acme Global",
                "employmentType": "Full Time",
                "seniority": ["Entry-level"],
                "locationRestrictions": ["Brazil"],
                "categories": [
                    "Software-Engineer",
                    "Backend-Engineer",
                    "Data-Entry-Clerk",
                    "Finance",
                    "Cat-5",
                    "Cat-6",
                    "Cat-7",
                    "Cat-8",
                    "Cat-9",
                ],
                "applicationLink": shared_apply_url,
                "description": "<p>Build scalable Python and FastAPI microservices.</p>",
                "expiryDate": future_epoch,
            }
        ]
    }
    gh_payload = [
        {
            "number": 7771,
            "state": "open",
            "title": "Python Backend Engineer na Acme Global",
            "html_url": "https://github.com/backend-br/vagas/issues/7771",
            "created_at": "2026-11-20T10:00:00Z",
            "labels": [
                {"name": "Remoto"},
                {"name": "link-quebrado"},
                {"name": "PYTHON"},
                {"name": "postgres"},
                {"name": "Docker"},
            ],
            "body": "Build scalable Python and FastAPI microservices.",
        }
    ]

    overrides = {
        "remote_ok": RemoteOKConnector(
            tags=("dev",),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=rok_payload)),
            sleep_fn=lambda _: None,
        ),
        "himalayas": HimalayasConnector(
            max_pages=1,
            search_queries=(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=him_payload)),
            sleep_fn=lambda _: None,
        ),
        "github_backend_br": GitHubBackendBRConnector(
            max_pages=1,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=gh_payload)),
            sleep_fn=lambda _: None,
        ),
    }

    sync_sources(db_session, source_slug="remote_ok", force=True, connector_overrides=overrides)
    sync_sources(db_session, source_slug="himalayas", force=True, connector_overrides=overrides)
    sync_sources(db_session, source_slug="github_backend_br", force=True, connector_overrides=overrides)

    opps = db_session.execute(select(Opportunity)).scalars().all()
    assert len(opps) == 1
    opp = opps[0]

    # Metadados primários (Remote OK) NÃO foram sobrescritos pela fonte secundária
    assert opp.raw_metadata["source"] == "remote_ok"
    assert opp.raw_metadata["raw_tags"] == ["python", "FASTAPI", "exec", "finance", "digital nomad"]
    assert "categories" not in opp.raw_metadata
    assert "labels" not in opp.raw_metadata
    assert set(opp.raw_metadata.get("also_seen_in_sources", [])) == {"himalayas", "github_backend_br"}

    # Technologies mescladas sem duplicação case-insensitive e sem contaminação
    assert opp.technologies == ["Python", "FastAPI", "PostgreSQL", "Docker"]

    # Cada fonte preservou integralmente sua própria taxonomia em OpportunitySourceLink.raw_metadata
    links = (
        db_session.execute(
            select(OpportunitySourceLink).where(OpportunitySourceLink.opportunity_id == opp.id)
        )
        .scalars()
        .all()
    )
    links_by_slug = {link.source.slug: link for link in links}
    assert set(links_by_slug.keys()) == {"remote_ok", "himalayas", "github_backend_br"}
    assert links_by_slug["remote_ok"].is_primary is True
    assert links_by_slug["remote_ok"].raw_metadata["raw_tags"] == [
        "python",
        "FASTAPI",
        "exec",
        "finance",
        "digital nomad",
    ]
    assert links_by_slug["himalayas"].is_primary is False
    assert len(links_by_slug["himalayas"].raw_metadata["categories"]) == 9
    assert links_by_slug["himalayas"].raw_metadata["categories"][-1] == "Cat-9"
    assert links_by_slug["github_backend_br"].is_primary is False
    assert "link-quebrado" in links_by_slug["github_backend_br"].raw_metadata["labels"]

    # Reclassificação usa exclusivamente os metadados da fonte primária (remote_ok),
    # sem absorver seniority=["Entry-level"] do link secundário Himalayas!
    rep = reclassify_opportunities(db_session, source_slug="remote_ok", dry_run=True)
    assert rep.evaluated_count == 1
    assert rep.updated_count == 0
    assert opp.opportunity_type == OpportunityType.OTHER.value
    assert opp.seniority_level == SeniorityLevel.UNKNOWN.value


def test_dx0321_merge_normalized_technologies_preserves_legacy_entries_and_deduplicates():
    # Registro legado com entradas antigas não é apagado cegamente; novas entradas
    # são normalizadas, filtradas e deduplicadas case-insensitive.
    legacy_existing = ["python", "LegacyTagFromUnknownSource"]
    merged = merge_normalized_technologies(
        legacy_existing,
        ["Python", "nodejs", "Software Engineer", "Finance", "docker"],
        incoming_source_slug="remote_ok",
        context_title="Backend Developer",
    )
    assert merged == ["python", "LegacyTagFromUnknownSource", "Node.js", "Docker"]

    # Fonte Himalayas/Jobicy não injeta categorias/setores mesmo se passados indevidamente
    merged_him = merge_normalized_technologies(
        ["Python"],
        ["Software Engineer", "Backend", "Python"],
        incoming_source_slug="himalayas",
    )
    assert merged_him == ["Python"]


# ==============================================================================
# 4. Classificação e reclassificação com raw_tags (compatibilidade DX-03.1.x)
# ==============================================================================


def test_dx0321_reclassify_uses_raw_tags_preserving_dx0313_and_legacy_fallback(
    db_session: Session,
):
    sources = {s.slug: s for s in ensure_default_sources(db_session)}
    rok_src = sources["remote_ok"]
    now = datetime.now(UTC)

    def _make_rok_opp(
        ext_id: str,
        *,
        title: str,
        description: str,
        opp_type: str,
        sen: str,
        emp: str,
        technologies: list[str],
        raw_metadata: dict,
        link_raw_metadata: dict | None = None,
    ) -> Opportunity:
        opp = Opportunity(
            source_id=rok_src.id,
            external_id=ext_id,
            title=title,
            company_name="SampleCo",
            description=description,
            opportunity_type=opp_type,
            seniority_level=sen,
            employment_type=emp,
            work_mode=WorkMode.REMOTE.value,
            professional_area=ProfessionalArea.BACKEND.value,
            eligible_countries=["Worldwide"],
            eligibility_unknown=False,
            technologies=technologies,
            source_url=f"https://remoteok.com/remote-jobs/{ext_id}",
            first_seen_at=now,
            last_seen_at=now,
            source_status=ExternalSourceStatus.ACTIVE.value,
            content_hash=f"h-{ext_id}",
            raw_metadata=raw_metadata,
        )
        db_session.add(opp)
        db_session.flush()
        if link_raw_metadata is not None:
            db_session.add(
                OpportunitySourceLink(
                    opportunity_id=opp.id,
                    source_id=rok_src.id,
                    external_id=ext_id,
                    source_url=opp.source_url,
                    is_primary=True,
                    source_status=ExternalSourceStatus.ACTIVE.value,
                    first_seen_at=now,
                    last_seen_at=now,
                    raw_metadata=link_raw_metadata,
                )
            )
        return opp

    # Caso A: raw_tags=["python", "exec", "junior"], technologies=["Python"] -> conflito bloqueado!
    opp_conflict = _make_rok_opp(
        "recls-conflict",
        title="Backend Developer",
        description="Build Python APIs.",
        opp_type=OpportunityType.JUNIOR.value,
        sen=SeniorityLevel.JUNIOR.value,
        emp=EmploymentType.UNKNOWN.value,
        technologies=["Python"],
        raw_metadata={"source": "remote_ok", "raw_tags": ["python", "exec", "junior"]},
        link_raw_metadata={"source": "remote_ok", "raw_tags": ["python", "exec", "junior"]},
    )

    # Caso B: raw_tags=["python", "junior"] sem conflito, technologies=["Python"] -> mantém junior!
    opp_clean_jr = _make_rok_opp(
        "recls-clean-jr",
        title="Backend Developer",
        description="Build Python APIs.",
        opp_type=OpportunityType.OTHER.value,
        sen=SeniorityLevel.UNKNOWN.value,
        emp=EmploymentType.UNKNOWN.value,
        technologies=["Python"],
        raw_metadata={"source": "remote_ok", "raw_tags": ["python", "junior"]},
        link_raw_metadata={"source": "remote_ok", "raw_tags": ["python", "junior"]},
    )

    # Caso C: raw_tags=["python", "entry_level"] sem conflito -> entry_level + junior!
    opp_clean_entry = _make_rok_opp(
        "recls-clean-entry",
        title="Backend Developer",
        description="Build Python APIs.",
        opp_type=OpportunityType.OTHER.value,
        sen=SeniorityLevel.UNKNOWN.value,
        emp=EmploymentType.UNKNOWN.value,
        technologies=["Python"],
        raw_metadata={"source": "remote_ok", "raw_tags": ["python", "entry_level"]},
        link_raw_metadata={"source": "remote_ok", "raw_tags": ["python", "entry_level"]},
    )

    # Caso D: raw_tags=["python", "internship", "senior"] -> conflito bloqueado!
    opp_intern_conflict = _make_rok_opp(
        "recls-intern-conflict",
        title="Backend Developer",
        description="Build Python APIs.",
        opp_type=OpportunityType.INTERNSHIP.value,
        sen=SeniorityLevel.INTERNSHIP.value,
        emp=EmploymentType.INTERNSHIP.value,
        technologies=["Python"],
        raw_metadata={"source": "remote_ok", "raw_tags": ["python", "internship", "senior"]},
        link_raw_metadata={"source": "remote_ok", "raw_tags": ["python", "internship", "senior"]},
    )

    # Caso E: evidência explícita no título + descrição prevalece sobre conflito em raw_tags
    opp_explicit_title = _make_rok_opp(
        "recls-explicit-title",
        title="Junior Python Developer",
        description="We are looking for a Junior Backend Developer to build Python APIs.",
        opp_type=OpportunityType.OTHER.value,
        sen=SeniorityLevel.UNKNOWN.value,
        emp=EmploymentType.UNKNOWN.value,
        technologies=["Python"],
        raw_metadata={"source": "remote_ok", "raw_tags": ["python", "exec", "senior"]},
        link_raw_metadata={"source": "remote_ok", "raw_tags": ["python", "exec", "senior"]},
    )

    # Caso F: registro legado sem raw_tags (fallback conservador para technologies)
    opp_legacy = _make_rok_opp(
        "recls-legacy",
        title="Backend Developer",
        description="Build Python APIs.",
        opp_type=OpportunityType.JUNIOR.value,
        sen=SeniorityLevel.JUNIOR.value,
        emp=EmploymentType.UNKNOWN.value,
        technologies=["python", "exec", "junior"],
        raw_metadata={"source": "remote_ok"},
        link_raw_metadata=None,
    )

    db_session.commit()

    report = reclassify_opportunities(db_session, source_slug="remote_ok", dry_run=True)
    changes_by_id = {c.opportunity_id: c for c in report.changes}

    # A: conflito bloqueado
    c_conflict = changes_by_id[str(opp_conflict.id)]
    assert (c_conflict.new_opportunity_type, c_conflict.new_seniority_level) == (
        OpportunityType.OTHER.value,
        SeniorityLevel.UNKNOWN.value,
    )

    # B: junior limpo recuperado via raw_tags
    c_jr = changes_by_id[str(opp_clean_jr.id)]
    assert (c_jr.new_opportunity_type, c_jr.new_seniority_level) == (
        OpportunityType.JUNIOR.value,
        SeniorityLevel.JUNIOR.value,
    )

    # C: entry_level limpo recuperado via raw_tags
    c_entry = changes_by_id[str(opp_clean_entry.id)]
    assert (c_entry.new_opportunity_type, c_entry.new_seniority_level) == (
        OpportunityType.JUNIOR.value,
        SeniorityLevel.ENTRY_LEVEL.value,
    )

    # D: internship + senior conflitante bloqueado
    c_intern = changes_by_id[str(opp_intern_conflict.id)]
    assert (c_intern.new_opportunity_type, c_intern.new_seniority_level, c_intern.new_employment_type) == (
        OpportunityType.OTHER.value,
        SeniorityLevel.UNKNOWN.value,
        EmploymentType.UNKNOWN.value,
    )

    # E: título/descrição explícito preservado
    c_title = changes_by_id[str(opp_explicit_title.id)]
    assert (c_title.new_opportunity_type, c_title.new_seniority_level) == (
        OpportunityType.JUNIOR.value,
        SeniorityLevel.JUNIOR.value,
    )

    # F: fallback legado continua bloqueando conflito
    c_legacy = changes_by_id[str(opp_legacy.id)]
    assert (c_legacy.new_opportunity_type, c_legacy.new_seniority_level) == (
        OpportunityType.OTHER.value,
        SeniorityLevel.UNKNOWN.value,
    )


# ==============================================================================
# 5. Matching, oportunidades manuais e preservação de content_hash
# ==============================================================================


def test_dx0321_matching_manual_opportunities_and_content_hash_integrity(db_session: Session):
    user = create_user_account(
        db_session,
        email="dx0321.match@example.com",
        display_name="Dev DX0321",
        password="StrongPassword123!",
        is_admin=False,
    )
    profile = get_or_create_profile(db_session, user)
    profile.country = "Brasil"
    skills = [
        Skill(user_id=user.id, name="Python", category="backend", proficiency_level=SkillProficiency.INTERMEDIATE.value),
        Skill(user_id=user.id, name="PostgreSQL", category="database", proficiency_level=SkillProficiency.INTERMEDIATE.value),
        Skill(user_id=user.id, name="DDD", category="architecture", proficiency_level=SkillProficiency.INTERMEDIATE.value),
        Skill(user_id=user.id, name="Node.js", category="backend", proficiency_level=SkillProficiency.INTERMEDIATE.value),
    ]
    db_session.add_all(skills)
    db_session.commit()

    # Ingestão Remote OK normalizada: matching consome apenas tecnologias reais, sem spam
    conn = RemoteOKConnector(
        tags=("dev",),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    draft = conn.parse_payload(
        [
            {"legal": "Remote OK"},
            {
                "id": "match-321",
                "position": "Junior Python Backend Developer",
                "company": "Acme",
                "location": "Worldwide",
                "tags": ["python", "postgres", "digital nomad", "finance", "recruiter", "customer support"],
                "url": "https://remoteok.com/remote-jobs/match-321",
                "description": "<p>Build backend services using Python and PostgreSQL.</p>",
            },
        ]
    )[0]
    now = datetime.now(UTC)
    opp = Opportunity(
        external_id=draft.external_id,
        title=draft.title,
        company_name=draft.company_name,
        description=draft.description,
        opportunity_type=draft.opportunity_type,
        seniority_level=draft.seniority_level,
        employment_type=draft.employment_type,
        work_mode=draft.work_mode,
        professional_area=draft.professional_area,
        secondary_areas=draft.secondary_areas,
        eligible_countries=draft.eligible_countries,
        eligibility_unknown=draft.eligibility_unknown,
        technologies=draft.technologies,
        source_url=draft.source_url,
        first_seen_at=now,
        last_seen_at=now,
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-match-321",
        raw_metadata=draft.raw_metadata,
    )
    ev = evaluate_opportunity_for_user(opp, profile, skills=skills)
    assert "Python" in ev.matched_skills
    assert "PostgreSQL" in ev.matched_skills
    assert "digital nomad" not in opp.technologies
    assert "finance" not in opp.technologies

    # Competências curadas (DDD) continuam suportadas no matching
    gh_conn = GitHubBackendBRConnector(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    gh_draft = gh_conn.parse_payload(
        [
            {
                "number": 8881,
                "state": "open",
                "title": "[Remoto] Desenvolvedor Backend Python na CuratedBR",
                "html_url": "https://github.com/backend-br/vagas/issues/8881",
                "created_at": "2026-11-20T10:00:00Z",
                "labels": [{"name": "Remoto"}, {"name": "Júnior"}, {"name": "PJ"}, {"name": "Python"}, {"name": "DDD"}, {"name": "em-triagem"}],
                "body": "Python e DDD.",
            }
        ]
    )[0]
    gh_opp = Opportunity(
        external_id=gh_draft.external_id,
        title=gh_draft.title,
        company_name=gh_draft.company_name,
        description=gh_draft.description,
        opportunity_type=gh_draft.opportunity_type,
        seniority_level=gh_draft.seniority_level,
        employment_type=gh_draft.employment_type,
        work_mode=gh_draft.work_mode,
        professional_area=gh_draft.professional_area,
        eligible_countries=gh_draft.eligible_countries,
        technologies=gh_draft.technologies,
        source_url=gh_draft.source_url,
        first_seen_at=now,
        last_seen_at=now,
        source_status=ExternalSourceStatus.ACTIVE.value,
        content_hash="h-gh-321",
        raw_metadata=gh_draft.raw_metadata,
    )
    ev_gh = evaluate_opportunity_for_user(gh_opp, profile, skills=skills)
    assert "DDD" in gh_opp.technologies
    assert "DDD" in ev_gh.matched_skills
    assert "em-triagem" not in gh_opp.technologies

    # Oportunidade manual preserva comportamento original sem normalização retroativa forçada
    manual = create_manual_opportunity(
        db_session,
        user,
        ManualOpportunityCreate(
            title="Vaga Manual Especializada",
            opportunity_type=OpportunityType.JUNIOR,
            employment_type=EmploymentType.PJ,
            work_mode=WorkMode.REMOTE,
            eligible_countries=["Brasil"],
            technologies=["MinhaFerramentaInterna", "Python"],
            source_url="https://carreiras.empresa.example/vaga-manual-321",
        ),
    )
    assert manual.technologies == ["MinhaFerramentaInterna", "Python"]

    # content_hash permanece inalterado (determinístico sem depender de technologies)
    h1 = compute_opportunity_content_hash(
        title="Backend Developer",
        company_name="Acme",
        source_url="https://example.com/1",
        work_mode="remote",
        employment_type="pj",
        location_text="Worldwide",
        description="Build APIs",
    )
    h2 = compute_opportunity_content_hash(
        title="Backend Developer",
        company_name="Acme",
        source_url="https://example.com/1",
        work_mode="remote",
        employment_type="pj",
        location_text="Worldwide",
        description="Build APIs",
    )
    assert h1 == h2
