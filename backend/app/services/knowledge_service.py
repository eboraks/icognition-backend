"""
Knowledge exploration service for managing filter trees and contextual chat interactions
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
import logging

from app.models import Entity, Document, EntityDocument
from app.utils.logging import get_logger

logger = get_logger(__name__)


class KnowledgeService:
    """Service for knowledge exploration features"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_filter_tree(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get the complete filter tree structure for a user.
        Returns a list of documents, each with nested entities grouped by type.
        Hierarchy: Document -> Entity Type -> Entity Name
        """
        try:
            # Get all documents for the user
            doc_stmt = select(Document).where(Document.user_id == user_id)
            doc_result = await self.session.execute(doc_stmt)
            documents = doc_result.scalars().all()

            if not documents:
                return []

            doc_ids = [d.id for d in documents]

            # Get all entities for the user
            entity_stmt = select(Entity).where(Entity.user_id == user_id)
            entity_result = await self.session.execute(entity_stmt)
            entities = entity_result.scalars().all()
            entities_dict = {e.id: e for e in entities}

            # Get entity-document relationships with DISTINCT to avoid duplicates at DB level
            entity_ids = [e.id for e in entities]
            
            if entity_ids and doc_ids:
                # Use distinct on entity_id and document_id to get unique relationships
                ed_stmt = (
                    select(EntityDocument.entity_id, EntityDocument.document_id)
                    .where(
                        and_(
                            EntityDocument.entity_id.in_(entity_ids),
                            EntityDocument.document_id.in_(doc_ids)
                        )
                    )
                    .distinct()
                )
                ed_result = await self.session.execute(ed_stmt)
                entity_document_pairs = ed_result.all()
            else:
                entity_document_pairs = []

            # Build a map of document_id -> set of entity_ids (using set for automatic deduplication)
            doc_to_entities: Dict[int, set[int]] = {}
            for entity_id, document_id in entity_document_pairs:
                if document_id not in doc_to_entities:
                    doc_to_entities[document_id] = set()
                doc_to_entities[document_id].add(entity_id)

            # Map entity types to display names and icons
            # PrimeIcons require the full class format: "pi pi-iconname"
            type_mapping = {
                "Person": {"label": "People", "icon": "pi pi-users", "group": "people"},
                "People": {"label": "People", "icon": "pi pi-users", "group": "people"},
                "Location": {"label": "Location", "icon": "pi pi-globe", "group": "location"},
                "City": {"label": "Location", "icon": "pi pi-globe", "group": "location"},
                "Country": {"label": "Location", "icon": "pi pi-globe", "group": "location"},
                "Organization": {"label": "Institution", "icon": "pi pi-building", "group": "institution"},
                "Institution": {"label": "Institution", "icon": "pi pi-building", "group": "institution"},
                "Company": {"label": "Institution", "icon": "pi pi-building", "group": "institution"},
                "Business": {"label": "Institution", "icon": "pi pi-building", "group": "institution"},
                "Agency": {"label": "Institution", "icon": "pi pi-building", "group": "institution"},
                "Event": {"label": "Event", "icon": "pi pi-calendar", "group": "event"},
                "Conference": {"label": "Event", "icon": "pi pi-calendar", "group": "event"},
                "Summit": {"label": "Event", "icon": "pi pi-calendar", "group": "event"},
                "Product": {"label": "Product", "icon": "pi pi-box", "group": "product"},
                "Technology": {"label": "Technology", "icon": "pi pi-cog", "group": "technology"},
                "Topic": {"label": "Concept", "icon": "pi pi-lightbulb", "group": "concept"},
                "Concept": {"label": "Concept", "icon": "pi pi-lightbulb", "group": "concept"},
                "Idea": {"label": "Concept", "icon": "pi pi-lightbulb", "group": "concept"},
                "Service": {"label": "Service", "icon": "pi pi-briefcase", "group": "service"},
                "Program": {"label": "Service", "icon": "pi pi-briefcase", "group": "service"},
                "Project": {"label": "Project", "icon": "pi pi-flag", "group": "project"},
                "Campaign": {"label": "Project", "icon": "pi pi-flag", "group": "project"},
            }

            # Build tree nodes: Document -> Entity Type -> Entity Name
            tree_nodes = []
            for doc in documents:
                # Get entities for this document (already deduplicated at DB level)
                entity_ids_for_doc = list(doc_to_entities.get(doc.id, set()))
                
                # Group entities by display group, using entity name as key to prevent duplicates
                entities_by_group: Dict[str, Dict[str, Any]] = {}
                for entity_id in entity_ids_for_doc:
                    if entity_id not in entities_dict:
                        continue
                    entity = entities_dict[entity_id]
                    entity_type = entity.type or "Other"
                    type_info = type_mapping.get(
                        entity_type,
                        {
                            "label": entity_type,
                            "icon": "pi pi-question",
                            "group": entity_type.lower().replace(" ", "_"),
                        },
                    )
                    group_key = type_info["group"]

                    if group_key not in entities_by_group:
                        entities_by_group[group_key] = {
                            "label": type_info["label"],
                            "icon": type_info["icon"],
                            "types": set(),
                            "entities": {},
                        }

                    group_entry = entities_by_group[group_key]
                    group_entry["types"].add(entity_type)
                    
                    # Use entity name as key to ensure uniqueness within each group
                    # If same name appears, keep the first one (or you could merge them)
                    entity_key = f"{entity.name.lower()}-{entity.id}"

                    if entity_key not in group_entry["entities"]:
                        group_entry["entities"][entity_key] = {
                            "key": f"entity-{entity.id}",
                            "label": entity.name,
                            "data": {
                                "type": "entity",
                                "id": entity.id,
                                "name": entity.name,
                                "entity_type": entity.type,
                            }
                        }

                # Build children: entity group nodes with entity name children
                entity_type_children = []
                for group_key, group_data in entities_by_group.items():
                    entity_list = sorted(
                        list(group_data["entities"].values()),
                        key=lambda x: x["label"].lower()
                    )

                    if not entity_list:
                        continue

                    entity_type_children.append({
                        "key": f"doc-{doc.id}-group-{group_key}",
                        "label": group_data["label"],
                        "data": {
                            "type": "entity_type",
                            "id": None,
                            "group": group_key,
                            "entity_types": sorted(group_data["types"]),
                        },
                        "children": entity_list
                    })

                entity_type_children.sort(key=lambda x: x["label"].lower())

                # Create document node
                doc_node = {
                    "key": f"doc-{doc.id}",
                    "label": doc.title or "Untitled",
                    "data": {
                        "type": "document",
                        "id": doc.id,
                        "title": doc.title,
                    },
                    "children": entity_type_children if entity_type_children else []
                }
                
                tree_nodes.append(doc_node)

            logger.info(f"Built filter tree for user {user_id} with {len(tree_nodes)} documents")
            return tree_nodes

        except Exception as e:
            logger.error(f"Error building filter tree for user {user_id}: {e}", exc_info=True)
            raise

    async def get_contextual_message(
        self, user_id: str, entity_id: Optional[int] = None, document_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a contextual message and suggested actions based on selected filter.
        """
        try:
            if entity_id:
                # Get entity information
                entity_stmt = select(Entity).where(
                    and_(Entity.id == entity_id, Entity.user_id == user_id)
                )
                entity_result = await self.session.execute(entity_stmt)
                entity = entity_result.scalar_one_or_none()

                if not entity:
                    raise ValueError(f"Entity {entity_id} not found for user {user_id}")

                # Get documents related to this entity
                ed_stmt = select(EntityDocument).where(EntityDocument.entity_id == entity_id)
                ed_result = await self.session.execute(ed_stmt)
                entity_docs = ed_result.scalars().all()

                doc_ids = [ed.document_id for ed in entity_docs]
                doc_stmt = select(Document).where(
                    and_(Document.id.in_(doc_ids), Document.user_id == user_id)
                )
                doc_result = await self.session.execute(doc_stmt)
                documents = doc_result.scalars().all()

                # Generate contextual message
                doc_count = len(documents)
                message = f"You've selected '{entity.name}'. I found {doc_count} document{'s' if doc_count != 1 else ''} related to {'him' if entity.type == 'Person' else 'it'} in your library. What would you like to explore next?"

                # Generate suggested actions
                actions = [
                    {"id": "learn_more", "label": f"Learn more about {entity.name}"},
                    {"id": "latest_news", "label": f"Show me latest news"},
                    {"id": "summarize", "label": "Summarize documents"},
                ]

                # Get entity description if available
                entity_info = entity.description or entity.wikidata_description or None

                return {
                    "message": message,
                    "actions": actions,
                    "entity": {
                        "id": entity.id,
                        "name": entity.name,
                        "type": entity.type,
                        "description": entity_info,
                    },
                    "document_count": doc_count,
                }

            elif document_id:
                # Get document information
                doc_stmt = select(Document).where(
                    and_(Document.id == document_id, Document.user_id == user_id)
                )
                doc_result = await self.session.execute(doc_stmt)
                document = doc_result.scalar_one_or_none()

                if not document:
                    raise ValueError(f"Document {document_id} not found for user {user_id}")

                message = f"You've selected '{document.title or 'Untitled'}'. What would you like to know about this document?"

                actions = [
                    {"id": "summarize", "label": "Summarize this document"},
                    {"id": "key_points", "label": "Show key points"},
                    {"id": "entities", "label": "Show entities mentioned"},
                ]

                return {
                    "message": message,
                    "actions": actions,
                    "document": {
                        "id": document.id,
                        "title": document.title,
                    },
                }

            else:
                # Default welcome message
                return {
                    "message": "Hello! I'm your knowledge exploration assistant. Use the filters on the left to navigate your knowledge graph, or ask me a question directly.",
                    "actions": [],
                }

        except Exception as e:
            logger.error(f"Error generating contextual message: {e}", exc_info=True)
            raise

    async def handle_action(
        self, user_id: str, action_id: str, entity_id: Optional[int] = None, document_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Handle a user action (e.g., clicking a suggested button).
        Returns a response message and any additional data.
        """
        try:
            if action_id == "learn_more" and entity_id:
                # Get entity information
                entity_stmt = select(Entity).where(
                    and_(Entity.id == entity_id, Entity.user_id == user_id)
                )
                entity_result = await self.session.execute(entity_stmt)
                entity = entity_result.scalar_one_or_none()

                if not entity:
                    raise ValueError(f"Entity {entity_id} not found")

                # Get related documents
                ed_stmt = select(EntityDocument).where(EntityDocument.entity_id == entity_id)
                ed_result = await self.session.execute(ed_stmt)
                entity_docs = ed_result.scalars().all()

                doc_ids = [ed.document_id for ed in entity_docs]
                doc_stmt = select(Document).where(
                    and_(Document.id.in_(doc_ids), Document.user_id == user_id)
                )
                doc_result = await self.session.execute(doc_stmt)
                documents = doc_result.scalars().all()

                # Build response with entity information
                response_parts = []
                if entity.description or entity.wikidata_description:
                    description = entity.description or entity.wikidata_description
                    response_parts.append(description)
                else:
                    response_parts.append(f"{entity.name} is a {entity.type or 'entity'} in your knowledge graph.")

                if documents:
                    doc_titles = [doc.title or "Untitled" for doc in documents]
                    response_parts.append(f"Your library contains information about {', '.join(doc_titles[:3])}.")
                    if len(doc_titles) > 3:
                        response_parts.append(f"And {len(doc_titles) - 3} more document{'s' if len(doc_titles) - 3 != 1 else ''}.")

                return {
                    "message": " ".join(response_parts),
                    "resources": [
                        {"id": doc.id, "title": doc.title or "Untitled"}
                        for doc in documents[:5]
                    ],
                }

            elif action_id == "summarize":
                if document_id:
                    doc_stmt = select(Document).where(
                        and_(Document.id == document_id, Document.user_id == user_id)
                    )
                    doc_result = await self.session.execute(doc_stmt)
                    document = doc_result.scalar_one_or_none()

                    if not document:
                        raise ValueError(f"Document {document_id} not found")

                    # For now, return a placeholder. In the future, this could call an AI summarization service
                    return {
                        "message": f"Summary for '{document.title or 'Untitled'}': This document is part of your knowledge graph. Detailed summarization will be available soon.",
                    }
                elif entity_id:
                    # Summarize all documents related to the entity
                    ed_stmt = select(EntityDocument).where(EntityDocument.entity_id == entity_id)
                    ed_result = await self.session.execute(ed_stmt)
                    entity_docs = ed_result.scalars().all()

                    doc_ids = [ed.document_id for ed in entity_docs]
                    doc_stmt = select(Document).where(
                        and_(Document.id.in_(doc_ids), Document.user_id == user_id)
                    )
                    doc_result = await self.session.execute(doc_stmt)
                    documents = doc_result.scalars().all()

                    return {
                        "message": f"I found {len(documents)} document{'s' if len(documents) != 1 else ''} related to this entity. Detailed summarization will be available soon.",
                    }

            elif action_id == "latest_news":
                # Placeholder for latest news feature
                return {
                    "message": "Latest news feature will be available soon. This will show recent information about the selected entity.",
                }

            elif action_id == "key_points" and document_id:
                # Placeholder for key points feature
                return {
                    "message": "Key points extraction will be available soon.",
                }

            elif action_id == "entities" and document_id:
                # Get entities related to this document
                ed_stmt = select(EntityDocument).where(EntityDocument.document_id == document_id)
                ed_result = await self.session.execute(ed_stmt)
                entity_docs = ed_result.scalars().all()

                entity_ids = [ed.entity_id for ed in entity_docs]
                entity_stmt = select(Entity).where(
                    and_(Entity.id.in_(entity_ids), Entity.user_id == user_id)
                )
                entity_result = await self.session.execute(entity_stmt)
                entities = entity_result.scalars().all()

                entity_names = [e.name for e in entities]
                return {
                    "message": f"This document mentions {len(entity_names)} entit{'ies' if len(entity_names) != 1 else 'y'}: {', '.join(entity_names[:5])}.",
                }

            else:
                return {
                    "message": "Action not recognized. Please try again.",
                }

        except Exception as e:
            logger.error(f"Error handling action {action_id}: {e}", exc_info=True)
            raise

