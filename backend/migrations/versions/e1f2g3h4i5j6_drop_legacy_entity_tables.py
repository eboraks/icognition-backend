"""drop_legacy_entity_tables

Drops legacy entity/relationship tables that have been replaced by
kg_node, kg_edge, and kg_node_document.

Also removes the legacy_entity_id FK column from kg_node.

Revision ID: e1f2g3h4i5j6
Revises: d55eed09daf8
Create Date: 2026-04-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1f2g3h4i5j6'
down_revision: Union[str, Sequence[str], None] = 'd55eed09daf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy entity tables and remove legacy_entity_id from kg_node."""
    # Remove legacy_entity_id column from kg_node (has FK to entities.id)
    op.drop_index('ix_kg_node_legacy_entity_id', table_name='kg_node', if_exists=True)
    op.drop_column('kg_node', 'legacy_entity_id')

    # Drop junction/link tables first (they have FKs to entities)
    op.drop_table('relationship_documents')
    op.drop_table('entity_documents')
    op.drop_table('document_entity_link')
    op.drop_table('entity_user_link')

    # Drop main tables
    op.drop_table('entity_relationships')
    op.drop_table('entities')
    op.drop_table('entity_type')

    # Drop test tables
    op.drop_table('test_entities')


def downgrade() -> None:
    """Not supported — data is lost."""
    raise NotImplementedError(
        "Cannot restore dropped legacy entity tables. "
        "Re-run seed scripts to recreate if needed."
    )
