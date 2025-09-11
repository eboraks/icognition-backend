"""
Background Task Manager for Content Analysis
"""

import asyncio
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.services.content_analysis_service import get_content_analysis_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ContentAnalysisTaskManager:
    """Manager for content analysis background tasks"""

    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.task_history: List[Dict[str, Any]] = []

    async def analyze_document_async(
        self,
        firebase_uid: str,
        document_id: int,
        analysis_type: str = "bullet_points"
    ) -> Dict[str, Any]:
        """
        Analyze a document asynchronously
        
        Args:
            firebase_uid: Firebase UID of the user
            document_id: ID of the document to analyze
            analysis_type: Type of analysis to perform
            
        Returns:
            Dictionary with task information
        """
        task_id = f"analysis_{firebase_uid}_{document_id}"
        
        # Check if task is already running
        if task_id in self.active_tasks:
            return {
                'task_id': task_id,
                'status': 'already_running',
                'message': 'Analysis task is already running for this document'
            }

        try:
            # Create the background task
            task = asyncio.create_task(
                self._run_analysis_task(firebase_uid, document_id, analysis_type, task_id)
            )
            
            self.active_tasks[task_id] = task
            
            # Add to history
            self.task_history.append({
                'task_id': task_id,
                'firebase_uid': firebase_uid,
                'document_id': document_id,
                'analysis_type': analysis_type,
                'started_at': datetime.now(),
                'status': 'started'
            })

            logger.info(f"Started background analysis task {task_id}")
            
            return {
                'task_id': task_id,
                'status': 'started',
                'message': 'Analysis task started successfully'
            }

        except Exception as e:
            logger.error(f"Error starting analysis task: {str(e)}")
            return {
                'task_id': task_id,
                'status': 'error',
                'message': f'Failed to start analysis task: {str(e)}'
            }

    async def batch_analyze_documents_async(
        self,
        firebase_uid: str,
        document_ids: Optional[List[int]] = None,
        analysis_type: str = "bullet_points"
    ) -> Dict[str, Any]:
        """
        Analyze multiple documents asynchronously
        
        Args:
            firebase_uid: Firebase UID of the user
            document_ids: List of document IDs to analyze (if None, analyzes ready documents)
            analysis_type: Type of analysis to perform
            
        Returns:
            Dictionary with batch task information
        """
        task_id = f"batch_analysis_{firebase_uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # Create the background task
            task = asyncio.create_task(
                self._run_batch_analysis_task(firebase_uid, document_ids, analysis_type, task_id)
            )
            
            self.active_tasks[task_id] = task
            
            # Add to history
            self.task_history.append({
                'task_id': task_id,
                'firebase_uid': firebase_uid,
                'document_ids': document_ids,
                'analysis_type': analysis_type,
                'started_at': datetime.now(),
                'status': 'started'
            })

            logger.info(f"Started batch analysis task {task_id}")
            
            return {
                'task_id': task_id,
                'status': 'started',
                'message': 'Batch analysis task started successfully'
            }

        except Exception as e:
            logger.error(f"Error starting batch analysis task: {str(e)}")
            return {
                'task_id': task_id,
                'status': 'error',
                'message': f'Failed to start batch analysis task: {str(e)}'
            }

    async def _run_analysis_task(
        self,
        firebase_uid: str,
        document_id: int,
        analysis_type: str,
        task_id: str
    ) -> None:
        """Run the actual analysis task"""
        try:
            # Get database session
            session_gen = get_session()
            session = await session_gen.__anext__()
            
            try:
                # Get analysis service
                analysis_service = get_content_analysis_service(session)
                
                # Run the analysis
                result = await analysis_service.analyze_document_content(
                    firebase_uid=firebase_uid,
                    document_id=document_id,
                    analysis_type=analysis_type
                )
                
                # Update task status
                self._update_task_status(task_id, 'completed', {
                    'document_id': document_id,
                    'result': 'success' if result else 'failed'
                })
                
                logger.info(f"Completed analysis task {task_id}")
                
            finally:
                await session.close()
                
        except Exception as e:
            logger.error(f"Error in analysis task {task_id}: {str(e)}")
            self._update_task_status(task_id, 'failed', {'error': str(e)})
            
        finally:
            # Remove from active tasks
            self.active_tasks.pop(task_id, None)

    async def _run_batch_analysis_task(
        self,
        firebase_uid: str,
        document_ids: Optional[List[int]],
        analysis_type: str,
        task_id: str
    ) -> None:
        """Run the actual batch analysis task"""
        try:
            # Get database session
            session_gen = get_session()
            session = await session_gen.__anext__()
            
            try:
                # Get analysis service
                analysis_service = get_content_analysis_service(session)
                
                # Run the batch analysis
                result = await analysis_service.batch_analyze_documents(
                    firebase_uid=firebase_uid,
                    document_ids=document_ids,
                    analysis_type=analysis_type
                )
                
                # Update task status
                self._update_task_status(task_id, 'completed', result)
                
                logger.info(f"Completed batch analysis task {task_id}")
                
            finally:
                await session.close()
                
        except Exception as e:
            logger.error(f"Error in batch analysis task {task_id}: {str(e)}")
            self._update_task_status(task_id, 'failed', {'error': str(e)})
            
        finally:
            # Remove from active tasks
            self.active_tasks.pop(task_id, None)

    def _update_task_status(self, task_id: str, status: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Update task status in history"""
        for task_record in self.task_history:
            if task_record['task_id'] == task_id:
                task_record['status'] = status
                task_record['completed_at'] = datetime.now()
                if metadata:
                    task_record['metadata'] = metadata
                break

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
        
        # Check history
        for task_record in self.task_history:
            if task_record['task_id'] == task_id:
                return task_record
        
        return None

    def get_all_tasks(self, firebase_uid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all tasks, optionally filtered by user"""
        tasks = []
        
        # Add active tasks
        for task_id, task in self.active_tasks.items():
            task_info = {
                'task_id': task_id,
                'status': 'running',
                'done': task.done(),
                'cancelled': task.cancelled()
            }
            
            # Extract firebase_uid from task_id if possible
            if firebase_uid is None or firebase_uid in task_id:
                tasks.append(task_info)
        
        # Add completed tasks from history
        for task_record in self.task_history:
            if firebase_uid is None or task_record.get('firebase_uid') == firebase_uid:
                tasks.append(task_record)
        
        return tasks

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            task.cancel()
            self._update_task_status(task_id, 'cancelled')
            logger.info(f"Cancelled task {task_id}")
            return True
        return False

    def get_task_statistics(self) -> Dict[str, Any]:
        """Get statistics about tasks"""
        total_tasks = len(self.task_history)
        active_tasks = len(self.active_tasks)
        
        status_counts = {}
        for task_record in self.task_history:
            status = task_record.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            'total_tasks': total_tasks,
            'active_tasks': active_tasks,
            'completed_tasks': status_counts.get('completed', 0),
            'failed_tasks': status_counts.get('failed', 0),
            'cancelled_tasks': status_counts.get('cancelled', 0),
            'status_counts': status_counts
        }


# Global task manager instance
_task_manager: Optional[ContentAnalysisTaskManager] = None


def get_content_analysis_task_manager() -> ContentAnalysisTaskManager:
    """Get the global content analysis task manager"""
    global _task_manager
    if _task_manager is None:
        _task_manager = ContentAnalysisTaskManager()
    return _task_manager
