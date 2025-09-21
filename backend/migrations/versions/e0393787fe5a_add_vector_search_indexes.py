"""add vector search indexes

Revision ID: e0393787fe5a
Revises: be0cb8aeef1a
Create Date: 2025-09-07 16:53:00.875118

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0393787fe5a'
down_revision: Union[str, Sequence[str], None] = 'be0cb8aeef1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create basic indexes for common query patterns
    # Note: HNSW and GIN indexes will be created after column types are properly configured
    
    # B-tree indexes for text search
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_documents_title_btree 
        ON test_documents 
        USING btree (title);
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_entities_type_btree 
        ON test_entities 
        USING btree (entity_type);
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop all indexes created in upgrade
    op.execute("DROP INDEX IF EXISTS idx_test_entities_type_btree;")
    op.execute("DROP INDEX IF EXISTS idx_test_documents_title_btree;")
