"""rename prompt content to user_prompt and add system_prompt

Revision ID: d61403a96d4d
Revises: 9769118a7e9f
Create Date: 2026-01-19 11:46:39.821282

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd61403a96d4d'
down_revision: Union[str, Sequence[str], None] = '9769118a7e9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Rename 'content' to 'user_prompt'
    op.alter_column('prompts', 'content', new_column_name='user_prompt')
    # Add 'system_prompt' column
    op.add_column('prompts', sa.Column('system_prompt', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop 'system_prompt' column
    op.drop_column('prompts', 'system_prompt')
    # Rename 'user_prompt' back to 'content'
    op.alter_column('prompts', 'user_prompt', new_column_name='content')
