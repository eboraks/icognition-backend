import threading
from typing import Callable, Any
from app.log import get_logger
import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor

logger = get_logger(__name__)

class ThreadEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """Event loop policy that creates an event loop per thread"""
    def __init__(self):
        super().__init__()
        self._loop_map = {}
        self._lock = threading.Lock()

    def get_event_loop(self):
        """Get the event loop for current thread, creating one if needed."""
        thread_id = threading.get_ident()
        with self._lock:
            if thread_id not in self._loop_map:
                loop = self.new_event_loop()
                self.set_event_loop(loop)
                self._loop_map[thread_id] = loop
            return self._loop_map[thread_id]

    def set_event_loop(self, loop):
        """Set the event loop for current thread."""
        thread_id = threading.get_ident()
        with self._lock:
            self._loop_map[thread_id] = loop

class BackgroundTaskManager:
    def __init__(self):
        self._threads = []
        self._executor = ThreadPoolExecutor(max_workers=10)
        # Set custom event loop policy
        asyncio.set_event_loop_policy(ThreadEventLoopPolicy())

    def _run_async_in_thread(self, func: Callable, *args, **kwargs):
        """Runs an async function in a thread with its own event loop"""
        try:
            # Get the event loop for this thread
            loop = asyncio.get_event_loop()
            
            # Run the async function
            result = loop.run_until_complete(func(*args, **kwargs))
            return result
            
        except Exception as e:
            logger.error(f"Error running async task {func.__name__}: {str(e)}")
            raise e

    def add_task(self, func: Callable, *args, **kwargs):
        """Adds a new background task to be executed in a thread"""
        if asyncio.iscoroutinefunction(func):
            thread = threading.Thread(
                target=self._run_async_in_thread,
                args=(func,) + args,
                kwargs=kwargs
            )
        else:
            thread = threading.Thread(
                target=func,
                args=args,
                kwargs=kwargs
            )

        thread.daemon = True
        thread.start()
        self._threads.append(thread)
        
        logger.info(f"Started background task {func.__name__} in thread {thread.ident}")
        return thread

    def wait_for_all(self):
        """Waits for all background tasks to complete"""
        for thread in self._threads:
            thread.join()
        self._threads = []

# Create a singleton instance
task_manager = BackgroundTaskManager() 