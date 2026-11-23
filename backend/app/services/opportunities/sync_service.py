from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Mapping
from urllib.parse import urlparse
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.opportunity import (
    ExternalSourceStatus,
    Opportunity,
    OpportunitySource,
    OpportunitySourceLink,
    OpportunitySyncRun,
    SyncRunStatus,
)
from app.schemas.opportunity import SyncRunSummary
from app.services.opportunities.classification import (
    classify_opportunity,
    normalize_classification_text,
    reconcile_structured_classification,
)
from app.services.opportunities.connectors.base import (
    BaseOpportunityConnector,
    ConnectorError,
    NormalizedOpportunityDraft,
    SourceLifecycleSignal,
)
from app.services.opportunities.connectors.github_vagas import (
    GitHubBackendBRConnector,
    GitHubFrontendBRConnector,
)
from app.services.opportunities.connectors.himalayas import HimalayasConnector
from app.services.opportunities.connectors.jobicy import (
    JobicyConnector,
    extract_base_title_and_geo_suffix,
)
from app.services.opportunities.connectors.remote_ok import RemoteOKConnector
from app.services.opportunities.connectors.remotive import RemotiveConnector
from app.services.opportunities.matching import (
    ensure_utc,
    is_deadline_expired,
    parse_location_cities,
    utc_now,
)
from app.services.opportunities.sanitization import compute_opportunity_content_hash

CONNECTOR_CLASSES: dict[str, type[BaseOpportunityConnector]] = {
    RemoteOKConnector.definition.slug: RemoteOKConnector,
    JobicyConnector.definition.slug: JobicyConnector,
    HimalayasConnector.definition.slug: HimalayasConnector,
    GitHubBackendBRConnector.definition.slug: GitHubBackendBRConnector,
    GitHubFrontendBRConnector.definition.slug: GitHubFrontendBRConnector,
    RemotiveConnector.definition.slug: RemotiveConnector,
}


class UpsertOutcome(StrEnum):
    INSERTED = "inserted"
    UPDATED = "updated"
    INTRA_SOURCE_DUPLICATE = "intra_source_duplicate"
    CROSS_SOURCE_DUPLICATE = "cross_source_duplicate"


def ensure_default_sources(db: Session) -> list[OpportunitySource]:
    """
    Garante o registro das fontes públicas no banco de forma idempotente e segura
    contra inicializações concorrentes (multiworker), usando INSERT ... ON CONFLICT DO NOTHING
    no PostgreSQL/SQLite. Nunca reativa automaticamente fontes desabilitadas manualmente
    quando a definição padrão permitir habilitação.
    """
    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    now = utc_now()
    for connector_cls in CONNECTOR_CLASSES.values():
        defn = connector_cls.definition
        values = {
            "id": uuid.uuid4(),
            "slug": defn.slug,
            "name": defn.name,
            "source_type": defn.source_type,
            "base_url": defn.base_url,
            "terms_url": defn.terms_url,
            "attribution_text": defn.attribution_text,
            "enabled": defn.enabled_by_default,
            "refresh_interval_seconds": defn.refresh_interval_seconds,
            "created_at": now,
            "updated_at": now,
        }
        if dialect_name == "postgresql":
            stmt = (
                pg_insert(OpportunitySource)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["slug"])
            )
            db.execute(stmt)
        elif dialect_name == "sqlite":
            stmt = (
                sqlite_insert(OpportunitySource)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["slug"])
            )
            db.execute(stmt)
        else:
            existing = db.execute(
                select(OpportunitySource).where(OpportunitySource.slug == defn.slug)
            ).scalar_one_or_none()
            if existing is None:
                try:
                    with db.begin_nested():
                        db.add(
                            OpportunitySource(
                                slug=defn.slug,
                                name=defn.name,
                                source_type=defn.source_type,
                                base_url=defn.base_url,
                                terms_url=defn.terms_url,
                                attribution_text=defn.attribution_text,
                                enabled=defn.enabled_by_default,
                                refresh_interval_seconds=defn.refresh_interval_seconds,
                            )
                        )
                        db.flush()
                except IntegrityError:
                    pass

    sources: list[OpportunitySource] = []
    for connector_cls in CONNECTOR_CLASSES.values():
        defn = connector_cls.definition
        existing = db.execute(
            select(OpportunitySource).where(OpportunitySource.slug == defn.slug)
        ).scalar_one()
        existing.name = defn.name
        existing.source_type = defn.source_type
        existing.base_url = defn.base_url
        existing.terms_url = defn.terms_url
        existing.attribution_text = defn.attribution_text
        if not defn.enabled_by_default:
            existing.enabled = False
        if existing.refresh_interval_seconds <= 0:
            existing.refresh_interval_seconds = defn.refresh_interval_seconds
        sources.append(existing)
    db.commit()
    return sources


def _is_specific_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    return len(path) >= 4


def _merge_country_lists(existing_list: list[str] | None, new_list: list[str] | None) -> list[str]:
    merged: list[str] = []
    seen_low: set[str] = set()
    for item in list(existing_list or []) + list(new_list or []):
        cleaned = str(item).strip()
        if not cleaned:
            continue
        low = cleaned.lower()
        if low not in seen_low:
            seen_low.add(low)
            merged.append(cleaned)
    if any(c.lower() == "worldwide" for c in merged) and len(merged) > 1:
        # Preserva países explícitos mas mantém Worldwide caso já fosse global
        pass
    return merged


def _regions_compatible_for_cross_source(
    cand: Opportunity,
    draft: NormalizedOpportunityDraft,
) -> bool:
    if cand.work_mode in {"onsite", "hybrid"} or draft.work_mode in {"onsite", "hybrid"}:
        if cand.work_mode != draft.work_mode:
            return False
        cand_cities = {
            normalize_classification_text(c)
            for c in parse_location_cities(cand.city or cand.location_text)[0]
            if c
        }
        draft_cities = {
            normalize_classification_text(c)
            for c in parse_location_cities(draft.city or draft.location_text)[0]
            if c
        }
        if cand_cities and draft_cities and not (cand_cities & draft_cities):
            return False
        cand_country = normalize_classification_text(cand.country)
        draft_country = normalize_classification_text(draft.country)
        if cand_country and draft_country and cand_country != draft_country:
            return False
        return True

    if cand.eligibility_unknown or draft.eligibility_unknown:
        return True

    cand_regions = {
        normalize_classification_text(r)
        for r in (list(cand.eligible_countries or []) + ([cand.country] if cand.country else []))
        if r
    }
    draft_regions = {
        normalize_classification_text(r)
        for r in (list(draft.eligible_countries or []) + ([draft.country] if draft.country else []))
        if r
    }
    if not cand_regions or not draft_regions:
        return True
    if "worldwide" in cand_regions or "worldwide" in draft_regions:
        return True
    if cand_regions & draft_regions:
        return True
    br_syns = {"brasil", "brazil", "latam", "latin america", "south america"}
    if (cand_regions & br_syns) and (draft_regions & br_syns):
        return True
    return False


def _is_safe_composite_match(
    cand: Opportunity,
    draft: NormalizedOpportunityDraft,
    *,
    same_source: bool,
) -> bool:
    """
    Avalia se duas publicações com URLs/IDs diferentes representam a mesma vaga real.
    Nunca considera apenas `(title, company_name)` como prova suficiente sem validar
    senioridade, modalidade, contrato, área, localização e evidência de conteúdo.
    """
    if not cand.company_name or not draft.company_name:
        return False
    norm_cand_comp = normalize_classification_text(cand.company_name)
    norm_draft_comp = normalize_classification_text(draft.company_name)
    if not norm_cand_comp or norm_cand_comp != norm_draft_comp:
        return False

    # 1. Conflito de senioridade / categoria
    if cand.opportunity_type != draft.opportunity_type:
        return False

    # 2. Conflito de modalidade de trabalho (remote vs hybrid vs onsite)
    if cand.work_mode != draft.work_mode:
        return False

    # 3. Conflito de regime contratual explícito (ex.: PJ vs CLT)
    if (
        cand.employment_type != "unknown"
        and draft.employment_type != "unknown"
        and cand.employment_type != draft.employment_type
    ):
        return False

    # 4. Conflito de área profissional
    if (
        cand.professional_area not in {"unknown", ""}
        and draft.professional_area not in {"unknown", ""}
    ):
        cand_areas = {cand.professional_area, *(cand.secondary_areas or [])}
        draft_areas = {draft.professional_area, *(draft.secondary_areas or [])}
        if not (cand_areas & draft_areas):
            return False

    cand_desc_norm = normalize_classification_text((cand.description or "")[:240])
    draft_desc_norm = normalize_classification_text((draft.description or "")[:240])
    has_identical_desc_prefix = (
        len(cand_desc_norm) >= 25
        and len(draft_desc_norm) >= 25
        and cand_desc_norm[:180] == draft_desc_norm[:180]
    )

    if same_source:
        # Dentro da mesma fonte, só unifica se for um clone multi-país/regional
        # com mesmo título-base e mesma descrição substantiva.
        cand_base, cand_geo_sfx = extract_base_title_and_geo_suffix(cand.title)
        draft_base, draft_geo_sfx = extract_base_title_and_geo_suffix(draft.title)
        norm_cand_base = normalize_classification_text(cand_base)
        norm_draft_base = normalize_classification_text(draft_base)
        if not norm_cand_base or norm_cand_base != norm_draft_base:
            return False
        if has_identical_desc_prefix:
            return True
        if (cand_geo_sfx or draft_geo_sfx) and cand_desc_norm == draft_desc_norm:
            return True
        return False

    # Entre fontes diferentes: exige título normalizado compatível e ausência de conflito geográfico
    norm_cand_title = normalize_classification_text(cand.title)
    norm_draft_title = normalize_classification_text(draft.title)
    cand_base = normalize_classification_text(extract_base_title_and_geo_suffix(cand.title)[0])
    draft_base = normalize_classification_text(extract_base_title_and_geo_suffix(draft.title)[0])

    if norm_cand_title != norm_draft_title and cand_base != draft_base:
        return False

    if not _regions_compatible_for_cross_source(cand, draft):
        return False

    if has_identical_desc_prefix:
        return True

    cand_techs = {normalize_classification_text(t) for t in (cand.technologies or []) if t}
    draft_techs = {normalize_classification_text(t) for t in (draft.technologies or []) if t}
    if len(cand_techs & draft_techs) >= 1 and len(norm_draft_title.split()) >= 3:
        return True

    # Títulos altamente específicos (ex.: "[Belo Horizonte, Brasil] Senior Software Engineer, Full Stack, Kids and Families na Google")
    if len(norm_draft_title.split()) >= 5 and norm_cand_title == norm_draft_title:
        return True

    return False


def _find_existing_opportunity(
    db: Session,
    source: OpportunitySource,
    draft: NormalizedOpportunityDraft,
    content_hash: str,
) -> tuple[Opportunity | None, OpportunitySourceLink | None, str]:
    """
    Localiza oportunidade existente e retorna `(opportunity, matched_link, match_kind)`.
    `match_kind` pode ser:
    - 'none'
    - 'link_ext_id' (mesmo source_id + external_id em OpportunitySourceLink)
    - 'opp_ext_id' (mesmo source_id + external_id em Opportunity)
    - 'same_source_url' (mesma source_url na mesma fonte)
    - 'same_source_hash' (mesmo content_hash na mesma fonte)
    - 'intra_source_clone' (clone regional na mesma fonte)
    - 'cross_source' (publicação correspondente em outra fonte)
    """
    # 1. Vínculo exato por (source_id, external_id)
    link = db.execute(
        select(OpportunitySourceLink)
        .options(selectinload(OpportunitySourceLink.opportunity))
        .where(
            OpportunitySourceLink.source_id == source.id,
            OpportunitySourceLink.external_id == draft.external_id,
        )
    ).scalar_one_or_none()
    if link is not None and link.opportunity is not None:
        return (link.opportunity, link, "link_ext_id")

    opp = db.execute(
        select(Opportunity).where(
            Opportunity.source_id == source.id,
            Opportunity.external_id == draft.external_id,
        )
    ).scalar_one_or_none()
    if opp is not None:
        return (opp, None, "opp_ext_id")

    # 2. URL canônica na mesma fonte
    link_by_url = (
        db.execute(
            select(OpportunitySourceLink)
            .options(selectinload(OpportunitySourceLink.opportunity))
            .where(
                OpportunitySourceLink.source_id == source.id,
                OpportunitySourceLink.source_url == draft.source_url,
            )
        )
        .scalars()
        .first()
    )
    if link_by_url is not None and link_by_url.opportunity is not None:
        return (link_by_url.opportunity, link_by_url, "same_source_url")

    opp = db.execute(
        select(Opportunity).where(
            Opportunity.source_id == source.id,
            Opportunity.source_url == draft.source_url,
        )
    ).scalar_one_or_none()
    if opp is not None:
        return (opp, None, "same_source_url")

    # 3. Content hash idêntico na mesma fonte
    opp = db.execute(
        select(Opportunity).where(
            Opportunity.source_id == source.id,
            Opportunity.content_hash == content_hash,
        )
    ).scalar_one_or_none()
    if opp is not None:
        return (opp, None, "same_source_hash")

    # 4. Igualdade de URLs entre fontes distintas
    if _is_specific_url(draft.application_url):
        opp = (
            db.execute(
                select(Opportunity).where(
                    Opportunity.source_id.is_not(None),
                    Opportunity.application_url == draft.application_url,
                )
            )
            .scalars()
            .first()
        )
        if opp is not None:
            kind = "intra_source_clone" if opp.source_id == source.id else "cross_source"
            return (opp, None, kind)

        link_apply = (
            db.execute(
                select(OpportunitySourceLink)
                .options(selectinload(OpportunitySourceLink.opportunity))
                .where(OpportunitySourceLink.application_url == draft.application_url)
            )
            .scalars()
            .first()
        )
        if link_apply is not None and link_apply.opportunity is not None:
            opp_match = link_apply.opportunity
            kind = "intra_source_clone" if opp_match.source_id == source.id else "cross_source"
            return (opp_match, link_apply if link_apply.source_id == source.id else None, kind)

    opp = (
        db.execute(
            select(Opportunity).where(
                Opportunity.source_id.is_not(None),
                Opportunity.source_url == draft.source_url,
            )
        )
        .scalars()
        .first()
    )
    if opp is not None:
        kind = "same_source_url" if opp.source_id == source.id else "cross_source"
        return (opp, None, kind)

    # 5. Identidade composta segura (intra-source multi-country clone ou cross-source corroborado)
    if draft.company_name and draft.company_name.strip():
        candidates = (
            db.execute(
                select(Opportunity).where(
                    Opportunity.source_id.is_not(None),
                    Opportunity.company_name.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        for cand in candidates:
            same_source = cand.source_id == source.id
            if _is_safe_composite_match(cand, draft, same_source=same_source):
                return (
                    cand,
                    None,
                    "intra_source_clone" if same_source else "cross_source",
                )

    return (None, None, "none")


def _upsert_source_link(
    db: Session,
    *,
    opp: Opportunity,
    source: OpportunitySource,
    draft: NormalizedOpportunityDraft,
    now: datetime,
    is_primary: bool,
    existing_link: OpportunitySourceLink | None = None,
) -> OpportunitySourceLink:
    link = existing_link
    if link is None:
        link = db.execute(
            select(OpportunitySourceLink).where(
                OpportunitySourceLink.source_id == source.id,
                OpportunitySourceLink.external_id == draft.external_id,
            )
        ).scalar_one_or_none()

    if link is None:
        link = OpportunitySourceLink(
            opportunity_id=opp.id,
            source_id=source.id,
            external_id=draft.external_id,
            source_url=draft.source_url,
            application_url=draft.application_url,
            is_primary=is_primary,
            source_status=draft.source_status,
            published_at=draft.published_at,
            deadline_at=draft.deadline_at,
            location_text=draft.location_text,
            eligible_countries=list(draft.eligible_countries or []),
            salary_min=draft.salary_min,
            salary_max=draft.salary_max,
            salary_currency=draft.salary_currency,
            salary_period=draft.salary_period,
            first_seen_at=now,
            last_seen_at=now,
            last_checked_at=now,
            missing_sync_count=0,
            raw_metadata=dict(draft.raw_metadata or {}),
        )
        db.add(link)
        db.flush()
        return link

    link.opportunity_id = opp.id
    link.source_url = draft.source_url
    link.application_url = draft.application_url
    if is_primary:
        link.is_primary = True
    link.source_status = draft.source_status
    if draft.published_at is not None:
        link.published_at = draft.published_at
    link.deadline_at = draft.deadline_at
    link.location_text = draft.location_text
    link.eligible_countries = list(draft.eligible_countries or [])
    link.salary_min = draft.salary_min
    link.salary_max = draft.salary_max
    link.salary_currency = draft.salary_currency
    link.salary_period = draft.salary_period
    link.last_seen_at = now
    link.last_checked_at = now
    link.missing_sync_count = 0
    link.raw_metadata = dict(draft.raw_metadata or {})
    db.flush()
    return link


def _recompute_opportunity_lifecycle(opp: Opportunity, now: datetime) -> None:
    links = list(opp.source_links or [])
    if not links:
        if is_deadline_expired(opp.deadline_at, now=now):
            opp.source_status = ExternalSourceStatus.EXPIRED.value
        return

    for link in links:
        if (
            is_deadline_expired(link.deadline_at, now=now)
            and link.source_status == ExternalSourceStatus.ACTIVE.value
        ):
            link.source_status = ExternalSourceStatus.EXPIRED.value

    statuses = {link.source_status for link in links}
    if ExternalSourceStatus.ACTIVE.value in statuses:
        opp.source_status = ExternalSourceStatus.ACTIVE.value
    elif ExternalSourceStatus.UNKNOWN.value in statuses or ExternalSourceStatus.UNCONFIRMED.value in statuses:
        opp.source_status = ExternalSourceStatus.UNKNOWN.value
    elif ExternalSourceStatus.EXPIRED.value in statuses:
        opp.source_status = ExternalSourceStatus.EXPIRED.value
    elif ExternalSourceStatus.CLOSED.value in statuses:
        opp.source_status = ExternalSourceStatus.CLOSED.value
    elif ExternalSourceStatus.REMOVED.value in statuses:
        opp.source_status = ExternalSourceStatus.REMOVED.value

    primary_links = [l for l in links if l.is_primary]
    ref_link = primary_links[0] if primary_links else links[0]
    opp.missing_sync_count = ref_link.missing_sync_count
    opp.last_status_check_at = now


def _merge_secondary_metadata_into_opportunity(
    existing: Opportunity,
    source: OpportunitySource,
    draft: NormalizedOpportunityDraft,
    now: datetime,
) -> None:
    existing.last_seen_at = now
    existing.last_status_check_at = now

    merged_techs = list(existing.technologies or [])
    for tech in draft.technologies or []:
        if tech not in merged_techs:
            merged_techs.append(tech)
    existing.technologies = merged_techs

    # Mescla países elegíveis quando a oportunidade é remota para não descartar elegibilidade geográfica
    if existing.work_mode == "remote" and draft.work_mode == "remote":
        merged_countries = _merge_country_lists(
            existing.eligible_countries, draft.eligible_countries
        )
        if merged_countries != list(existing.eligible_countries or []):
            existing.eligible_countries = merged_countries
            existing.eligibility_unknown = False
            if len(merged_countries) == 1:
                existing.country = merged_countries[0]
            elif existing.location_text and "worldwide" not in existing.location_text.lower():
                existing.location_text = ", ".join(merged_countries[:6])

    if existing.salary_min is None and draft.salary_min is not None:
        existing.salary_min = draft.salary_min
        existing.salary_max = draft.salary_max
        existing.salary_currency = draft.salary_currency
        existing.salary_period = draft.salary_period

    meta = dict(existing.raw_metadata or {})
    if existing.source_id != source.id:
        also_seen = list(meta.get("also_seen_in_sources") or [])
        if source.slug not in also_seen:
            also_seen.append(source.slug)
        meta["also_seen_in_sources"] = also_seen
    existing.raw_metadata = meta


def _upsert_opportunity(
    db: Session,
    source: OpportunitySource,
    draft: NormalizedOpportunityDraft,
    now: datetime,
    seen_opp_ids_in_run: set,
) -> tuple[Opportunity, OpportunitySourceLink, UpsertOutcome]:
    content_hash = compute_opportunity_content_hash(
        title=draft.title,
        company_name=draft.company_name,
        source_url=draft.source_url,
        work_mode=draft.work_mode,
        employment_type=draft.employment_type,
        location_text=draft.location_text,
        description=draft.description,
    )

    existing, matched_link, match_kind = _find_existing_opportunity(
        db, source, draft, content_hash
    )
    if existing is None:
        opp = Opportunity(
            source_id=source.id,
            created_by_user_id=None,
            external_id=draft.external_id,
            title=draft.title,
            company_name=draft.company_name,
            description=draft.description,
            opportunity_type=draft.opportunity_type,
            seniority_level=draft.seniority_level,
            experience_requirement_mode=draft.experience_requirement_mode,
            experience_min_years=draft.experience_min_years,
            experience_preferred_years=draft.experience_preferred_years,
            experience_summary=draft.experience_summary,
            employment_type=draft.employment_type,
            work_mode=draft.work_mode,
            professional_area=draft.professional_area,
            secondary_areas=draft.secondary_areas,
            location_text=draft.location_text,
            city=draft.city,
            state=draft.state,
            country=draft.country,
            eligible_countries=draft.eligible_countries,
            eligibility_unknown=draft.eligibility_unknown,
            language=draft.language,
            salary_min=draft.salary_min,
            salary_max=draft.salary_max,
            salary_currency=draft.salary_currency,
            salary_period=draft.salary_period,
            requirements=draft.requirements,
            technologies=draft.technologies,
            source_url=draft.source_url,
            application_url=draft.application_url,
            published_at=draft.published_at,
            deadline_at=draft.deadline_at,
            source_status=draft.source_status,
            first_seen_at=now,
            last_seen_at=now,
            last_status_check_at=now,
            missing_sync_count=0,
            content_hash=content_hash,
            raw_metadata=draft.raw_metadata,
        )
        db.add(opp)
        db.flush()
        link = _upsert_source_link(
            db,
            opp=opp,
            source=source,
            draft=draft,
            now=now,
            is_primary=True,
        )
        return (opp, link, UpsertOutcome.INSERTED)

    # Caso 1: Deduplicação entre fontes distintas (cross-source)
    if existing.source_id != source.id or match_kind == "cross_source":
        # Garante que a oportunidade existente já tenha seu link primário registrado
        primary_exists = db.execute(
            select(OpportunitySourceLink).where(
                OpportunitySourceLink.opportunity_id == existing.id,
                OpportunitySourceLink.is_primary.is_(True),
            )
        ).scalar_one_or_none()
        if primary_exists is None and existing.source_id is not None:
            db.add(
                OpportunitySourceLink(
                    opportunity_id=existing.id,
                    source_id=existing.source_id,
                    external_id=str(existing.external_id or existing.id),
                    source_url=existing.source_url,
                    application_url=existing.application_url,
                    is_primary=True,
                    source_status=existing.source_status,
                    published_at=existing.published_at,
                    deadline_at=existing.deadline_at,
                    location_text=existing.location_text,
                    eligible_countries=list(existing.eligible_countries or []),
                    salary_min=existing.salary_min,
                    salary_max=existing.salary_max,
                    salary_currency=existing.salary_currency,
                    salary_period=existing.salary_period,
                    first_seen_at=existing.first_seen_at,
                    last_seen_at=existing.last_seen_at,
                    last_checked_at=existing.last_status_check_at or existing.last_seen_at,
                    missing_sync_count=existing.missing_sync_count,
                    raw_metadata=dict(existing.raw_metadata or {}),
                )
            )
            db.flush()

        _merge_secondary_metadata_into_opportunity(existing, source, draft, now)
        link = _upsert_source_link(
            db,
            opp=existing,
            source=source,
            draft=draft,
            now=now,
            is_primary=False,
            existing_link=matched_link,
        )
        db.refresh(existing, attribute_names=["source_links"])
        _recompute_opportunity_lifecycle(existing, now)
        return (existing, link, UpsertOutcome.CROSS_SOURCE_DUPLICATE)

    # Caso 2: Duplicata dentro da mesma fonte (clone multi-país no mesmo lote ou vínculo secundário da mesma fonte)
    is_secondary_same_source = (
        existing.id in seen_opp_ids_in_run
        or match_kind == "intra_source_clone"
        or (matched_link is not None and not matched_link.is_primary)
    )
    if is_secondary_same_source:
        _merge_secondary_metadata_into_opportunity(existing, source, draft, now)
        link = _upsert_source_link(
            db,
            opp=existing,
            source=source,
            draft=draft,
            now=now,
            is_primary=False,
            existing_link=matched_link,
        )
        db.refresh(existing, attribute_names=["source_links"])
        _recompute_opportunity_lifecycle(existing, now)
        return (existing, link, UpsertOutcome.INTRA_SOURCE_DUPLICATE)

    # Caso 3: Atualização da publicação primária na mesma fonte
    old_ext_id = existing.external_id
    existing.external_id = draft.external_id
    existing.title = draft.title
    existing.company_name = draft.company_name
    existing.description = draft.description
    existing.opportunity_type = draft.opportunity_type
    existing.seniority_level = draft.seniority_level
    existing.experience_requirement_mode = draft.experience_requirement_mode
    existing.experience_min_years = draft.experience_min_years
    existing.experience_preferred_years = draft.experience_preferred_years
    existing.experience_summary = draft.experience_summary
    existing.employment_type = draft.employment_type
    existing.work_mode = draft.work_mode
    existing.professional_area = draft.professional_area
    existing.secondary_areas = draft.secondary_areas
    existing.location_text = draft.location_text
    existing.city = draft.city
    existing.state = draft.state
    existing.country = draft.country
    existing.eligible_countries = _merge_country_lists(
        draft.eligible_countries, existing.eligible_countries
    )
    existing.eligibility_unknown = draft.eligibility_unknown
    existing.language = draft.language
    existing.salary_min = draft.salary_min
    existing.salary_max = draft.salary_max
    existing.salary_currency = draft.salary_currency
    existing.salary_period = draft.salary_period
    existing.requirements = draft.requirements
    existing.technologies = draft.technologies
    existing.source_url = draft.source_url
    existing.application_url = draft.application_url
    if draft.published_at is not None:
        existing.published_at = draft.published_at
    existing.deadline_at = draft.deadline_at
    existing.source_status = draft.source_status
    existing.last_seen_at = now
    existing.last_status_check_at = now
    existing.missing_sync_count = 0
    existing.content_hash = content_hash

    preserved_also_seen = (existing.raw_metadata or {}).get("also_seen_in_sources")
    new_meta = dict(draft.raw_metadata or {})
    if preserved_also_seen:
        new_meta["also_seen_in_sources"] = preserved_also_seen
    existing.raw_metadata = new_meta

    if matched_link is None and old_ext_id:
        matched_link = db.execute(
            select(OpportunitySourceLink).where(
                OpportunitySourceLink.source_id == source.id,
                OpportunitySourceLink.external_id == old_ext_id,
            )
        ).scalar_one_or_none()
        if matched_link is not None:
            matched_link.external_id = draft.external_id

    link = _upsert_source_link(
        db,
        opp=existing,
        source=source,
        draft=draft,
        now=now,
        is_primary=True,
        existing_link=matched_link,
    )
    db.refresh(existing, attribute_names=["source_links"])
    _recompute_opportunity_lifecycle(existing, now)
    return (existing, link, UpsertOutcome.UPDATED)


def _apply_lifecycle_signals(
    db: Session,
    source: OpportunitySource,
    signals: list[SourceLifecycleSignal],
    seen_link_ids: set,
    seen_opp_ids: set,
    now: datetime,
) -> int:
    """
    Aplica sinais explícitos de encerramento/expiração vindos da própria fonte
    (ex.: issue fechada/Stale no GitHub ou vaga expirada na Himalayas) sobre registros
    já existentes no catálogo. Retorna quantos registros existentes foram atualizados.
    """
    applied_updates = 0
    for sig in signals:
        link = db.execute(
            select(OpportunitySourceLink)
            .options(selectinload(OpportunitySourceLink.opportunity))
            .where(
                OpportunitySourceLink.source_id == source.id,
                OpportunitySourceLink.external_id == sig.external_id,
            )
        ).scalar_one_or_none()
        if link is None:
            link = (
                db.execute(
                    select(OpportunitySourceLink)
                    .options(selectinload(OpportunitySourceLink.opportunity))
                    .where(
                        OpportunitySourceLink.source_id == source.id,
                        OpportunitySourceLink.source_url == sig.source_url,
                    )
                )
                .scalars()
                .first()
            )
        if link is not None and link.opportunity is not None:
            link.source_status = sig.status
            if sig.deadline_at is not None:
                link.deadline_at = sig.deadline_at
            link.last_checked_at = now
            seen_link_ids.add(link.id)
            opp = link.opportunity
            seen_opp_ids.add(opp.id)
            db.refresh(opp, attribute_names=["source_links"])
            _recompute_opportunity_lifecycle(opp, now)
            applied_updates += 1
            continue

        opp = db.execute(
            select(Opportunity).where(
                Opportunity.source_id == source.id,
                Opportunity.external_id == sig.external_id,
            )
        ).scalar_one_or_none()
        if opp is not None:
            opp.source_status = sig.status
            if sig.deadline_at is not None:
                opp.deadline_at = sig.deadline_at
            opp.last_status_check_at = now
            seen_opp_ids.add(opp.id)
            applied_updates += 1

    return applied_updates


def _update_absent_opportunities(
    db: Session,
    source: OpportunitySource,
    connector: BaseOpportunityConnector,
    seen_link_ids: set,
    seen_opp_ids: set,
    now: datetime,
) -> None:
    if not seen_opp_ids and not seen_link_ids:
        return

    # 1. Atualiza links ativos desta fonte que estiveram ausentes do lote atual
    active_links = (
        db.execute(
            select(OpportunitySourceLink)
            .options(selectinload(OpportunitySourceLink.opportunity))
            .where(
                OpportunitySourceLink.source_id == source.id,
                OpportunitySourceLink.source_status == ExternalSourceStatus.ACTIVE.value,
            )
        )
        .scalars()
        .all()
    )

    revalidation_budget = 5
    touched_opps: dict = {}

    absent_links: list[OpportunitySourceLink] = []
    for link in active_links:
        if link.id in seen_link_ids:
            continue
        link.last_checked_at = now
        if is_deadline_expired(link.deadline_at, now=now):
            link.missing_sync_count += 1
            link.source_status = ExternalSourceStatus.EXPIRED.value
            if link.opportunity is not None:
                touched_opps[link.opportunity.id] = link.opportunity
            continue
        absent_links.append(link)

    # Tenta revalidação em lote quando o conector suportar (ex.: Jobicy /api/jobs/status?ids=...)
    batch_signals: dict[str, SourceLifecycleSignal] = {}
    if absent_links:
        batch_result = connector.check_publications_status_batch(
            [
                (
                    link.external_id,
                    link.source_url,
                    link.raw_metadata if isinstance(link.raw_metadata, dict) else None,
                )
                for link in absent_links[:100]
            ]
        )
        if batch_result:
            batch_signals = batch_result

    for link in absent_links:
        signal: SourceLifecycleSignal | None = batch_signals.get(link.external_id)
        if signal is None and not batch_signals and revalidation_budget > 0:
            revalidation_budget -= 1
            signal = connector.check_publication_status(
                link.external_id,
                link.source_url,
                link.raw_metadata if isinstance(link.raw_metadata, dict) else None,
            )

        if signal is not None:
            link.source_status = signal.status
            if signal.status == ExternalSourceStatus.ACTIVE.value:
                link.missing_sync_count = 0
            else:
                link.missing_sync_count += 1
        else:
            link.missing_sync_count += 1
            if link.missing_sync_count >= 3:
                link.source_status = ExternalSourceStatus.UNKNOWN.value

        if link.opportunity is not None:
            touched_opps[link.opportunity.id] = link.opportunity

    for opp in touched_opps.values():
        db.refresh(opp, attribute_names=["source_links"])
        _recompute_opportunity_lifecycle(opp, now)

    # 2. Compatibilidade com oportunidades sem link explícito (ex.: fixtures legadas)
    active_opps = (
        db.execute(
            select(Opportunity)
            .options(selectinload(Opportunity.source_links))
            .where(
                Opportunity.source_id == source.id,
                Opportunity.source_status == ExternalSourceStatus.ACTIVE.value,
            )
        )
        .scalars()
        .all()
    )
    for opp in active_opps:
        if opp.id in seen_opp_ids or opp.id in touched_opps:
            continue
        if opp.source_links:
            continue
        opp.last_status_check_at = now
        opp.missing_sync_count += 1
        if is_deadline_expired(opp.deadline_at, now=now):
            opp.source_status = ExternalSourceStatus.EXPIRED.value
        elif opp.missing_sync_count >= 3:
            opp.source_status = ExternalSourceStatus.UNKNOWN.value


def _compute_source_catalog_counts(
    db: Session,
    source_id,
    *,
    now: datetime | None = None,
) -> tuple[int, int, int, int]:
    """Retorna `(unique_count, open_count, closed_or_expired_count, unconfirmed_count)`."""
    reference_now = ensure_utc(now) or utc_now()
    opps = (
        db.execute(
            select(Opportunity.source_status, Opportunity.deadline_at).where(
                Opportunity.source_id == source_id
            )
        )
        .all()
    )
    unique_count = len(opps)
    open_count = 0
    closed_or_expired_count = 0
    unconfirmed_count = 0
    for raw_st, deadline_at in opps:
        st = (raw_st or "active").lower()
        if (
            st
            not in {
                ExternalSourceStatus.EXPIRED.value,
                ExternalSourceStatus.CLOSED.value,
                ExternalSourceStatus.REMOVED.value,
            }
            and is_deadline_expired(deadline_at, now=reference_now)
        ):
            st = ExternalSourceStatus.EXPIRED.value
        if st == ExternalSourceStatus.ACTIVE.value:
            open_count += 1
        elif st in {
            ExternalSourceStatus.EXPIRED.value,
            ExternalSourceStatus.CLOSED.value,
            ExternalSourceStatus.REMOVED.value,
        }:
            closed_or_expired_count += 1
        else:
            unconfirmed_count += 1
    return (unique_count, open_count, closed_or_expired_count, unconfirmed_count)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    return ensure_utc(dt)


def sync_sources(
    db: Session,
    *,
    source_slug: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    connector_overrides: Mapping[str, BaseOpportunityConnector] | None = None,
) -> list[SyncRunSummary]:
    """
    Executa coleta, validação, deduplicação e atualização de ciclo de vida.
    Quando `dry_run=True`, executa estritamente em modo somente leitura:
    não inicializa fontes padrão, não grava `OpportunitySyncRun`, não altera
    registros e não executa `COMMIT` nem `FLUSH`.
    """
    if not dry_run:
        ensure_default_sources(db)

    query = select(OpportunitySource).order_by(OpportunitySource.slug.asc())
    if source_slug:
        query = query.where(OpportunitySource.slug == source_slug.strip().lower())
    else:
        query = query.where(OpportunitySource.enabled.is_(True))

    sources = db.execute(query).scalars().all()
    if not sources:
        if dry_run:
            any_source = db.execute(select(OpportunitySource.id).limit(1)).scalar_one_or_none()
            if any_source is None:
                raise ValueError(
                    "Fontes padrão ainda não foram inicializadas no banco de dados. "
                    "Execute 'python -m app.cli init-sources' antes de rodar em modo --dry-run."
                )
        if source_slug:
            raise ValueError(f"Fonte '{source_slug}' não encontrada no catálogo.")

    if connector_overrides is not None and not source_slug:
        sources = [s for s in sources if s.slug in connector_overrides]

    summaries: list[SyncRunSummary] = []

    for source in sources:
        started_at = utc_now()
        connector: BaseOpportunityConnector | None = None
        if connector_overrides and source.slug in connector_overrides:
            connector = connector_overrides[source.slug]
        elif source.slug in CONNECTOR_CLASSES:
            connector = CONNECTOR_CLASSES[source.slug]()

        if connector is None:
            err_msg = "Nenhum conector registrado para esta fonte."
            if not dry_run:
                run = OpportunitySyncRun(
                    source_id=source.id,
                    status=SyncRunStatus.SKIPPED.value,
                    started_at=started_at,
                    finished_at=utc_now(),
                    error_summary=err_msg,
                )
                db.add(run)
                db.commit()
            summaries.append(
                SyncRunSummary(
                    source_slug=source.slug,
                    status=SyncRunStatus.SKIPPED.value,
                    error_summary=err_msg,
                )
            )
            continue

        if not source.enabled or not connector.definition.enabled_by_default:
            disabled_msg = (
                connector.definition.disabled_reason
                or f"A fonte '{source.slug}' está desabilitada e não pode ser sincronizada."
            )
            if source_slug:
                raise ValueError(disabled_msg)
            if not dry_run:
                run = OpportunitySyncRun(
                    source_id=source.id,
                    status=SyncRunStatus.SKIPPED.value,
                    started_at=started_at,
                    finished_at=utc_now(),
                    error_summary=disabled_msg,
                )
                db.add(run)
                db.commit()
            summaries.append(
                SyncRunSummary(
                    source_slug=source.slug,
                    status=SyncRunStatus.SKIPPED.value,
                    error_summary=disabled_msg,
                )
            )
            continue

        last_synced = _ensure_utc(source.last_synced_at)
        if not force and last_synced is not None:
            next_allowed = last_synced + timedelta(
                seconds=source.refresh_interval_seconds
            )
            if started_at < next_allowed:
                msg = (
                    f"Intervalo mínimo de atualização respeitado "
                    f"({source.refresh_interval_seconds}s)."
                )
                u_cnt, o_cnt, c_cnt, unc_cnt = _compute_source_catalog_counts(
                    db, source.id, now=started_at
                )
                if not dry_run:
                    run = OpportunitySyncRun(
                        source_id=source.id,
                        status=SyncRunStatus.SKIPPED.value,
                        started_at=started_at,
                        finished_at=utc_now(),
                        unique_opportunities_count=u_cnt,
                        open_opportunities_count=o_cnt,
                        closed_or_expired_count=c_cnt,
                        unconfirmed_count=unc_cnt,
                        error_summary=msg,
                    )
                    db.add(run)
                    db.commit()
                summaries.append(
                    SyncRunSummary(
                        source_slug=source.slug,
                        status=SyncRunStatus.SKIPPED.value,
                        unique_opportunities_count=u_cnt,
                        open_opportunities_count=o_cnt,
                        closed_or_expired_count=c_cnt,
                        unconfirmed_count=unc_cnt,
                        error_summary=msg,
                    )
                )
                continue

        try:
            batch = connector.collect_batch()
            drafts = batch.valid_drafts
        except (ConnectorError, Exception) as exc:
            error_msg = (
                str(exc)[:480]
                if isinstance(exc, ConnectorError)
                else f"Erro inesperado no conector ({type(exc).__name__})."
            )
            finished_at = utc_now()
            u_cnt, o_cnt, c_cnt, unc_cnt = _compute_source_catalog_counts(
                db, source.id, now=finished_at
            )
            if not dry_run:
                source.last_synced_at = finished_at
                source.last_error_at = finished_at
                source.last_error_summary = error_msg
                run = OpportunitySyncRun(
                    source_id=source.id,
                    status=SyncRunStatus.FAILED.value,
                    started_at=started_at,
                    finished_at=finished_at,
                    unique_opportunities_count=u_cnt,
                    open_opportunities_count=o_cnt,
                    closed_or_expired_count=c_cnt,
                    unconfirmed_count=unc_cnt,
                    error_summary=error_msg,
                )
                db.add(run)
                db.commit()
            summaries.append(
                SyncRunSummary(
                    source_slug=source.slug,
                    status=SyncRunStatus.FAILED.value,
                    unique_opportunities_count=u_cnt,
                    open_opportunities_count=o_cnt,
                    closed_or_expired_count=c_cnt,
                    unconfirmed_count=unc_cnt,
                    error_summary=error_msg,
                )
            )
            continue

        valid_count = len(drafts)
        received_count = batch.received_count or (valid_count + batch.rejected_count)
        rejected_count = batch.rejected_count
        fetched_count = valid_count

        if dry_run:
            # Modo dry-run estritamente sem escrita: nenhum INSERT, UPDATE, DELETE, FLUSH ou COMMIT.
            u_cnt, o_cnt, c_cnt, unc_cnt = _compute_source_catalog_counts(
                db, source.id, now=started_at
            )
            summaries.append(
                SyncRunSummary(
                    source_slug=source.slug,
                    status=SyncRunStatus.DRY_RUN.value,
                    received_count=received_count,
                    valid_count=valid_count,
                    rejected_count=rejected_count,
                    fetched_count=fetched_count,
                    skipped_count=fetched_count,
                    unique_opportunities_count=u_cnt,
                    open_opportunities_count=o_cnt,
                    closed_or_expired_count=c_cnt,
                    unconfirmed_count=unc_cnt,
                )
            )
            continue

        inserted_count = 0
        updated_count = 0
        intra_dup_count = 0
        cross_dup_count = 0
        seen_opp_ids: set = set()
        seen_link_ids: set = set()
        now = datetime.now(UTC)

        try:
            for draft in drafts:
                opp, link, outcome = _upsert_opportunity(
                    db, source, draft, now, seen_opp_ids
                )
                seen_opp_ids.add(opp.id)
                seen_link_ids.add(link.id)
                if outcome == UpsertOutcome.INSERTED:
                    inserted_count += 1
                elif outcome == UpsertOutcome.UPDATED:
                    updated_count += 1
                elif outcome == UpsertOutcome.INTRA_SOURCE_DUPLICATE:
                    intra_dup_count += 1
                elif outcome == UpsertOutcome.CROSS_SOURCE_DUPLICATE:
                    cross_dup_count += 1

            signal_updates = _apply_lifecycle_signals(
                db,
                source,
                batch.lifecycle_signals,
                seen_link_ids,
                seen_opp_ids,
                now,
            )
            if signal_updates > 0:
                updated_count += signal_updates
                valid_count += signal_updates
                fetched_count = valid_count
                rejected_count = max(0, rejected_count - signal_updates)

            _update_absent_opportunities(
                db,
                source,
                connector,
                seen_link_ids,
                seen_opp_ids,
                now,
            )

            db.flush()
            u_cnt, o_cnt, c_cnt, unc_cnt = _compute_source_catalog_counts(db, source.id)

            finished_at = datetime.now(UTC)
            source.last_synced_at = finished_at
            source.last_success_at = finished_at
            source.last_error_summary = None

            run = OpportunitySyncRun(
                source_id=source.id,
                status=SyncRunStatus.SUCCESS.value,
                started_at=started_at,
                finished_at=finished_at,
                fetched_count=fetched_count,
                received_count=received_count,
                valid_count=valid_count,
                rejected_count=rejected_count,
                inserted_count=inserted_count,
                updated_count=updated_count,
                intra_source_duplicate_count=intra_dup_count,
                cross_source_duplicate_count=cross_dup_count,
                skipped_count=rejected_count + intra_dup_count + cross_dup_count,
                unique_opportunities_count=u_cnt,
                open_opportunities_count=o_cnt,
                closed_or_expired_count=c_cnt,
                unconfirmed_count=unc_cnt,
            )
            db.add(run)
            db.commit()
        except Exception as exc:
            db.rollback()
            finished_at = datetime.now(UTC)
            err = f"Erro transacional durante persistência da coleta ({type(exc).__name__})."
            source_db = db.get(OpportunitySource, source.id)
            if source_db is not None:
                source_db.last_synced_at = finished_at
                source_db.last_error_at = finished_at
                source_db.last_error_summary = err
            u_cnt, o_cnt, c_cnt, unc_cnt = _compute_source_catalog_counts(db, source.id)
            db.add(
                OpportunitySyncRun(
                    source_id=source.id,
                    status=SyncRunStatus.FAILED.value,
                    started_at=started_at,
                    finished_at=finished_at,
                    unique_opportunities_count=u_cnt,
                    open_opportunities_count=o_cnt,
                    closed_or_expired_count=c_cnt,
                    unconfirmed_count=unc_cnt,
                    error_summary=err,
                )
            )
            db.commit()
            summaries.append(
                SyncRunSummary(
                    source_slug=source.slug,
                    status=SyncRunStatus.FAILED.value,
                    unique_opportunities_count=u_cnt,
                    open_opportunities_count=o_cnt,
                    closed_or_expired_count=c_cnt,
                    unconfirmed_count=unc_cnt,
                    error_summary=err,
                )
            )
            continue

        summaries.append(
            SyncRunSummary(
                source_slug=source.slug,
                status=SyncRunStatus.SUCCESS.value,
                received_count=received_count,
                valid_count=valid_count,
                rejected_count=rejected_count,
                fetched_count=fetched_count,
                inserted_count=inserted_count,
                updated_count=updated_count,
                intra_source_duplicate_count=intra_dup_count,
                cross_source_duplicate_count=cross_dup_count,
                skipped_count=rejected_count + intra_dup_count + cross_dup_count,
                unique_opportunities_count=u_cnt,
                open_opportunities_count=o_cnt,
                closed_or_expired_count=c_cnt,
                unconfirmed_count=unc_cnt,
            )
        )

    return summaries


@dataclass(frozen=True, slots=True)
class ReclassificationChange:
    opportunity_id: str
    title: str
    old_opportunity_type: str
    new_opportunity_type: str
    old_employment_type: str
    new_employment_type: str
    old_professional_area: str = "unknown"
    new_professional_area: str = "unknown"
    old_secondary_areas: tuple[str, ...] = ()
    new_secondary_areas: tuple[str, ...] = ()
    old_seniority_level: str = "unknown"
    new_seniority_level: str = "unknown"
    old_experience_mode: str = "not_specified"
    new_experience_mode: str = "not_specified"
    old_experience_min_years: int | None = None
    new_experience_min_years: int | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReclassificationReport:
    source_slug: str | None
    dry_run: bool
    evaluated_count: int
    updated_count: int
    unchanged_count: int
    before_counts: dict[str, int]
    after_counts: dict[str, int]
    changes: tuple[ReclassificationChange, ...]
    before_area_counts: dict[str, int] | None = None
    after_area_counts: dict[str, int] | None = None
    before_seniority_counts: dict[str, int] | None = None
    after_seniority_counts: dict[str, int] | None = None
    before_experience_counts: dict[str, int] | None = None
    after_experience_counts: dict[str, int] | None = None


def reclassify_opportunities(
    db: Session,
    *,
    source_slug: str | None = None,
    dry_run: bool = False,
) -> ReclassificationReport:
    """
    Reavalia deterministicamente `opportunity_type`, `employment_type`, `professional_area`
    e `secondary_areas` de registros já persistidos de fontes externas habilitadas sem
    alterar cadastros manuais, metadados originais, histórico temporal ou estados do usuário.
    """
    if not dry_run:
        ensure_default_sources(db)

    if source_slug:
        normalized_slug = source_slug.strip().lower()
        source = db.execute(
            select(OpportunitySource).where(OpportunitySource.slug == normalized_slug)
        ).scalar_one_or_none()
        if source is None:
            raise ValueError(f"Fonte '{source_slug}' não encontrada no catálogo.")
        if not source.enabled:
            raise ValueError(
                f"Fonte '{source.slug}' está desabilitada e não pode ser reclassificada por este comando."
            )
        target_source_ids = [source.id]
        resolved_slug: str | None = source.slug
    else:
        enabled_sources = (
            db.execute(
                select(OpportunitySource)
                .where(OpportunitySource.enabled.is_(True))
                .order_by(OpportunitySource.slug)
            )
            .scalars()
            .all()
        )
        if not enabled_sources:
            raise ValueError("Nenhuma fonte externa habilitada encontrada para reclassificação.")
        target_source_ids = [s.id for s in enabled_sources]
        resolved_slug = None

    opportunities = (
        db.execute(
            select(Opportunity)
            .options(selectinload(Opportunity.source))
            .where(
                Opportunity.source_id.is_not(None),
                Opportunity.source_id.in_(target_source_ids),
            )
            .order_by(Opportunity.created_at, Opportunity.id)
        )
        .scalars()
        .all()
    )

    before_counter: Counter[str] = Counter()
    after_counter: Counter[str] = Counter()
    before_area_counter: Counter[str] = Counter()
    after_area_counter: Counter[str] = Counter()
    before_seniority_counter: Counter[str] = Counter()
    after_seniority_counter: Counter[str] = Counter()
    before_exp_counter: Counter[str] = Counter()
    after_exp_counter: Counter[str] = Counter()
    changes: list[ReclassificationChange] = []

    for opp in opportunities:
        old_area = opp.professional_area or "unknown"
        old_sec = tuple(opp.secondary_areas or [])
        old_sen = getattr(opp, "seniority_level", None) or "unknown"
        old_exp_mode = getattr(opp, "experience_requirement_mode", None) or "not_specified"
        old_exp_min = getattr(opp, "experience_min_years", None)
        old_exp_pref = getattr(opp, "experience_preferred_years", None)
        old_exp_sum = getattr(opp, "experience_summary", None)
        before_counter[opp.opportunity_type] += 1
        before_area_counter[old_area] += 1
        before_seniority_counter[old_sen] += 1
        before_exp_counter[old_exp_mode] += 1

        meta = opp.raw_metadata if isinstance(opp.raw_metadata, dict) else {}
        extra_tags: list[str] = []
        meta_levels: list[str] = []
        if isinstance(meta.get("labels"), list):
            extra_tags.extend(str(x) for x in meta["labels"])
            meta_levels.extend(str(x) for x in meta["labels"])
        if isinstance(meta.get("job_type"), list):
            extra_tags.extend(str(x) for x in meta["job_type"])
        if meta.get("job_level") and str(meta["job_level"]).lower() not in {"any", "all"}:
            extra_tags.append(str(meta["job_level"]))
            meta_levels.append(str(meta["job_level"]))
        if isinstance(meta.get("seniority"), list):
            extra_tags.extend(str(x) for x in meta["seniority"])
            meta_levels.extend(str(x) for x in meta["seniority"])
        if meta.get("employment_type_raw"):
            extra_tags.append(str(meta["employment_type_raw"]))

        decision = classify_opportunity(
            title=opp.title,
            tags=list(opp.technologies or []) + extra_tags,
            description=opp.description,
            requirements=list(opp.requirements or []),
            metadata_levels=meta_levels,
        )
        raw_labels = [str(x) for x in (meta.get("labels") or [])] if isinstance(meta.get("labels"), list) else []
        raw_job_types: list[str] = []
        if isinstance(meta.get("job_type"), list):
            raw_job_types.extend(str(x) for x in meta["job_type"])
        if meta.get("employment_type_raw"):
            raw_job_types.append(str(meta["employment_type_raw"]))

        new_opp_type, new_emp_type, new_sen = reconcile_structured_classification(
            decision,
            metadata_levels=meta_levels,
            metadata_job_types=raw_job_types,
            metadata_labels=raw_labels,
        )
        new_area = decision.professional_area
        new_sec_areas = decision.secondary_areas
        if new_area == "unknown" and opp.source is not None:
            if opp.source.slug == "github_frontend_br":
                new_area = "frontend"
                if "software_development" not in new_sec_areas:
                    new_sec_areas = (*new_sec_areas, "software_development")
            elif opp.source.slug == "github_backend_br":
                new_area = "backend"
                if "software_development" not in new_sec_areas:
                    new_sec_areas = (*new_sec_areas, "software_development")

        after_counter[new_opp_type] += 1
        after_area_counter[new_area] += 1
        after_seniority_counter[new_sen] += 1
        after_exp_counter[decision.experience_requirement_mode] += 1

        if (
            new_opp_type,
            new_emp_type,
            new_area,
            new_sec_areas,
            new_sen,
            decision.experience_requirement_mode,
            decision.experience_min_years,
            decision.experience_preferred_years,
            decision.experience_summary,
        ) != (
            opp.opportunity_type,
            opp.employment_type,
            old_area,
            old_sec,
            old_sen,
            old_exp_mode,
            old_exp_min,
            old_exp_pref,
            old_exp_sum,
        ):
            changes.append(
                ReclassificationChange(
                    opportunity_id=str(opp.id),
                    title=opp.title,
                    old_opportunity_type=opp.opportunity_type,
                    new_opportunity_type=new_opp_type,
                    old_employment_type=opp.employment_type,
                    new_employment_type=new_emp_type,
                    old_professional_area=old_area,
                    new_professional_area=new_area,
                    old_secondary_areas=old_sec,
                    new_secondary_areas=new_sec_areas,
                    old_seniority_level=old_sen,
                    new_seniority_level=new_sen,
                    old_experience_mode=old_exp_mode,
                    new_experience_mode=decision.experience_requirement_mode,
                    old_experience_min_years=old_exp_min,
                    new_experience_min_years=decision.experience_min_years,
                    reasons=decision.reasons,
                )
            )
            if not dry_run:
                opp.opportunity_type = new_opp_type
                opp.employment_type = new_emp_type
                opp.professional_area = new_area
                opp.secondary_areas = list(new_sec_areas)
                opp.seniority_level = new_sen
                opp.experience_requirement_mode = decision.experience_requirement_mode
                opp.experience_min_years = decision.experience_min_years
                opp.experience_preferred_years = decision.experience_preferred_years
                opp.experience_summary = decision.experience_summary

    if not dry_run and changes:
        db.commit()

    return ReclassificationReport(
        source_slug=resolved_slug,
        dry_run=dry_run,
        evaluated_count=len(opportunities),
        updated_count=len(changes),
        unchanged_count=len(opportunities) - len(changes),
        before_counts=dict(sorted(before_counter.items())),
        after_counts=dict(sorted(after_counter.items())),
        changes=tuple(changes),
        before_area_counts=dict(sorted(before_area_counter.items())),
        after_area_counts=dict(sorted(after_area_counter.items())),
        before_seniority_counts=dict(sorted(before_seniority_counter.items())),
        after_seniority_counts=dict(sorted(after_seniority_counter.items())),
        before_experience_counts=dict(sorted(before_exp_counter.items())),
        after_experience_counts=dict(sorted(after_exp_counter.items())),
    )
