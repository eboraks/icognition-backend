"""remove_legacy_document_columns

Revision ID: 17da34c28575
Revises: 0e3c95d9a1e4
Create Date: 2026-03-02 14:34:02.039043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '17da34c28575'
down_revision: Union[str, Sequence[str], None] = '0e3c95d9a1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy columns from the document table."""
    op.drop_column('document', 'source_text_in_html')
    op.drop_column('document', 'update_at')
    op.drop_column('document', 'llm_service_meta')
    op.drop_column('document', 'types_and_concepts')
    op.drop_column('document', 'cosine_similarity')


def downgrade() -> None:
    """Restore legacy columns (data will be empty)."""
    op.add_column('document', sa.Column('cosine_similarity', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True))
    op.add_column('document', sa.Column('types_and_concepts', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True))
    op.add_column('document', sa.Column('llm_service_meta', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True))
    op.add_column('document', sa.Column('update_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
    op.add_column('document', sa.Column('source_text_in_html', sa.VARCHAR(), autoincrement=False, nullable=True))
