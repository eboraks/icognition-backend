"""Remove option from cloned_document

Revision ID: d7e5377df0eb
Revises: 2e37b753b5d1
Create Date: 2024-03-22 12:35:25.836749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
import pgvector
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'd7e5377df0eb'
down_revision: Union[str, None] = '2e37b753b5d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###
