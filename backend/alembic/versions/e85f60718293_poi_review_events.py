"""Append-only review/correction ledger; never remove raw collection pages."""

import sqlalchemy as sa

from alembic import op

revision = "e85f60718293"
down_revision = "d74e5f607182"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "poi_review_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "station_id", sa.Integer(), sa.ForeignKey("charging_stations.id"), nullable=False
        ),
        sa.Column("event_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_poi_review_events_station_id", "poi_review_events", ["station_id"])
    op.create_table(
        "boundary_revisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("adcode", sa.String(6), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("coordinate_system", sa.String(20), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_boundary_revisions_adcode", "boundary_revisions", ["adcode"])


def downgrade():
    op.drop_table("boundary_revisions")
    op.drop_table("poi_review_events")
