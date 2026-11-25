"""phase2b_postgis_spatial

Revision ID: d2b5f9d3a218
Revises: d1a4e8c2f109
Create Date: 2026-11-25 22:50:00.000000

"""
from typing import Sequence, Union

from alembic import context, op
from geoalchemy2 import Geography
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2b5f9d3a218"
down_revision: Union[str, Sequence[str], None] = "d1a4e8c2f109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add PostGIS GEOGRAPHY(POINT, 4326) column, backfill existing complaints, and build GiST index."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        if not context.is_offline_mode():
            available = bind.execute(
                sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'")
            ).scalar()
            if not available:
                raise RuntimeError(
                    "PostGIS extension is not available on this PostgreSQL server. "
                    "Enable or install PostGIS before applying spatial migration d2b5f9d3a218."
                )

        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
        op.add_column(
            "complaints",
            sa.Column(
                "location",
                Geography(geometry_type="POINT", srid=4326, spatial_index=False),
                nullable=True,
            ),
        )
        op.execute(
            sa.text(
                """
                UPDATE complaints
                SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
                WHERE latitude IS NOT NULL
                  AND longitude IS NOT NULL
                  AND latitude BETWEEN -90.0 AND 90.0
                  AND longitude BETWEEN -180.0 AND 180.0
                  AND location IS NULL
                """
            )
        )
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_complaints_location_gist ON complaints USING GIST (location)"
            )
        )
    else:
        op.add_column("complaints", sa.Column("location", sa.Text(), nullable=True))
        op.execute(
            sa.text(
                """
                UPDATE complaints
                SET location = 'SRID=4326;POINT(' || longitude || ' ' || latitude || ')'
                WHERE latitude IS NOT NULL
                  AND longitude IS NOT NULL
                  AND latitude BETWEEN -90.0 AND 90.0
                  AND longitude BETWEEN -180.0 AND 180.0
                  AND location IS NULL
                """
            )
        )


def downgrade() -> None:
    """Safely remove Phase 2B spatial index and location column without touching coordinates."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP INDEX IF EXISTS ix_complaints_location_gist"))
        op.drop_column("complaints", "location")
    else:
        with op.batch_alter_table("complaints") as batch_op:
            batch_op.drop_column("location")
