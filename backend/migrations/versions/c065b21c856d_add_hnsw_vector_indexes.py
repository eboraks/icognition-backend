"""add HNSW vector indexes

Revision ID: c065b21c856d
Revises: a7fa71f32f87
Create Date: 2025-09-07 16:57:00.389110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c065b21c856d'
down_revision: Union[str, Sequence[str], None] = 'a7fa71f32f87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create HNSW indexes for vector similarity search
    # These indexes will significantly improve vector search performance
    
    # HNSW index for test_documents embedding column
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_documents_embedding_hnsw 
        ON test_documents 
        USING hnsw (embedding vector_l2_ops) 
        WITH (m=16, ef_construction=64);
    """)
    
    # HNSW index for test_entities embedding column
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_entities_embedding_hnsw 
        ON test_entities 
        USING hnsw (embedding vector_l2_ops) 
        WITH (m=16, ef_construction=64);
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop HNSW indexes
    op.execute("DROP INDEX IF EXISTS idx_test_entities_embedding_hnsw;")
    op.execute("DROP INDEX IF EXISTS idx_test_documents_embedding_hnsw;")
