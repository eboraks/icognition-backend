"""
Background Task Manager for Entity Extraction
"""

import asyncio
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.services.entity_extraction_service import get_entity_extraction_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


class EntityExtractionTaskManager:
    """Manager for entity extraction background tasks"""

    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.task_history: List[Dict[str, Any]] = []

    async def extract_entities_async(
        self,
        firebase_uid: str,
        document_id: int,
        content: str
    ) -> Dict[str, Any]:
        """
        Extract entities from a document asynchronously
        
        Args:
            firebase_uid: Firebase UID of the user
            document_id: ID of the document
            content: Document content
            
        Returns:
            Processing results dictionary
        """
        task_id = f"entity_extraction_{firebase_uid}_{document_id}"
        
        try:
            logger.info(f"Starting entity extraction for document {document_id}")
            
            # Get database session
            session_gen = get_session()
            session = await session_gen.__anext__()
            
            try:
                # Get entity extraction service
                entity_service = get_entity_extraction_service(session)
                
                # Process document entities
                result = await entity_service.process_document_entities(
                    firebase_uid, document_id, content
                )
                
                # Commit changes
                await session.commit()
                
                # Log task completion
                self._log_task_completion(task_id, result)
                
                return result
                
            finally:
                await session.close()
                
        except Exception as e:
            logger.error(f"Error in entity extraction task {task_id}: {e}")
            error_result = {
                'status': 'error',
                'message': str(e),
                'entities_processed': 0
            }
            self._log_task_completion(task_id, error_result)
            return error_result

    async def batch_extract_entities(
        self,
        firebase_uid: str,
        document_ids: List[int],
        max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        Extract entities from multiple documents in batch
        
        Args:
            firebase_uid: Firebase UID of the user
            document_ids: List of document IDs to process
            max_concurrent: Maximum number of concurrent tasks
            
        Returns:
            Batch processing results
        """
        logger.info(f"Starting batch entity extraction for {len(document_ids)} documents")
        
        # Get database session for fetching document content
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Get entity extraction service
            entity_service = get_entity_extraction_service(session)
            
            # Get documents ready for processing
            documents = await entity_service.get_documents_ready_for_entity_extraction(
                firebase_uid, limit=len(document_ids)
            )
            
            # Filter to only requested document IDs
            documents_to_process = [
                doc for doc in documents if doc.id in document_ids
            ]
            
            if not documents_to_process:
                return {
                    'status': 'success',
                    'message': 'No documents found for entity extraction',
                    'documents_processed': 0,
                    'total_entities': 0
                }
            
            # Process documents with concurrency control
            semaphore = asyncio.Semaphore(max_concurrent)
            tasks = []
            
            for document in documents_to_process:
                task = self._process_document_with_semaphore(
                    semaphore, firebase_uid, document.id, document.content
                )
                tasks.append(task)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            successful_results = []
            failed_results = []
            total_entities = 0
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_results.append({
                        'document_id': documents_to_process[i].id,
                        'error': str(result)
                    })
                else:
                    successful_results.append(result)
                    total_entities += result.get('entities_processed', 0)
            
            return {
                'status': 'success',
                'message': f'Batch processing completed',
                'documents_processed': len(successful_results),
                'documents_failed': len(failed_results),
                'total_entities': total_entities,
                'successful_results': successful_results,
                'failed_results': failed_results
            }
            
        finally:
            await session.close()

    async def _process_document_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        firebase_uid: str,
        document_id: int,
        content: str
    ) -> Dict[str, Any]:
        """Process a single document with semaphore for concurrency control"""
        async with semaphore:
            return await self.extract_entities_async(firebase_uid, document_id, content)

    def _log_task_completion(self, task_id: str, result: Dict[str, Any]):
        """Log task completion"""
        log_entry = {
            'task_id': task_id,
            'timestamp': datetime.utcnow().isoformat(),
            'result': result
        }
        
        self.task_history.append(log_entry)
        
        # Keep only last 100 task history entries
        if len(self.task_history) > 100:
            self.task_history = self.task_history[-100:]
        
        logger.info(f"Task {task_id} completed: {result.get('status', 'unknown')}")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task"""
        # Check active tasks
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            return {
                'task_id': task_id,
                'status': 'running',
                'done': task.done(),
                'cancelled': task.cancelled()
            }
        
        # Check task history
        for log_entry in reversed(self.task_history):
            if log_entry['task_id'] == task_id:
                return {
                    'task_id': task_id,
                    'status': 'completed',
                    'result': log_entry['result'],
                    'timestamp': log_entry['timestamp']
                }
        
        return None

    def get_task_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent task history"""
        return self.task_history[-limit:] if self.task_history else []

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            task.cancel()
            del self.active_tasks[task_id]
            logger.info(f"Cancelled task {task_id}")
            return True
        return False

    def cleanup_completed_tasks(self):
        """Clean up completed tasks from active tasks"""
        completed_tasks = []
        for task_id, task in self.active_tasks.items():
            if task.done():
                completed_tasks.append(task_id)
        
        for task_id in completed_tasks:
            del self.active_tasks[task_id]
        
        if completed_tasks:
            logger.info(f"Cleaned up {len(completed_tasks)} completed tasks")


# Global task manager instance
_entity_extraction_task_manager: Optional[EntityExtractionTaskManager] = None


def get_entity_extraction_task_manager() -> EntityExtractionTaskManager:
    """Get the global entity extraction task manager instance"""
    global _entity_extraction_task_manager
    if _entity_extraction_task_manager is None:
        _entity_extraction_task_manager = EntityExtractionTaskManager()
    return _entity_extraction_task_manager
