"""Remove consolidate response model

Revision ID: d82ce344113e
Revises: 866f227d2b6d
Create Date: 2023-09-12 19:50:14.226418

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
import pgvector


# revision identifiers, used by Alembic.
revision: str = 'd82ce344113e'
down_revision: Union[str, None] = '866f227d2b6d'
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
