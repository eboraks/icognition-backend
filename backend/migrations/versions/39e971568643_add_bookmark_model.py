"""add bookmark model

Revision ID: 39e971568643
Revises: 1844d91dd50a
Create Date: 2025-09-07 17:24:29.666940

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '39e971568643'
down_revision: Union[str, Sequence[str], None] = '1844d91dd50a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create bookmarks table
    op.create_table('bookmarks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('url', sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('bookmark_metadata', sa.JSON(), nullable=True),
    sa.Column('is_processed', sa.Boolean(), nullable=False),
    sa.Column('processing_status', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for bookmarks table
    op.create_index(op.f('ix_bookmarks_url'), 'bookmarks', ['url'], unique=False)
    op.create_index(op.f('ix_bookmarks_user_id'), 'bookmarks', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop bookmarks table and indexes
    op.drop_index(op.f('ix_bookmarks_user_id'), table_name='bookmarks')
    op.drop_index(op.f('ix_bookmarks_url'), table_name='bookmarks')
    op.drop_table('bookmarks')