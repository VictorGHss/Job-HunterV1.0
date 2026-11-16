from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.opportunity import (
    ExternalSourceStatus,
    Opportunity,
    OpportunitySource,
    OpportunitySyncRun,
    SyncRunStatus,
)
from app.schemas.opportunity import SyncRunSummary
from app.services.opportunities.classification import classify_opportunity
from app.services.opportunities.connectors.base import (
    BaseOpportunityConnector,
    ConnectorError,
    NormalizedOpportunityDraft,
)
from app.services.opportunities.connectors.remote_ok import RemoteOKConnector
from app.services.opportunities.connectors.remotive import RemotiveConnector
from app.services.opportunities.sanitization import compute_opportunity_content_hash

CONNECTOR_CLASSES: dict[str, type[BaseOpportunityConnector]] = {
    RemoteOKConnector.definition.slug: RemoteOKConnector,
    RemotiveConnector.definition.slug: RemotiveConnector,
}


def ensure_default_sources(db: Session) -> list[OpportunitySource]:
    """
    Garante o registro das fontes públicas no banco respeitando o estado explícito
    de habilitação padrão. Nunca reativa automaticamente fontes que tenham sido
    desabilitadas manualmente quando a definição padrão permitir habilitação.
    """
    sources: list[OpportunitySource] = []
    for connector_cls in CONNECTOR_CLASSES.values():
        defn = connector_cls.definition
        existing = db.execute(
            select(OpportunitySource).where(OpportunitySource.slug == defn.slug)
        ).scalar_one_or_none()
        if existing is None:
            existing = OpportunitySource(
                slug=defn.slug,
                name=defn.name,
                source_type=defn.source_type,
                base_url=defn.base_url,
                terms_url=defn.terms_url,
                attribution_text=defn.attribution_text,
                enabled=defn.enabled_by_default,
                refresh_interval_seconds=defn.refresh_interval_seconds,
            )
            db.add(existing)
        else:
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


def _find_existing_opportunity(
    db: Session,
    source_id,
    draft: NormalizedOpportunityDraft,
    content_hash: str,
) -> Opportunity | None:
    # 1. Deduplicação primária: fonte + identificador externo
    opp = db.execute(
        select(Opportunity).where(
            Opportunity.source_id == source_id,
            Opportunity.external_id == draft.external_id,
        )
    ).scalar_one_or_none()
    if opp is not None:
        return opp

    # 2. Deduplicação secundária: URL canônica normalizada dentro da mesma fonte
    opp = db.execute(
        select(Opportunity).where(
            Opportunity.source_id == source_id,
            Opportunity.source_url == draft.source_url,
        )
    ).scalar_one_or_none()
    if opp is not None:
        return opp

    # 3. Deduplicação complementar: hash estável dos dados relevantes
    return db.execute(
        select(Opportunity).where(
            Opportunity.source_id == source_id,
            Opportunity.content_hash == content_hash,
        )
    ).scalar_one_or_none()


def _upsert_opportunity(
    db: Session,
    source: OpportunitySource,
    draft: NormalizedOpportunityDraft,
    now: datetime,
) -> tuple[Opportunity, bool]:
    content_hash = compute_opportunity_content_hash(
        title=draft.title,
        company_name=draft.company_name,
        source_url=draft.source_url,
        work_mode=draft.work_mode,
        employment_type=draft.employment_type,
        location_text=draft.location_text,
        description=draft.description,
    )

    existing = _find_existing_opportunity(db, source.id, draft, content_hash)
    if existing is None:
        opp = Opportunity(
            source_id=source.id,
            created_by_user_id=None,
            external_id=draft.external_id,
            title=draft.title,
            company_name=draft.company_name,
            description=draft.description,
            opportunity_type=draft.opportunity_type,
            employment_type=draft.employment_type,
            work_mode=draft.work_mode,
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
        return (opp, True)

    existing.external_id = draft.external_id
    existing.title = draft.title
    existing.company_name = draft.company_name
    existing.description = draft.description
    existing.opportunity_type = draft.opportunity_type
    existing.employment_type = draft.employment_type
    existing.work_mode = draft.work_mode
    existing.location_text = draft.location_text
    existing.city = draft.city
    existing.state = draft.state
    existing.country = draft.country
    existing.eligible_countries = draft.eligible_countries
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
    existing.raw_metadata = draft.raw_metadata
    return (existing, False)


def _update_absent_opportunities(
    db: Session,
    source_id,
    seen_ids: set,
    now: datetime,
) -> None:
    if not seen_ids:
        return
    active_opps = db.execute(
        select(Opportunity).where(
            Opportunity.source_id == source_id,
            Opportunity.source_status == ExternalSourceStatus.ACTIVE.value,
        )
    ).scalars().all()

    for opp in active_opps:
        if opp.id in seen_ids:
            continue
        opp.last_status_check_at = now
        opp.missing_sync_count += 1
        if opp.deadline_at is not None and opp.deadline_at < now:
            opp.source_status = ExternalSourceStatus.EXPIRED.value
        elif opp.missing_sync_count >= 3:
            # Conservador: nunca encerra após uma única ausência; após 3 ausências completas marca como unknown
            opp.source_status = ExternalSourceStatus.UNKNOWN.value


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def sync_sources(
    db: Session,
    *,
    source_slug: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    connector_overrides: Mapping[str, BaseOpportunityConnector] | None = None,
) -> list[SyncRunSummary]:
    """Executa coleta, validação e deduplicação para uma ou todas as fontes habilitadas."""
    ensure_default_sources(db)

    query = select(OpportunitySource).order_by(OpportunitySource.slug.asc())
    if source_slug:
        query = query.where(OpportunitySource.slug == source_slug.strip().lower())
    else:
        query = query.where(OpportunitySource.enabled.is_(True))

    sources = db.execute(query).scalars().all()
    if source_slug and not sources:
        raise ValueError(f"Fonte '{source_slug}' não encontrada no catálogo.")

    summaries: list[SyncRunSummary] = []

    for source in sources:
        started_at = datetime.now(UTC)
        connector: BaseOpportunityConnector | None = None
        if connector_overrides and source.slug in connector_overrides:
            connector = connector_overrides[source.slug]
        elif source.slug in CONNECTOR_CLASSES:
            connector = CONNECTOR_CLASSES[source.slug]()

        if connector is None:
            run = OpportunitySyncRun(
                source_id=source.id,
                status=SyncRunStatus.SKIPPED.value,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error_summary="Nenhum conector registrado para esta fonte.",
            )
            db.add(run)
            db.commit()
            summaries.append(
                SyncRunSummary(
                    source_slug=source.slug,
                    status=SyncRunStatus.SKIPPED.value,
                    error_summary=run.error_summary,
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
            run = OpportunitySyncRun(
                source_id=source.id,
                status=SyncRunStatus.SKIPPED.value,
                started_at=started_at,
                finished_at=datetime.now(UTC),
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
                run = OpportunitySyncRun(
                    source_id=source.id,
                    status=SyncRunStatus.SKIPPED.value,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    error_summary=msg,
                )
                db.add(run)
                db.commit()
                summaries.append(
                    SyncRunSummary(
                        source_slug=source.slug,
                        status=SyncRunStatus.SKIPPED.value,
                        error_summary=msg,
                    )
                )
                continue

        try:
            drafts = connector.collect()
        except (ConnectorError, Exception) as exc:
            error_msg = str(exc)[:480] if isinstance(exc, ConnectorError) else f"Erro inesperado no conector ({type(exc).__name__})."
            finished_at = datetime.now(UTC)
            source.last_synced_at = finished_at
            source.last_error_at = finished_at
            source.last_error_summary = error_msg
            run = OpportunitySyncRun(
                source_id=source.id,
                status=SyncRunStatus.FAILED.value,
                started_at=started_at,
                finished_at=finished_at,
                error_summary=error_msg,
            )
            db.add(run)
            db.commit()
            summaries.append(
                SyncRunSummary(
                    source_slug=source.slug,
                    status=SyncRunStatus.FAILED.value,
                    error_summary=error_msg,
                )
            )
            continue

        fetched_count = len(drafts)
        if dry_run:
            finished_at = datetime.now(UTC)
            run = OpportunitySyncRun(
                source_id=source.id,
                status=SyncRunStatus.DRY_RUN.value,
                started_at=started_at,
                finished_at=finished_at,
                fetched_count=fetched_count,
                inserted_count=0,
                updated_count=0,
                skipped_count=fetched_count,
            )
            db.add(run)
            db.commit()
            summaries.append(
                SyncRunSummary(
                    source_slug=source.slug,
                    status=SyncRunStatus.DRY_RUN.value,
                    fetched_count=fetched_count,
                    skipped_count=fetched_count,
                )
            )
            continue

        inserted_count = 0
        updated_count = 0
        seen_ids: set = set()
        now = datetime.now(UTC)

        try:
            for draft in drafts:
                opp, is_new = _upsert_opportunity(db, source, draft, now)
                seen_ids.add(opp.id)
                if is_new:
                    inserted_count += 1
                else:
                    updated_count += 1

            _update_absent_opportunities(db, source.id, seen_ids, now)

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
                inserted_count=inserted_count,
                updated_count=updated_count,
                skipped_count=0,
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
            db.add(
                OpportunitySyncRun(
                    source_id=source.id,
                    status=SyncRunStatus.FAILED.value,
                    started_at=started_at,
                    finished_at=finished_at,
                    error_summary=err,
                )
            )
            db.commit()
            summaries.append(
                SyncRunSummary(
                    source_slug=source.slug,
                    status=SyncRunStatus.FAILED.value,
                    error_summary=err,
                )
            )
            continue

        summaries.append(
            SyncRunSummary(
                source_slug=source.slug,
                status=SyncRunStatus.SUCCESS.value,
                fetched_count=fetched_count,
                inserted_count=inserted_count,
                updated_count=updated_count,
                skipped_count=0,
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
    reasons: tuple[str, ...]


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


def reclassify_opportunities(
    db: Session,
    *,
    source_slug: str | None = None,
    dry_run: bool = False,
) -> ReclassificationReport:
    """
    Reavalia deterministicamente `opportunity_type` e `employment_type` de registros
    já persistidos de fontes externas habilitadas sem alterar cadastros manuais,
    metadados originais, histórico temporal ou estados do usuário.
    """
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
    changes: list[ReclassificationChange] = []

    for opp in opportunities:
        before_counter[opp.opportunity_type] += 1
        decision = classify_opportunity(
            title=opp.title,
            tags=list(opp.technologies or []),
            description=opp.description,
        )
        after_counter[decision.opportunity_type] += 1

        if (decision.opportunity_type, decision.employment_type) != (
            opp.opportunity_type,
            opp.employment_type,
        ):
            changes.append(
                ReclassificationChange(
                    opportunity_id=str(opp.id),
                    title=opp.title,
                    old_opportunity_type=opp.opportunity_type,
                    new_opportunity_type=decision.opportunity_type,
                    old_employment_type=opp.employment_type,
                    new_employment_type=decision.employment_type,
                    reasons=decision.reasons,
                )
            )
            if not dry_run:
                opp.opportunity_type = decision.opportunity_type
                opp.employment_type = decision.employment_type

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
    )
