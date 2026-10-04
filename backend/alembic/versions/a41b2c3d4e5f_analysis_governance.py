"""Add governance and analysis persistence without changing raw station records."""

import sqlalchemy as sa

from alembic import op

revision = "a41b2c3d4e5f"
down_revision = "f233d458f264"
branch_labels = None
depends_on = None
OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def upgrade():
    op.create_table(
        "poi_quality",
        sa.Column(
            "station_id", sa.Integer(), sa.ForeignKey("charging_stations.id"), primary_key=True
        ),
        sa.Column("classification", sa.String(30), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("review_note", sa.String(1000)),
        sa.Column("rules_version", sa.String(40), nullable=False),
        sa.Column("run_id", sa.String(32), sa.ForeignKey("collection_runs.id"), nullable=False),
        sa.Column("classified_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        **OPTIONS,
    )
    op.create_index(
        "ix_poi_quality_filter", "poi_quality", ["classification", "review_status", "needs_review"]
    )
    op.create_index("ix_poi_quality_run_id", "poi_quality", ["run_id"])
    op.create_table(
        "analysis_snapshots",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("run_id", sa.String(32), sa.ForeignKey("collection_runs.id"), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("boundary_hash", sa.String(64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        **OPTIONS,
    )
    op.create_index("ix_analysis_snapshot_latest", "analysis_snapshots", ["status", "computed_at"])
    op.create_index("ix_analysis_snapshots_run_id", "analysis_snapshots", ["run_id"])
    op.create_index("ix_analysis_snapshots_input_hash", "analysis_snapshots", ["input_hash"])
    op.create_table(
        "analysis_boundaries",
        sa.Column("adcode", sa.String(6), primary_key=True),
        sa.Column("city_code", sa.String(6), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("coordinate_system", sa.String(20), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        **OPTIONS,
    )
    op.create_index("ix_analysis_boundaries_city_code", "analysis_boundaries", ["city_code"])
    op.create_table(
        "analysis_scope_quality",
        sa.Column("adcode", sa.String(6), primary_key=True),
        sa.Column("city_code", sa.String(6), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("completeness_warning", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("run_id", sa.String(32), sa.ForeignKey("collection_runs.id"), nullable=False),
        **OPTIONS,
    )
    op.create_index("ix_analysis_scope_quality_city_code", "analysis_scope_quality", ["city_code"])
    op.create_index("ix_analysis_scope_quality_run_id", "analysis_scope_quality", ["run_id"])
    op.create_index(
        "ix_charging_stations_source_adcode_location",
        "charging_stations",
        ["source", "adcode", "longitude", "latitude"],
    )


def downgrade():
    op.drop_index("ix_charging_stations_source_adcode_location", "charging_stations")
    for table in (
        "analysis_scope_quality",
        "analysis_boundaries",
        "analysis_snapshots",
        "poi_quality",
    ):
        op.drop_table(table)
