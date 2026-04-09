"""
Knowledge exploration service for managing filter trees and contextual chat interactions
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
import logging
import json
import re

from app.models import Document
from app.models_kg import KGNode, KGEdge, KGNodeDocument
from app.services.document_service import DocumentService
from app.services.prompt_service import get_prompt
from app.services.gemini_service import get_gemini_service, GeminiModel, GeminiConfig
from app.utils.logging import get_logger
from app.utils.text_utils import extract_text_from_html
from app.core.config import settings

logger = get_logger(__name__)

# Default prompt content for opening messages
DEFAULT_OPENING_MESSAGE_PROMPT = """You are a knowledge exploration assistant. The user has recently bookmarked or saved the following documents:

{documents_list}

For each document, you are provided:
- Document ID: [the exact numeric ID - you MUST use this exact ID in your response]
- Title: [document title]
- URL: [document url]
- Content preview: [first 500 characters of content]

CRITICAL: You MUST use the exact Document ID numbers provided above when creating buttons. Do NOT make up or guess document IDs.

Your task:
1. Analyze the documents to understand what they are about
2. Determine if the documents are related (same topic, theme, or subject)
3. Generate a natural, conversational opening message that:
   - Mentions the documents the user recently bookmarked
   - Describes what each document is about in a brief, engaging way
   - If documents are related, combine them: "You recently bookmarked 'doc1' and 'doc2' about [common topic]. Would you like to explore this topic?"
   - If documents are unrelated, mention them separately: "You recently bookmarked 'doc1' that is about [topic1] and 'doc2' that discussed [topic2]"
4. Determine which documents should have summary buttons:
   - DO NOT create summary buttons for short social media posts (e.g., Twitter/X posts, short comments)
   - DO create summary buttons for articles, blog posts, news articles, or substantial content
   - Consider content length and source type when making this decision
5. Format your response as JSON:
{{
  "message": "Your generated opening message text here",
  "buttons": [
    {{"document_id": <EXACT_ID_FROM_ABOVE>, "label": "Summary of [document title]"}},
    ...
  ]
}}

Important guidelines:
- Keep the message conversational and friendly
- Be specific about what each document discusses
- Only suggest summaries for documents that would benefit from summarization
- If all documents are too short for summaries, return an empty buttons array
- USE ONLY the document IDs provided in the document list above - do not use any other IDs
"""


def create_document_summary_button(document_id: int, document_title: str) -> Dict[str, Any]:
    """
    Create a button action for generating a document summary.
    
    Args:
        document_id: ID of the document
        document_title: Title of the document
        
    Returns:
        Dictionary with button action structure
    """
    return {
        "id": f"summary_doc_{document_id}",
        "label": f"Summary of {document_title}",
        "document_id": document_id,
        "action_type": "generate_summary"
    }


class KnowledgeService:
    """Service for knowledge exploration features"""

    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def _ensure_opening_message_prompt(self) -> str:
        """
        Get the opening message prompt from YAML.
        Returns the prompt content.
        """
        from app.services.prompt_utils import PromptType
        prompt = get_prompt(PromptType.OPENING_MESSAGE.value)
        return prompt.user_prompt if prompt else DEFAULT_OPENING_MESSAGE_PROMPT
    
    async def _generate_opening_message_from_documents(
        self, user_id: str, documents: List[Document], limit: int = 2
    ) -> Dict[str, Any]:
        """
        Generate an opening message using LLM based on latest documents.
        
        Args:
            user_id: User ID
            documents: List of Document objects
            limit: Number of documents to consider
            
        Returns:
            Dictionary with message and actions
        """
        try:
            logger.info(f"Generating opening message from {len(documents)} documents for user {user_id}")
            if not documents:
                logger.info("No documents found, returning default message")
                return {
                    "message": "Hello! I'm your knowledge exploration assistant. Use the filters on the left to navigate your knowledge graph, or ask me a question directly.",
                    "actions": [],
                }
            
            # Get or create the prompt
            prompt_template = await self._ensure_opening_message_prompt()
            
            # Format documents for the prompt - include document IDs so LLM uses correct ones
            documents_list_parts = []
            valid_document_ids = []  # Track which document IDs are valid for this user
            for i, doc in enumerate(documents[:limit], 1):
                valid_document_ids.append(doc.id)
                # Extract text preview (first 500 chars)
                content_preview = ""
                if doc.content:
                    cleaned_content = extract_text_from_html(doc.content)
                    content_preview = cleaned_content[:500] + ("..." if len(cleaned_content) > 500 else "")
                
                doc_info = f"""Document {i} (ID: {doc.id}):
- Title: {doc.title or 'Untitled'}
- URL: {doc.url or 'N/A'}
- Content preview: {content_preview}
"""
                documents_list_parts.append(doc_info)
            
            documents_list = "\n".join(documents_list_parts)
            
            # Format the prompt - only {documents_list} needs to be replaced
            formatted_prompt = prompt_template.format(
                documents_list=documents_list
            )
            
            # Call LLM to generate the message
            gemini_service = get_gemini_service()
            config = GeminiConfig(
                temperature=0.7,
                response_mime_type="application/json",
                max_output_tokens=2048  # Increased to prevent truncation
            )
            
            logger.info(f"Calling LLM with prompt length: {len(formatted_prompt)}")
            
            result = await gemini_service.generate_content(
                prompt=formatted_prompt,
                model=GeminiModel.FLASH,
                config=config
            )
            
            if not result.get("success"):
                logger.error(f"Failed to generate opening message: {result.get('error')}")
                raise Exception("Failed to generate opening message")
            
            # Parse JSON response - gemini_service returns 'content' not 'text'
            response_text = result.get("content", "") or result.get("text", "")
            
            if not response_text:
                logger.error("Empty response from LLM")
                raise Exception("Empty response from LLM")
            
            logger.info(f"LLM response received (length: {len(response_text)}): {response_text[:300]}...")  # Log first 300 chars
            
            # Try to extract JSON from the response (in case it's wrapped in markdown code blocks)
            response_text_clean = response_text.strip()
            if response_text_clean.startswith("```"):
                # Extract JSON from markdown code block
                lines = response_text_clean.split("\n")
                json_start = None
                json_end = None
                for i, line in enumerate(lines):
                    if line.strip().startswith("```") and json_start is None:
                        json_start = i + 1
                    elif line.strip().startswith("```") and json_start is not None:
                        json_end = i
                        break
                if json_start is not None and json_end is not None:
                    response_text_clean = "\n".join(lines[json_start:json_end])
                elif json_start is not None:
                    response_text_clean = "\n".join(lines[json_start:])
            
            # Try to fix truncated JSON by attempting to complete it
            def try_fix_truncated_json(text: str) -> Optional[dict]:
                """Try to fix truncated JSON by closing open structures"""
                try:
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    # Try to fix common truncation issues
                    fixed = text
                    
                    # Check if we're in the middle of a string (unterminated string error)
                    if "Unterminated string" in str(e) or fixed.count('"') % 2 != 0:
                        # Find the last quote and see if we're in a string value
                        # Look for patterns like: "key": "incomplete value...
                        # Find the last ":" before the truncation
                        last_colon = fixed.rfind(':')
                        if last_colon > 0:
                            # Check if there's an opening quote after the colon
                            after_colon = fixed[last_colon+1:].strip()
                            if after_colon.startswith('"'):
                                # We're in a string value, find where it starts
                                quote_start = last_colon + 1 + after_colon.find('"')
                                # Everything after the opening quote is the incomplete string
                                # Close it by adding a closing quote
                                fixed = fixed[:quote_start+1] + '"'
                    
                    # Count open braces and brackets
                    open_braces = fixed.count('{') - fixed.count('}')
                    open_brackets = fixed.count('[') - fixed.count(']')
                    
                    # Remove trailing comma if present
                    fixed = fixed.rstrip().rstrip(',')
                    
                    # Close brackets and braces
                    fixed += ']' * open_brackets
                    fixed += '}' * open_braces
                    
                    try:
                        return json.loads(fixed)
                    except json.JSONDecodeError:
                        # If still failing, try a more aggressive fix: extract what we can
                        # Try to find a valid JSON object by removing the last incomplete item
                        if '"buttons"' in fixed:
                            # Try to extract just the message if buttons are incomplete
                            message_match = re.search(r'"message"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', fixed)
                            if message_match:
                                return {
                                    "message": message_match.group(1),
                                    "buttons": []
                                }
                        return None
            
            try:
                llm_response = json.loads(response_text_clean)
            except json.JSONDecodeError as e:
                logger.warning(f"Initial JSON parse failed: {e}, attempting to fix truncated JSON")
                # Try to fix truncated JSON
                llm_response = try_fix_truncated_json(response_text_clean)
                
                if llm_response is None:
                    logger.error(f"Failed to parse LLM JSON response even after fix attempt")
                    logger.error(f"Response text (first 1000 chars): {response_text_clean[:1000]}")
                    # Fallback to default message
                    return {
                        "message": "Hello! I'm your knowledge exploration assistant. Use the filters on the left to navigate your knowledge graph, or ask me a question directly.",
                        "actions": [],
                    }
            
            # Extract message and buttons
            message = llm_response.get("message", "Hello! I'm your knowledge exploration assistant.")
            buttons = llm_response.get("buttons", [])
            
            logger.info(f"Extracted message: {message[:100]}..., buttons: {len(buttons)}")
            
            # Convert buttons to actions format
            # IMPORTANT: Only include buttons for documents that actually belong to this user
            actions = []
            for button in buttons:
                doc_id = button.get("document_id")
                label = button.get("label", f"Summary of document {doc_id}")
                
                # Validate that the document ID is in our valid list
                if doc_id and doc_id in valid_document_ids:
                    # Extract document title from label (remove "Summary of " prefix if present)
                    doc_title = label.replace("Summary of ", "").strip()
                    actions.append(create_document_summary_button(doc_id, doc_title))
                    logger.info(f"Added button for document {doc_id}: {doc_title}")
                elif doc_id:
                    logger.warning(f"Skipping button for document {doc_id} - not in valid document list {valid_document_ids}")
            
            logger.info(f"Created {len(actions)} valid action buttons from {len(buttons)} LLM buttons")
            
            logger.info(f"Returning opening message with {len(actions)} actions")
            return {
                "message": message,
                "actions": actions,
            }
            
        except Exception as e:
            logger.error(f"Error generating opening message from documents: {e}", exc_info=True)
            # Fallback to default message
            return {
                "message": "Hello! I'm your knowledge exploration assistant. Use the filters on the left to navigate your knowledge graph, or ask me a question directly.",
                "actions": [],
            }

    async def get_filter_tree(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get the complete filter tree structure for a user.
        Returns a list of documents, each with nested entities grouped by type.
        Hierarchy: Document -> Entity Type -> Entity Name
        """
        try:
            # 1. Get all documents for the user
            doc_stmt = select(Document)
            if not settings.DISABLE_AUTH:
                doc_stmt = doc_stmt.where(Document.user_id == user_id)
                
            doc_result = await self.session.execute(doc_stmt)
            documents = doc_result.scalars().all()

            if not documents:
                return []

            doc_ids = [d.id for d in documents]

            # 2. Get all KG nodes linked to these documents
            node_join_stmt = (
                select(KGNode)
                .join(KGNodeDocument, KGNode.id == KGNodeDocument.node_id)
                .where(KGNodeDocument.document_id.in_(doc_ids))
                .distinct()
            )

            node_result = await self.session.execute(node_join_stmt)
            entities = node_result.scalars().all()
            entities_dict = {e.id: e for e in entities}
            entity_ids = list(entities_dict.keys())

            # 3. Get node-document relationships for these specific nodes and documents
            if entity_ids:
                ed_stmt = (
                    select(KGNodeDocument.node_id, KGNodeDocument.document_id)
                    .where(
                        and_(
                            KGNodeDocument.node_id.in_(entity_ids),
                            KGNodeDocument.document_id.in_(doc_ids)
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
                    entity_type = entity.raw_type or "Other"
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
                    entity_key = f"{entity.label.lower()}-{entity.id}"

                    if entity_key not in group_entry["entities"]:
                        group_entry["entities"][entity_key] = {
                            "key": f"entity-{entity.id}",
                            "label": entity.label,
                            "data": {
                                "type": "entity",
                                "id": entity.id,
                                "name": entity.label,
                                "entity_type": entity.raw_type,
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
                # Get entity information - we don't filter by user_id on Entity anymore
                # instead we ensure it's linked to a document the user owns (below)
                entity_stmt = select(KGNode).where(KGNode.id == entity_id)
                entity_result = await self.session.execute(entity_stmt)
                entity = entity_result.scalar_one_or_none()

                if not entity:
                    entity_not_found_msg = f"Entity {entity_id} not found"
                    if not settings.DISABLE_AUTH:
                        entity_not_found_msg += f" for user {user_id}"
                    raise ValueError(entity_not_found_msg)

                # Get documents related to this entity
                ed_stmt = select(KGNodeDocument).where(KGNodeDocument.node_id == entity_id)
                ed_result = await self.session.execute(ed_stmt)
                entity_docs = ed_result.scalars().all()

                doc_ids = [ed.document_id for ed in entity_docs]
                doc_stmt = select(Document).where(Document.id.in_(doc_ids))
                if not settings.DISABLE_AUTH:
                    doc_stmt = doc_stmt.where(Document.user_id == user_id)
                doc_result = await self.session.execute(doc_stmt)
                documents = doc_result.scalars().all()

                # Generate contextual message
                doc_count = len(documents)
                message = f"You've selected '{entity.label}'. I found {doc_count} document{'s' if doc_count != 1 else ''} related to {'him' if entity.raw_type == 'Person' else 'it'} in your library. What would you like to explore next?"

                # Generate suggested actions
                actions = [
                    {"id": "learn_more", "label": f"Learn more about {entity.label}"},
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
                        "name": entity.label,
                        "type": entity.raw_type,
                        "description": entity_info,
                    },
                    "document_count": doc_count,
                }

            elif document_id:
                # Get document information
                doc_stmt = select(Document).where(Document.id == document_id)
                if not settings.DISABLE_AUTH:
                    doc_stmt = doc_stmt.where(Document.user_id == user_id)
                    
                doc_result = await self.session.execute(doc_stmt)
                document = doc_result.scalar_one_or_none()

                if not document:
                    doc_not_found_msg = f"Document {document_id} not found"
                    if not settings.DISABLE_AUTH:
                        doc_not_found_msg += f" for user {user_id}"
                    raise ValueError(doc_not_found_msg)

                message = f"You've selected '{document.title or 'Untitled'}'. What would you like to know about this document?"

                actions = [
                    {"id": "summarize", "label": "Summarize this document"},
                    {"id": "bullet_points", "label": "Show key points"},
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
                # Default case: Generate opening message based on latest documents
                document_service = DocumentService(self.session)
                # Get latest documents (default 2, configurable)
                latest_documents = await document_service.get_latest_documents(
                    user_id=user_id,
                    limit=2  # Can be made configurable via settings
                )
                
                # Generate opening message using LLM
                return await self._generate_opening_message_from_documents(
                    user_id=user_id,
                    documents=latest_documents,
                    limit=2
                )

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
            # Handle document summary generation from opening message buttons
            if action_id.startswith("summary_doc_"):
                try:
                    # Extract document_id from action_id (format: "summary_doc_123")
                    doc_id_str = action_id.split("_")[-1]
                    doc_id = int(doc_id_str)
                except (ValueError, IndexError):
                    raise ValueError(f"Invalid document summary action ID: {action_id}")
                
                # Get the document - need to resolve user_id properly
                # user_id is Firebase UID, need to get the User object first (same pattern as get_latest_documents)
                from app.services.user_service import UserService
                
                # Get the user object to ensure user exists and get proper user.id
                user = await UserService.get_user_by_firebase_uid(self.session, user_id)
                if not user:
                    raise ValueError(f"User {user_id} not found")
                
                # Now query document using user.id (which is the Firebase UID stored in users table)
                # Document.user_id is a foreign key to users.id, so it stores the Firebase UID
                doc_stmt = select(Document).where(Document.id == doc_id)
                if not settings.DISABLE_AUTH:
                    # Get the user object to ensure user exists and get proper user.id
                    user = await UserService.get_user_by_firebase_uid(self.session, user_id)
                    if not user:
                        raise ValueError(f"User {user_id} not found")
                    doc_stmt = doc_stmt.where(Document.user_id == user.id)
                    
                doc_result = await self.session.execute(doc_stmt)
                document = doc_result.scalar_one_or_none()
                
                if not document:
                    # Log more details for debugging
                    logger.error(f"Document {doc_id} not found for user {user_id} (user.id: {user.id})")
                    # Try to see if document exists at all
                    check_stmt = select(Document).where(Document.id == doc_id)
                    check_result = await self.session.execute(check_stmt)
                    check_doc = check_result.scalar_one_or_none()
                    if check_doc:
                        logger.error(f"Document {doc_id} exists but belongs to user {check_doc.user_id}, not {user.id}")
                    raise ValueError(f"Document {doc_id} not found for user {user_id}")
                
                # Generate summary using GeminiService
                try:
                    gemini_service = get_gemini_service()
                    
                    # Extract and clean content
                    content = document.content or ""
                    if content:
                        content = extract_text_from_html(content)
                        # Limit content length for API efficiency
                        content = content[:4000] if len(content) > 4000 else content
                    
                    if not content or not content.strip():
                        return {
                            "message": f"Sorry, I couldn't generate a summary for '{document.title or 'Untitled'}' because the document has no readable content.",
                        }
                    
                    # Get template from YAML
                    from app.services.prompt_utils import PromptType
                    db_prompt = get_prompt(PromptType.CONTENT_SUMMARY.value)
                    
                    if db_prompt:
                        system_prompt = db_prompt.system_prompt or ""
                        user_template = db_prompt.user_prompt
                        try:
                            user_prompt = user_template.format(content=content, title=document.title or "Untitled")
                            prompt = f"{system_prompt}\n\n{user_prompt}"
                        except (KeyError, ValueError):
                            prompt = f"{system_prompt}\n\n{user_template}\n\nContent: {content}"
                    else:
                        # Create summary prompt
                        prompt_parts = [
                            "Please provide a concise summary of the following document.",
                            "The summary should be 2-3 sentences that capture the main points and key information.",
                            "Focus on the most important ideas and avoid unnecessary details."
                        ]
                        
                        if document.title:
                            prompt_parts.append(f"Title: {document.title}")
                        
                        prompt_parts.extend([
                            "",
                            "Content:",
                            content
                        ])
                        
                        prompt = "\n".join(prompt_parts)
                    
                    # Generate summary using Gemini
                    config = GeminiConfig(
                        temperature=0.3,
                        max_output_tokens=300,
                        response_mime_type="text/plain"
                    )
                    
                    result = await gemini_service.generate_content(
                        prompt=prompt,
                        model=GeminiModel.FLASH,
                        config=config
                    )
                    
                    if result.get("success") and result.get("text"):
                        summary = result["text"].strip()
                        message = f"**Summary of '{document.title or 'Untitled'}':**\n\n{summary}"
                        if document.url:
                            message += f"\n\n[View full document]({document.url})"
                    else:
                        # Fallback if AI generation fails
                        error_msg = result.get("error", "Unknown error")
                        logger.error(f"Failed to generate summary: {error_msg}")
                        message = f"**Summary of '{document.title or 'Untitled'}':**\n\nI encountered an error while generating the summary. Please try again later."
                    
                    return {
                        "message": message,
                    }
                    
                except Exception as e:
                    logger.error(f"Error generating document summary: {e}", exc_info=True)
                    return {
                        "message": f"Sorry, I encountered an error while generating a summary for '{document.title or 'Untitled'}'. Please try again later.",
                    }
            
            if action_id == "learn_more" and entity_id:
                # Get entity information
                entity_stmt = select(KGNode).where(KGNode.id == entity_id)
                entity_result = await self.session.execute(entity_stmt)
                entity = entity_result.scalar_one_or_none()

                if not entity:
                    raise ValueError(f"Entity {entity_id} not found")

                # Get related documents
                ed_stmt = select(KGNodeDocument).where(KGNodeDocument.node_id == entity_id)
                ed_result = await self.session.execute(ed_stmt)
                entity_docs = ed_result.scalars().all()

                doc_ids = [ed.document_id for ed in entity_docs]
                doc_stmt = select(Document).where(Document.id.in_(doc_ids))
                if not settings.DISABLE_AUTH:
                    doc_stmt = doc_stmt.where(Document.user_id == user_id)
                doc_result = await self.session.execute(doc_stmt)
                documents = doc_result.scalars().all()

                # Build response with entity information
                response_parts = []
                if entity.description or entity.wikidata_description:
                    description = entity.description or entity.wikidata_description
                    response_parts.append(description)
                else:
                    response_parts.append(f"{entity.label} is a {entity.raw_type or 'entity'} in your knowledge graph.")

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
                    ed_stmt = select(KGNodeDocument).where(KGNodeDocument.node_id == entity_id)
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

            elif action_id == "bullet_points" and document_id:
                # Get bullet points for the document
                doc_stmt = select(Document).where(
                    and_(Document.id == document_id, Document.user_id == user_id)
                )
                doc_result = await self.session.execute(doc_stmt)
                document = doc_result.scalar_one_or_none()

                if not document:
                    raise ValueError(f"Document {document_id} not found")

                if document.ai_bullet_points and len(document.ai_bullet_points) > 0:
                    bullet_points_text = "\n".join([f"• {point}" for point in document.ai_bullet_points])
                    return {
                        "message": f"Key points for '{document.title or 'Untitled'}':\n\n{bullet_points_text}",
                    }
                else:
                    return {
                        "message": f"No bullet points available for '{document.title or 'Untitled'}'. The document may still be processing.",
                    }

            elif action_id == "entities" and document_id:
                # Get entities related to this document
                ed_stmt = select(KGNodeDocument).where(KGNodeDocument.document_id == document_id)
                ed_result = await self.session.execute(ed_stmt)
                entity_docs = ed_result.scalars().all()

                entity_ids = [ed.entity_id for ed in entity_docs]
                entity_stmt = select(KGNode).where(
                    and_(KGNode.id.in_(entity_ids), KGNode.user_id == user_id)
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

    async def get_entity_relationships(self, entity_id: int) -> Dict[str, Any]:
        """
        Return an entity and all its directed relationships (as from or to).
        """
        entity_result = await self.session.execute(
            select(KGNode).where(KGNode.id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")

        edge_result = await self.session.execute(
            select(KGEdge)
            .where(
                or_(
                    KGEdge.from_node_id == entity_id,
                    KGEdge.to_node_id == entity_id,
                )
            )
            .limit(50)
        )
        relationships = edge_result.scalars().all()

        # Fetch all referenced nodes in one query
        related_ids: set[int] = set()
        for r in relationships:
            related_ids.add(r.from_node_id)
            related_ids.add(r.to_node_id)
        related_ids.discard(entity_id)

        node_map: Dict[int, KGNode] = {entity.id: entity}
        if related_ids:
            extra_result = await self.session.execute(
                select(KGNode).where(KGNode.id.in_(related_ids))
            )
            for e in extra_result.scalars().all():
                node_map[e.id] = e

        formatted = []
        for r in relationships:
            from_e = node_map.get(r.from_node_id)
            to_e = node_map.get(r.to_node_id)
            if from_e and to_e:
                formatted.append({
                    "from_entity": {"id": from_e.id, "name": from_e.label, "type": from_e.raw_type},
                    "relationship_type": r.property_label,
                    "to_entity": {"id": to_e.id, "name": to_e.label, "type": to_e.raw_type},
                })

        return {
            "entity": {
                "id": entity.id,
                "name": entity.label,
                "type": entity.raw_type,
                "description": entity.description,
            },
            "relationships": formatted,
        }

