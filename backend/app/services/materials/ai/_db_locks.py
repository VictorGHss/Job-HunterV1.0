from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
import time
from typing import TypeVar
import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.ai_usage import AIQuotaScopeLock
from app.models.material import ApplicationMaterial, ApplicationMaterialVersion

T = TypeVar("T")


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def prepare_atomic_write_transaction(db: Session) -> str:
    """Prepara uma transação curta de escrita evitando upgrade deadlock no SQLite."""
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "sqlite":
        if (
            not db.info.get("_in_composite_tx")
            and db.in_transaction()
            and not (db.new or db.dirty or db.deleted)
        ):
            # Libera eventual SHARED lock aberto por SELECT anterior na mesma sessão
            db.commit()
        db.connection().exec_driver_sql("PRAGMA busy_timeout = 15000")
    return dialect_name


def acquire_quota_scope_locks(
    db: Session,
    scope_items: Sequence[tuple[str, str]],
    now: datetime,
) -> None:
    """Adquire locks atômicos determinísticos sobre os escopos de cota informados.

    - PostgreSQL 16: garante existência via ``ON CONFLICT DO NOTHING`` e trava as
      linhas em ordem canônica ascendente de ``scope_key`` via ``SELECT ... FOR UPDATE``
      (prevenindo deadlocks e phantom inserts sob ``READ COMMITTED``).
    - SQLite: inicia escrita imediata via ``INSERT ... ON CONFLICT DO UPDATE``,
      obtendo ``RESERVED`` write lock no primeiro statement da transação.
    """
    if not scope_items:
        return

    dialect_name = prepare_atomic_write_transaction(db)
    dedup_sorted = sorted(dict(scope_items).items(), key=lambda pair: pair[0])
    rows = [
        {
            "scope_key": scope_key,
            "scope_type": scope_type,
            "created_at": now,
            "updated_at": now,
        }
        for scope_key, scope_type in dedup_sorted
    ]
    keys = [scope_key for scope_key, _ in dedup_sorted]

    if dialect_name == "postgresql":
        db.execute(
            pg_insert(AIQuotaScopeLock)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["scope_key"])
        )
        db.execute(
            select(AIQuotaScopeLock.scope_key)
            .where(AIQuotaScopeLock.scope_key.in_(keys))
            .order_by(AIQuotaScopeLock.scope_key.asc())
            .with_for_update()
        )
        return

    if dialect_name == "sqlite":
        db.execute(
            sqlite_insert(AIQuotaScopeLock)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["scope_key"],
                set_={"updated_at": now},
            )
        )
        return

    for row in rows:
        existing = db.get(AIQuotaScopeLock, row["scope_key"])
        if existing is None:
            db.add(AIQuotaScopeLock(**row))
    db.flush()
    db.execute(
        select(AIQuotaScopeLock.scope_key)
        .where(AIQuotaScopeLock.scope_key.in_(keys))
        .order_by(AIQuotaScopeLock.scope_key.asc())
        .with_for_update()
    )


def acquire_material_exclusivity_lock(
    db: Session,
    *,
    user_id: uuid.UUID,
    material_id: uuid.UUID,
    source_version_id: uuid.UUID | None = None,
) -> None:
    """Adquire lock exclusivo sobre o material pai (e opcionalmente a versão-fonte).

    Ordem canônica de locks (Níveis 1 e 2):
    1. ``ApplicationMaterial(id=material_id, user_id=user_id)``
    2. ``ApplicationMaterialVersion(id=source_version_id, material_id=material_id)``

    - PostgreSQL 16: ``SELECT ... FOR UPDATE`` real em nível de linha.
    - SQLite: inicia escrita imediata via ``UPDATE application_materials SET updated_at = updated_at``
      após ``prepare_atomic_write_transaction``, obtendo ``RESERVED`` write lock antes
      de qualquer leitura da transação e evitando deadlocks de upgrade ``SHARED -> RESERVED``.
    """
    dialect_name = prepare_atomic_write_transaction(db)
    if dialect_name == "sqlite":
        db.execute(
            update(ApplicationMaterial)
            .where(
                ApplicationMaterial.id == material_id,
                ApplicationMaterial.user_id == user_id,
            )
            .values(updated_at=ApplicationMaterial.updated_at)
        )
        return

    db.execute(
        select(ApplicationMaterial.id)
        .where(
            ApplicationMaterial.id == material_id,
            ApplicationMaterial.user_id == user_id,
        )
        .with_for_update()
    )
    if source_version_id is not None:
        db.execute(
            select(ApplicationMaterialVersion.id)
            .where(
                ApplicationMaterialVersion.id == source_version_id,
                ApplicationMaterialVersion.material_id == material_id,
            )
            .with_for_update()
        )


def run_atomic_with_sqlite_retry(
    db: Session,
    operation: Callable[[], T],
    *,
    max_attempts: int = 6,
) -> T:
    """Executa transação curta tratando contenção transitória de arquivo no SQLite."""
    dialect_name = db.get_bind().dialect.name
    attempts = 0
    while True:
        attempts += 1
        try:
            return operation()
        except OperationalError as exc:
            db.rollback()
            is_sqlite_locked = (
                dialect_name == "sqlite"
                and "locked" in str(exc).lower()
                and attempts < max_attempts
            )
            if not is_sqlite_locked:
                raise
            time.sleep(0.015 * attempts)
