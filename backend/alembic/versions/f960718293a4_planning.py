"""Add immutable planning evidence without changing station collection tables."""

import sqlalchemy as sa

from alembic import op

revision = "f960718293a4"
down_revision = "e85f60718293"
branch_labels = None
depends_on = None


def upgrade():
    options = dict(
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci"
    )
    op.create_table(
        "planning_datasets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("records", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        **options,
    )
    op.create_index("ix_planning_datasets_kind", "planning_datasets", ["kind"])
    op.create_table(
        "planning_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("algorithm_version", sa.String(60), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        **options,
    )
    op.create_index("ix_planning_runs_input_hash", "planning_runs", ["input_hash"])


def downgrade():
    op.drop_table("planning_runs")
    op.drop_table("planning_datasets")
