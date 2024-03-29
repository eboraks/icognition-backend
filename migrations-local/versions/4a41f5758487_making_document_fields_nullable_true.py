"""Making document fields nullable true

Revision ID: 4a41f5758487
Revises: 1be08eec43c0
Create Date: 2024-02-17 10:24:46.402251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
import pgvector
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4a41f5758487'
down_revision: Union[str, None] = '1be08eec43c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('document', 'short_summary',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('document', 'raw_answer',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('document', 'publication_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('document', 'publication_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('document', 'raw_answer',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('document', 'short_summary',
               existing_type=sa.VARCHAR(),
               nullable=False)
    # ### end Alembic commands ###
