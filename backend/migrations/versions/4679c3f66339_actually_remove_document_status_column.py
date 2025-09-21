"""actually_remove_document_status_column

Revision ID: 4679c3f66339
Revises: 23e7e946ddc6
Create Date: 2025-09-20 18:46:19.776301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4679c3f66339'
down_revision: Union[str, Sequence[str], None] = '23e7e946ddc6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    ## Delete the data from the status column
    op.execute("UPDATE document SET status = NULL")
    op.drop_column('document', 'status')
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('document', sa.Column('status', sa.String(), autoincrement=False, nullable=True))
