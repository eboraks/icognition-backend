"""update_embedding_vector_dimension_to_1536

Revision ID: 4084848d3cc8
Revises: 3ab769de7c06
Create Date: 2025-11-03 20:14:17.529824

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '4084848d3cc8'
down_revision: Union[str, Sequence[str], None] = '3ab769de7c06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Alter embedding vector column from vector(768) to vector(1536)
    # Note: Existing embeddings with 768 dimensions will be incompatible and need regeneration
    op.execute("""
        ALTER TABLE embedding 
        ALTER COLUMN vector TYPE vector(1536);
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert embedding vector column back to vector(768)
    # Note: Existing embeddings with 1536 dimensions will be incompatible and need regeneration
    op.execute("""
        ALTER TABLE embedding 
        ALTER COLUMN vector TYPE vector(768);
    """)
