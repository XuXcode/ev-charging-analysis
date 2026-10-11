"""Additive demand-side POI evidence for planning reference scoring."""

import sqlalchemy as sa

from alembic import op

revision = "a10b2c3d4e5f"
down_revision = "f960718293a4"
branch_labels = None
depends_on = None


def upgrade():
    options = dict(
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci"
    )
    op.create_table(
        "demand_pois",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("poi_id", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("demand_type", sa.String(30), nullable=False, index=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("adcode", sa.String(6), nullable=False, index=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        **options,
    )
    op.create_index("ix_demand_pois_type_adcode", "demand_pois", ["demand_type", "adcode"])
    op.create_table(
        "demand_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.String(500), nullable=True),
        **options,
    )
    op.create_table(
        "demand_score_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("algorithm_version", sa.String(60), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False, index=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        **options,
    )


def downgrade():
    op.drop_table("demand_score_runs")
    op.drop_table("demand_runs")
    op.drop_table("demand_pois")
