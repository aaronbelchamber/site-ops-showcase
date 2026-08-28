import threading
import uuid
import time
from contextlib import contextmanager
from typing import Dict, Any, Callable, Optional
from flask import jsonify
from src.logging.logger import logger

# How long a finished task stays visible in /api/system/status before eviction,
# and the hard cap on tracked tasks regardless of age (oldest-finished-first).
_TASK_RETENTION_SECONDS = 10 * 60
_MAX_TRACKED_TASKS = 500

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
                cls._instance._task_completed_epoch = {}
            return cls._instance

    def _purge_stale_tasks(self) -> None:
        """Evict finished tasks past retention age or beyond the tracked cap."""
        with self._lock:
            now = time.time()
            for tid, epoch in list(self._task_completed_epoch.items()):
                if now - epoch > _TASK_RETENTION_SECONDS:
                    self._tasks.pop(tid, None)
                    self._task_completed_epoch.pop(tid, None)

            excess = len(self._tasks) - _MAX_TRACKED_TASKS
            if excess > 0:
                finished_by_age = sorted(
                    self._task_completed_epoch.items(), key=lambda kv: kv[1]
                )
                for tid, _ in finished_by_age[:excess]:
                    self._tasks.pop(tid, None)
                    self._task_completed_epoch.pop(tid, None)

    @property
    def tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get the dictionary of all background tasks."""
        self._purge_stale_tasks()
        return self._tasks

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve task details by ID."""
        self._purge_stale_tasks()
        return self._tasks.get(task_id)

    def is_operation_in_progress(self, site_name: str) -> bool:
        """Check if a mutating operation is already in progress for the given site."""
        with self._lock:
            return site_name in self._site_locks and self._site_locks[site_name].locked()

    def _acquire_site_lock(self, site_name: str) -> bool:
        """Try to take the per-site operation lock without blocking."""
        with self._lock:
            if site_name not in self._site_locks:
                self._site_locks[site_name] = threading.Lock()
            return self._site_locks[site_name].acquire(blocking=False)

    def _release_site_lock(self, site_name: str) -> None:
        with self._lock:
            if site_name in self._site_locks:
                try:
                    self._site_locks[site_name].release()
                except RuntimeError:
                    pass  # already released
                # Drop the entry so _site_locks doesn't grow for the process
                # lifetime -- a fresh Lock is created on next acquire.
                del self._site_locks[site_name]

    @contextmanager
    def site_operation(self, site_name: Optional[str]):
        """
        Hold the per-site lock for an operation run synchronously in the request
        thread, so that endpoints which do real work inline (a live health check,
        a forced update scan) serialise against background tasks instead of
        stacking SSH sessions and browser launches on the same site.

        Yields True if the lock was taken, False if an operation is already
        running for that site.
        """
        if site_name is None:
            yield True
            return
        acquired = self._acquire_site_lock(site_name)
        try:
            yield acquired
        finally:
            if acquired:
                self._release_site_lock(site_name)

    def start_task(self, name: str, func: Callable, *args, site_name: Optional[str] = None, **kwargs) -> Optional[str]:
        """
        Run a function in a daemon thread.
        Returns the task_id, or None if site_name is provided and operation is already in progress.
        """
        if site_name is not None:
            if not self._acquire_site_lock(site_name):
                return None

        self._purge_stale_tasks()

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
                    self._task_completed_epoch[task_id] = time.time()
                logger.info(f"Background task completed successfully: {name} (ID: {task_id})")
            except Exception as e:
                if task_id in self._tasks:
                    self._tasks[task_id].update({
                        "status": "failed",
                        "progress": f"Failed: {e}",
                        "error": str(e),
                        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    })
                    self._task_completed_epoch[task_id] = time.time()
                logger.error(f"Background task failed: {name} (ID: {task_id}) - Error: {e}", exc_info=True)
            finally:
                with self._lock:
                    if thread_ident in self._thread_to_task:
                        del self._thread_to_task[thread_ident]
                if site_name is not None:
                    self._release_site_lock(site_name)

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


def site_operation(site_name: Optional[str]):
    """Context manager holding the per-site lock for a synchronous operation."""
    return _manager.site_operation(site_name)
