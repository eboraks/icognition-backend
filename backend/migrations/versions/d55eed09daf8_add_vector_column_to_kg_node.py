"""add_vector_column_to_kg_node

Revision ID: d55eed09daf8
Revises: h1i2j3k4l5m6
Create Date: 2026-04-06 15:03:02.676536

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'd55eed09daf8'
down_revision: Union[str, Sequence[str], None] = 'h1i2j3k4l5m6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add vector column and HNSW index to kg_node for semantic dedup."""
    op.add_column('kg_node', sa.Column('vector', Vector(dim=1536), nullable=True))
    op.create_index(
        'ix_kg_node_vector_hnsw', 'kg_node', ['vector'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'vector': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    """Remove vector column and index from kg_node."""
    op.drop_index(
        'ix_kg_node_vector_hnsw', table_name='kg_node',
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'vector': 'vector_cosine_ops'},
    )
    op.drop_column('kg_node', 'vector')
