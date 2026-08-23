import threading
import uuid
import time
from typing import Dict, Any, Callable, Optional
from flask import jsonify
from src.logging.logger import logger

class BackgroundTaskManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BackgroundTaskManager, cls).__new__(cls)
                cls._instance._tasks = {}
                cls._instance._thread_to_task = {}
                cls._instance._site_locks = {}
            return cls._instance

    @property
    def tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get the dictionary of all background tasks."""
        return self._tasks

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve task details by ID."""
        return self._tasks.get(task_id)

    def is_operation_in_progress(self, site_name: str) -> bool:
        """Check if a mutating operation is already in progress for the given site."""
        with self._lock:
            return site_name in self._site_locks and self._site_locks[site_name].locked()

    def start_task(self, name: str, func: Callable, *args, site_name: Optional[str] = None, **kwargs) -> Optional[str]:
        """
        Run a function in a daemon thread.
        Returns the task_id, or None if site_name is provided and operation is already in progress.
        """
        if site_name is not None:
            with self._lock:
                if site_name not in self._site_locks:
                    self._site_locks[site_name] = threading.Lock()
                if not self._site_locks[site_name].acquire(blocking=False):
                    return None

        task_id = str(uuid.uuid4())
        self._tasks[task_id] = {
            "task_id": task_id,
            "name": name,
            "status": "running",
            "progress": "Initializing...",
            "result": None,
            "error": None,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "completed_at": None
        }

        logger.info(f"Background task started: {name} (ID: {task_id})")

        def run():
            thread_ident = threading.get_ident()
            self._thread_to_task[thread_ident] = task_id
            try:
                call_kwargs = dict(kwargs)
                if site_name is not None:
                    call_kwargs["site_name"] = site_name
                res = func(*args, **call_kwargs)
                if task_id in self._tasks:
                    self._tasks[task_id].update({
                        "status": "completed",
                        "progress": "Completed",
                        "result": res,
                        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    })
                logger.info(f"Background task completed successfully: {name} (ID: {task_id})")
            except Exception as e:
                if task_id in self._tasks:
                    self._tasks[task_id].update({
                        "status": "failed",
                        "progress": f"Failed: {e}",
                        "error": str(e),
                        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    })
                logger.error(f"Background task failed: {name} (ID: {task_id}) - Error: {e}", exc_info=True)
            finally:
                with self._lock:
                    if thread_ident in self._thread_to_task:
                        del self._thread_to_task[thread_ident]
                    if site_name is not None and site_name in self._site_locks:
                        self._site_locks[site_name].release()

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()
        return task_id

    def set_task_progress(self, progress: str) -> None:
        """Update progress string for the current thread's task."""
        thread_ident = threading.get_ident()
        task_id = self._thread_to_task.get(thread_ident)
        if task_id and task_id in self._tasks:
            self._tasks[task_id]["progress"] = progress

# Instantiate thread-safe singleton manager
_manager = BackgroundTaskManager()

# Backward-compatible references
BACKGROUND_TASKS = _manager.tasks
start_task = _manager.start_task


def operation_in_progress_response(site_name: str):
    """
    Standard 409 response for when start_task() returns None because a
    mutating operation is already in progress for the given site.
    """
    return jsonify({
        "success": False,
        "data": None,
        "error": f"An operation is already in progress for site '{site_name}'.",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }), 409

def set_task_progress(progress: str) -> None:
    """Set the progress status message for the current thread's task."""
    _manager.set_task_progress(progress)
