"""Adjust demand_pois uniqueness to (poi_id, demand_type).

A single facility can be recalled by multiple demand keywords (e.g. a hospital
parking lot matches both "医院" and "停车场"); keeping one row per type is
intentional evidence, not a duplicate.
"""

from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a10b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("uq_demand_pois_poi_id", "demand_pois", type_="unique")
    op.create_unique_constraint("uq_demand_pois_poi_type", "demand_pois", ["poi_id", "demand_type"])


def downgrade():
    op.drop_constraint("uq_demand_pois_poi_type", "demand_pois", type_="unique")
    op.create_unique_constraint("uq_demand_pois_poi_id", "demand_pois", ["poi_id"])
