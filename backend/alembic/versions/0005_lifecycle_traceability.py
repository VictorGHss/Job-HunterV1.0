"""Add opportunity_source_links and sync observability metrics for phase 02.5

Revision ID: 0005_lifecycle_traceability
Revises: 0004_professional_areas
Create Date: 2026-11-15 22:55:00.000000

"""
from typing import Sequence, Union
from urllib.parse import urlparse
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_lifecycle_traceability"
down_revision: Union[str, None] = "0004_professional_areas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

json_type = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()),
    "postgresql",
)


def upgrade() -> None:
    op.create_table(
        "opportunity_source_links",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("application_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "source_status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location_text", sa.String(length=255), nullable=True),
        sa.Column("eligible_countries", json_type, nullable=False),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("salary_currency", sa.String(length=16), nullable=True),
        sa.Column("salary_period", sa.String(length=32), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "missing_sync_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("raw_metadata", json_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_opportunity_source_links_opportunity_id_opportunities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["opportunity_sources.id"],
            name=op.f("fk_opportunity_source_links_source_id_opportunity_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_source_links")),
        sa.UniqueConstraint(
            "source_id",
            "external_id",
            name="uq_opp_source_links_source_external",
        ),
    )
    op.create_index(
        op.f("ix_opportunity_source_links_opportunity_id"),
        "opportunity_source_links",
        ["opportunity_id"],
    )
    op.create_index(
        op.f("ix_opportunity_source_links_source_id"),
        "opportunity_source_links",
        ["source_id"],
    )
    op.create_index(
        op.f("ix_opportunity_source_links_source_status"),
        "opportunity_source_links",
        ["source_status"],
    )
    op.create_index(
        "ix_opp_source_links_source_url",
        "opportunity_source_links",
        ["source_id", "source_url"],
    )

    with op.batch_alter_table("opportunity_sync_runs") as batch_op:
        for col_name in (
            "received_count",
            "valid_count",
            "rejected_count",
            "intra_source_duplicate_count",
            "cross_source_duplicate_count",
            "unique_opportunities_count",
            "open_opportunities_count",
            "closed_or_expired_count",
            "unconfirmed_count",
        ):
            batch_op.add_column(
                sa.Column(
                    col_name,
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE opportunity_sync_runs "
            "SET received_count = fetched_count, "
            "valid_count = CASE WHEN (inserted_count + updated_count) > 0 "
            "THEN (inserted_count + updated_count) ELSE fetched_count END"
        )
    )

    # Normaliza external_id de oportunidades já persistidas da Himalayas (incluindo company slug)
    himalayas_row = bind.execute(
        sa.text("SELECT id FROM opportunity_sources WHERE slug = 'himalayas'")
    ).fetchone()
    if himalayas_row is not None:
        himalayas_id = himalayas_row[0]
        him_opps = bind.execute(
            sa.text(
                "SELECT id, external_id, source_url FROM opportunities WHERE source_id = :sid"
            ),
            {"sid": himalayas_id},
        ).fetchall()
        for opp_id, ext_id, src_url in him_opps:
            if src_url and "/" not in str(ext_id or ""):
                path_clean = urlparse(str(src_url)).path.strip("/")
                if path_clean.startswith("companies/"):
                    path_clean = path_clean[len("companies/") :]
                if path_clean:
                    bind.execute(
                        sa.text(
                            "UPDATE opportunities SET external_id = :new_ext WHERE id = :oid"
                        ),
                        {"new_ext": path_clean[:255], "oid": opp_id},
                    )

    # Backfill de vínculos primários para oportunidades de fontes externas existentes
    opps_table = sa.table(
        "opportunities",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("source_id", sa.Uuid(as_uuid=True)),
        sa.column("external_id", sa.String()),
        sa.column("source_url", sa.String()),
        sa.column("application_url", sa.String()),
        sa.column("source_status", sa.String()),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("deadline_at", sa.DateTime(timezone=True)),
        sa.column("location_text", sa.String()),
        sa.column("eligible_countries", json_type),
        sa.column("salary_min", sa.Float()),
        sa.column("salary_max", sa.Float()),
        sa.column("salary_currency", sa.String()),
        sa.column("salary_period", sa.String()),
        sa.column("first_seen_at", sa.DateTime(timezone=True)),
        sa.column("last_seen_at", sa.DateTime(timezone=True)),
        sa.column("last_status_check_at", sa.DateTime(timezone=True)),
        sa.column("missing_sync_count", sa.Integer()),
        sa.column("raw_metadata", json_type),
    )
    links_table = sa.table(
        "opportunity_source_links",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("opportunity_id", sa.Uuid(as_uuid=True)),
        sa.column("source_id", sa.Uuid(as_uuid=True)),
        sa.column("external_id", sa.String()),
        sa.column("source_url", sa.String()),
        sa.column("application_url", sa.String()),
        sa.column("is_primary", sa.Boolean()),
        sa.column("source_status", sa.String()),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("deadline_at", sa.DateTime(timezone=True)),
        sa.column("location_text", sa.String()),
        sa.column("eligible_countries", json_type),
        sa.column("salary_min", sa.Float()),
        sa.column("salary_max", sa.Float()),
        sa.column("salary_currency", sa.String()),
        sa.column("salary_period", sa.String()),
        sa.column("first_seen_at", sa.DateTime(timezone=True)),
        sa.column("last_seen_at", sa.DateTime(timezone=True)),
        sa.column("last_checked_at", sa.DateTime(timezone=True)),
        sa.column("missing_sync_count", sa.Integer()),
        sa.column("raw_metadata", json_type),
    )

    existing_opps = bind.execute(
        sa.select(opps_table).where(opps_table.c.source_id.is_not(None))
    ).mappings().all()

    link_rows = []
    for row in existing_opps:
        ext_id = str(row["external_id"] or row["id"])[:255]
        countries = row["eligible_countries"]
        if isinstance(countries, str):
            try:
                countries = json.loads(countries)
            except Exception:
                countries = []
        meta = row["raw_metadata"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        link_rows.append(
            {
                "id": uuid.uuid4(),
                "opportunity_id": row["id"],
                "source_id": row["source_id"],
                "external_id": ext_id,
                "source_url": row["source_url"],
                "application_url": row["application_url"],
                "is_primary": True,
                "source_status": row["source_status"] or "active",
                "published_at": row["published_at"],
                "deadline_at": row["deadline_at"],
                "location_text": row["location_text"],
                "eligible_countries": countries if isinstance(countries, list) else [],
                "salary_min": row["salary_min"],
                "salary_max": row["salary_max"],
                "salary_currency": row["salary_currency"],
                "salary_period": row["salary_period"],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
                "last_checked_at": row["last_status_check_at"] or row["last_seen_at"],
                "missing_sync_count": row["missing_sync_count"] or 0,
                "raw_metadata": meta if isinstance(meta, dict) else {},
            }
        )

    if link_rows:
        op.bulk_insert(links_table, link_rows)


def downgrade() -> None:
    with op.batch_alter_table("opportunity_sync_runs") as batch_op:
        for col_name in (
            "unconfirmed_count",
            "closed_or_expired_count",
            "open_opportunities_count",
            "unique_opportunities_count",
            "cross_source_duplicate_count",
            "intra_source_duplicate_count",
            "rejected_count",
            "valid_count",
            "received_count",
        ):
            batch_op.drop_column(col_name)

    op.drop_index("ix_opp_source_links_source_url", table_name="opportunity_source_links")
    op.drop_index(
        op.f("ix_opportunity_source_links_source_status"),
        table_name="opportunity_source_links",
    )
    op.drop_index(
        op.f("ix_opportunity_source_links_source_id"),
        table_name="opportunity_source_links",
    )
    op.drop_index(
        op.f("ix_opportunity_source_links_opportunity_id"),
        table_name="opportunity_source_links",
    )
    op.drop_table("opportunity_source_links")
