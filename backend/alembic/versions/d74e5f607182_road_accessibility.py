"""Persist frozen road calculations and OD cache."""

import sqlalchemy as sa

from alembic import op

revision = "d74e5f607182"
down_revision = "c63d4e5f6071"
branch_labels = None
depends_on = None


def upgrade():
    options = dict(
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci"
    )
    op.create_table(
        "road_accessibility_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        *(
            sa.Column(name, sa.JSON(), nullable=False)
            for name in ("parameters", "inputs", "progress", "result")
        ),
        sa.Column("api_calls", sa.Integer(), nullable=False),
        sa.Column("cache_hits", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        **options,
    )
    op.create_table(
        "road_od_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        **options,
    )


def downgrade():
    op.drop_table("road_od_cache")
    op.drop_table("road_accessibility_runs")
