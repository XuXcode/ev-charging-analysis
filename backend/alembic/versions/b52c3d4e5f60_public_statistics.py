"""Add traceable partial public statistics; never fill missing metrics with zero."""

import sqlalchemy as sa

from alembic import op

revision = "b52c3d4e5f60"
down_revision = "a41b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "public_statistics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region_adcode", sa.String(6), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(50), nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("scope_description", sa.String(1000), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_public_statistic_lookup", "public_statistics", ["region_adcode", "year", "metric"]
    )


def downgrade():
    op.drop_table("public_statistics")
