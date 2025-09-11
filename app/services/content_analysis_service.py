"""
Content Analysis Service for generating bullet points and analyzing document content
"""

import asyncio
import json
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.models import Document, User
from app.services.base_service import UserIsolatedService
from app.services.gemini_service import get_gemini_service, GeminiModel
from app.services.user_service import UserService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ContentAnalysisService(UserIsolatedService[Document]):
    """Service for analyzing document content and generating bullet points"""

    def __init__(self, session: AsyncSession):
        super().__init__(Document)
        self.session = session
        self.gemini_service = get_gemini_service()

    async def analyze_document_content(
        self,
        firebase_uid: str,
        document_id: int,
        analysis_type: str = "bullet_points"
    ) -> Optional[Document]:
        """
        Analyze document content and generate bullet points
        
        Args:
            firebase_uid: Firebase UID of the user
            document_id: ID of the document to analyze
            analysis_type: Type of analysis to perform (default: "bullet_points")
            
        Returns:
            Updated document with analysis results, or None if not found
        """
        try:
            # Get the document
            document = await self.get_document_by_id(firebase_uid, document_id)
            if not document:
                logger.error(f"Document {document_id} not found for user {firebase_uid}")
                return None

            # Check if document has content to analyze
            if not document.content or not document.content.strip():
                logger.warning(f"Document {document_id} has no content to analyze")
                await self._update_document_status(firebase_uid, document_id, "analysis_failed", {
                    'analysis_error': 'Document has no content to analyze'
                })
                return document

            # Update status to processing
            await self._update_document_status(firebase_uid, document_id, "analyzing")

            # Perform analysis based on type
            if analysis_type == "bullet_points":
                analysis_result = await self._generate_bullet_points(document.content)
            else:
                analysis_result = await self._perform_general_analysis(document.content, analysis_type)

            # Update document with analysis results
            await self._update_document_analysis(firebase_uid, document_id, analysis_result)

            # Update status to completed
            await self._update_document_status(firebase_uid, document_id, "analyzed")

            logger.info(f"Successfully analyzed document {document_id}")
            return await self.get_document_by_id(firebase_uid, document_id)

        except Exception as e:
            logger.error(f"Error analyzing document {document_id}: {str(e)}")
            await self._update_document_status(firebase_uid, document_id, "analysis_failed", {
                'analysis_error': str(e)
            })
            return None

    async def _generate_bullet_points(self, content: str) -> Dict[str, Any]:
        """
        Generate bullet points from document content using Gemini AI
        
        Args:
            content: Document content to analyze
            
        Returns:
            Dictionary containing bullet points and metadata
        """
        try:
            # Create a focused prompt for bullet point generation
            prompt = f"""Analyze the following content and extract the most important key points. 
            Return exactly 6 bullet points that capture the main ideas, facts, or insights.
            Each bullet point should be concise but informative.
            Format your response as a JSON object with a "bullet_points" array.
            
            Content:
            {content[:4000]}  # Limit content to avoid token limits
            """

            # Generate content using Gemini
            result = await self.gemini_service.generate_content(
                prompt=prompt,
                model=GeminiModel.FLASH,
                retry_count=2
            )

            if not result.get('success'):
                raise Exception(f"Gemini API call failed: {result}")

            # Parse the response
            bullet_points = self._parse_bullet_points_response(result['content'])
            
            return {
                'analysis_type': 'bullet_points',
                'bullet_points': bullet_points,
                'generated_at': datetime.now().isoformat(),
                'model_used': result.get('model', 'unknown'),
                'content_length': len(content),
                'success': True
            }

        except Exception as e:
            logger.error(f"Error generating bullet points: {str(e)}")
            return {
                'analysis_type': 'bullet_points',
                'bullet_points': [],
                'generated_at': datetime.now().isoformat(),
                'error': str(e),
                'success': False
            }

    async def _perform_general_analysis(self, content: str, analysis_type: str) -> Dict[str, Any]:
        """
        Perform general content analysis using Gemini AI
        
        Args:
            content: Document content to analyze
            analysis_type: Type of analysis to perform
            
        Returns:
            Dictionary containing analysis results
        """
        try:
            # Use the existing analyze_content method from GeminiService
            result = await self.gemini_service.analyze_content(
                content=content[:4000],  # Limit content to avoid token limits
                analysis_type=analysis_type,
                model=GeminiModel.FLASH
            )

            return {
                'analysis_type': analysis_type,
                'result': result.get('content', ''),
                'parsed_result': result.get('parsed_content', ''),
                'generated_at': datetime.now().isoformat(),
                'model_used': result.get('model', 'unknown'),
                'content_length': len(content),
                'success': True
            }

        except Exception as e:
            logger.error(f"Error performing {analysis_type} analysis: {str(e)}")
            return {
                'analysis_type': analysis_type,
                'result': '',
                'generated_at': datetime.now().isoformat(),
                'error': str(e),
                'success': False
            }

    def _parse_bullet_points_response(self, response: str) -> List[str]:
        """
        Parse bullet points from Gemini response
        
        Args:
            response: Raw response from Gemini
            
        Returns:
            List of bullet points
        """
        try:
            # Try to parse as JSON first
            try:
                parsed = json.loads(response)
                if isinstance(parsed, dict) and 'bullet_points' in parsed:
                    return parsed['bullet_points']
                elif isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

            # Fallback: extract bullet points from text
            bullet_points = []
            
            # Look for various bullet point patterns
            patterns = [
                r'•\s*(.+?)(?=\n|$)',  # • bullet points
                r'-\s*(.+?)(?=\n|$)',   # - bullet points
                r'\*\s*(.+?)(?=\n|$)',  # * bullet points
                r'\d+\.\s*(.+?)(?=\n|$)',  # numbered lists
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response, re.MULTILINE)
                if matches:
                    bullet_points.extend([match.strip() for match in matches])
                    break
            
            # If no patterns found, split by lines and clean up
            if not bullet_points:
                lines = response.split('\n')
                bullet_points = [
                    line.strip() 
                    for line in lines 
                    if line.strip() and len(line.strip()) > 10  # Filter out very short lines
                ]
            
            # Limit to 6 bullet points and clean up
            bullet_points = bullet_points[:6]
            bullet_points = [
                point.strip() 
                for point in bullet_points 
                if point.strip() and len(point.strip()) > 5
            ]
            
            return bullet_points

        except Exception as e:
            logger.error(f"Error parsing bullet points: {str(e)}")
            return []

    async def _update_document_status(
        self,
        firebase_uid: str,
        document_id: int,
        status: str,
        metadata_updates: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update document status and metadata"""
        try:
            document = await self.get_document_by_id(firebase_uid, document_id)
            if not document:
                return

            document.status = status
            
            if metadata_updates:
                if document.document_metadata is None:
                    document.document_metadata = {}
                document.document_metadata.update(metadata_updates)

            await self.session.commit()
            logger.debug(f"Updated document {document_id} status to {status}")

        except Exception as e:
            logger.error(f"Error updating document status: {str(e)}")

    async def _update_document_analysis(
        self,
        firebase_uid: str,
        document_id: int,
        analysis_result: Dict[str, Any]
    ) -> None:
        """Update document with analysis results"""
        try:
            document = await self.get_document_by_id(firebase_uid, document_id)
            if not document:
                return

            if document.document_metadata is None:
                document.document_metadata = {}
            
            document.document_metadata['content_analysis'] = analysis_result
            await self.session.commit()
            logger.debug(f"Updated document {document_id} with analysis results")

        except Exception as e:
            logger.error(f"Error updating document analysis: {str(e)}")

    async def get_document_by_id(
        self,
        firebase_uid: str,
        document_id: int
    ) -> Optional[Document]:
        """Get a specific document by ID for a user"""
        try:
            user = await UserService.get_or_create_user(self.session, firebase_uid)
            
            query = select(Document).where(
                and_(Document.id == document_id, Document.user_id == user.id)
            )
            
            result = await self.session.execute(query)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Error getting document {document_id}: {str(e)}")
            return None

    async def get_documents_ready_for_analysis(
        self,
        firebase_uid: str,
        limit: int = 10
    ) -> List[Document]:
        """Get documents that are ready for content analysis"""
        try:
            user = await UserService.get_or_create_user(self.session, firebase_uid)
            
            # Get documents that have content but haven't been analyzed yet
            query = select(Document).where(
                and_(
                    Document.user_id == user.id,
                    Document.content.isnot(None),
                    Document.content != '',
                    Document.status.in_(['processed', 'validated', 'embedded'])
                )
            ).limit(limit)
            
            result = await self.session.execute(query)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Error getting documents ready for analysis: {str(e)}")
            return []

    async def batch_analyze_documents(
        self,
        firebase_uid: str,
        document_ids: Optional[List[int]] = None,
        analysis_type: str = "bullet_points"
    ) -> Dict[str, Any]:
        """
        Analyze multiple documents in batch
        
        Args:
            firebase_uid: Firebase UID of the user
            document_ids: List of document IDs to analyze (if None, analyzes ready documents)
            analysis_type: Type of analysis to perform
            
        Returns:
            Dictionary with batch analysis results
        """
        try:
            if document_ids:
                # Analyze specific documents
                documents_to_analyze = []
                for doc_id in document_ids:
                    doc = await self.get_document_by_id(firebase_uid, doc_id)
                    if doc and doc.content:
                        documents_to_analyze.append(doc)
            else:
                # Get documents ready for analysis
                documents_to_analyze = await self.get_documents_ready_for_analysis(firebase_uid)

            results = {
                'total_documents': len(documents_to_analyze),
                'successful_analyses': 0,
                'failed_analyses': 0,
                'results': []
            }

            # Process each document
            for document in documents_to_analyze:
                try:
                    analysis_result = await self.analyze_document_content(
                        firebase_uid=firebase_uid,
                        document_id=document.id,
                        analysis_type=analysis_type
                    )
                    
                    if analysis_result:
                        results['successful_analyses'] += 1
                        results['results'].append({
                            'document_id': document.id,
                            'title': document.title,
                            'status': 'success'
                        })
                    else:
                        results['failed_analyses'] += 1
                        results['results'].append({
                            'document_id': document.id,
                            'title': document.title,
                            'status': 'failed'
                        })

                except Exception as e:
                    logger.error(f"Error analyzing document {document.id}: {str(e)}")
                    results['failed_analyses'] += 1
                    results['results'].append({
                        'document_id': document.id,
                        'title': document.title,
                        'status': 'error',
                        'error': str(e)
                    })

            logger.info(f"Batch analysis completed: {results['successful_analyses']} successful, {results['failed_analyses']} failed")
            return results

        except Exception as e:
            logger.error(f"Error in batch analysis: {str(e)}")
            return {
                'total_documents': 0,
                'successful_analyses': 0,
                'failed_analyses': 0,
                'error': str(e),
                'results': []
            }


# Global service instance
_content_analysis_service: Optional[ContentAnalysisService] = None


def get_content_analysis_service(session: AsyncSession) -> ContentAnalysisService:
    """Get a ContentAnalysisService instance"""
    return ContentAnalysisService(session)