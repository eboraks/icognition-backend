"""add user model

Revision ID: 1844d91dd50a
Revises: c065b21c856d
Create Date: 2025-09-07 17:19:16.829468

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '1844d91dd50a'
down_revision: Union[str, Sequence[str], None] = 'c065b21c856d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create users table for user management
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('firebase_uid', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('display_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('photo_url', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.Column('last_active', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('preferences', sa.JSON(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_verified', sa.Boolean(), nullable=False),
    sa.Column('first_login', sa.DateTime(), nullable=True),
    sa.Column('last_login', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for users table
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    op.create_index(op.f('ix_users_firebase_uid'), 'users', ['firebase_uid'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop users table and indexes
    op.drop_index(op.f('ix_users_firebase_uid'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
