"""fix vector column types

Revision ID: a7fa71f32f87
Revises: e0393787fe5a
Create Date: 2025-09-07 16:55:21.783261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7fa71f32f87'
down_revision: Union[str, Sequence[str], None] = 'e0393787fe5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Convert ARRAY(Float) columns to proper vector types for pgvector
    # This is necessary for HNSW indexes to work properly
    
    # Convert test_documents.embedding from double precision[] to vector(1536)
    op.execute("""
        ALTER TABLE test_documents 
        ALTER COLUMN embedding TYPE vector(1536) 
        USING embedding::vector(1536);
    """)
    
    # Convert test_entities.embedding from double precision[] to vector(1536)
    op.execute("""
        ALTER TABLE test_entities 
        ALTER COLUMN embedding TYPE vector(1536) 
        USING embedding::vector(1536);
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Convert vector columns back to double precision[] arrays
    op.execute("""
        ALTER TABLE test_entities 
        ALTER COLUMN embedding TYPE double precision[] 
        USING embedding::double precision[];
    """)
    
    op.execute("""
        ALTER TABLE test_documents 
        ALTER COLUMN embedding TYPE double precision[] 
        USING embedding::double precision[];
    """)
