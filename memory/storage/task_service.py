"""Task management service for high-level task operations."""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from .sqlite_backend import SQLiteBackend
from .task_models import CreateTaskRequest, Task, TaskStatus, UpdateTaskRequest

logger = logging.getLogger(__name__)


class TaskService:
    """High-level service for task management operations."""

    def __init__(self, storage_backend: SQLiteBackend):
        """Initialize the task service.

        Args:
            storage_backend: Storage backend for persistence
        """
        self.storage = storage_backend

    async def create_task(self, request: CreateTaskRequest) -> Task:
        """Create a new task from request."""
        task_id = str(uuid.uuid4())

        # Map CreateTaskRequest fields to Task fields
        task = Task(
            id=task_id,
            name=request.title,  # CreateTaskRequest has 'title', Task has 'name'
            description=request.description,
            instructions="",  # Task requires instructions, but CreateTaskRequest doesn't have it
            input_parameters=[],  # Task requires these fields
            output_parameters=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            usage_count=0,
        )

        await self.storage.store_task(task)
        logger.info(f"Created task {task_id}: {task.name}")

        return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return await self.storage.get_task(task_id)

    async def update_task(self, task_id: str, request: UpdateTaskRequest) -> Optional[Task]:
        """Update a task with provided changes."""
        # First get the existing task
        existing_task = await self.get_task(task_id)
        if not existing_task:
            return None

        # UpdateTaskRequest only has: title, description, status, user_feedback, user_rating
        # But Task model has: name, description, instructions, etc.
        # We need to update the Task object properly

        if request.title is not None:
            existing_task.name = request.title  # Map title to name
        if request.description is not None:
            existing_task.description = request.description
        # Task model doesn't have status, user_feedback, or user_rating fields
        # So we can't update those

        existing_task.updated_at = datetime.utcnow()

        # Update in storage
        success = await self.storage.update_task(existing_task)

        if success:
            logger.info(f"Updated task {task_id}")
            return existing_task

        return None

    async def assign_task(self, task_id: str, agent_id: str) -> bool:
        """Assign a task to an agent."""
        # Task model doesn't have agent_id or status fields
        # This method needs to be redesigned or Task model needs to be extended
        logger.warning("assign_task not implemented - Task model lacks agent_id and status fields")
        return False

    async def complete_task(
        self, task_id: str, result: dict[str, Any], artifacts: Optional[list[str]] = None
    ) -> bool:
        """Mark a task as completed with results."""
        # Task model doesn't have status, completed_at, result, or artifacts fields
        logger.warning("complete_task not implemented - Task model lacks required fields")
        return False

    async def fail_task(self, task_id: str, error_message: str) -> bool:
        """Mark a task as failed with error details."""
        # Task model doesn't have status, completed_at, or error_message fields
        logger.warning("fail_task not implemented - Task model lacks required fields")
        return False

    async def search_tasks(self, filters: Any) -> list[Task]:
        """Search tasks and return summaries."""
        # storage.search_tasks doesn't exist
        logger.warning("search_tasks not implemented - SQLiteBackend lacks this method")
        return []

    async def get_pending_tasks(self, limit: Optional[int] = None) -> list[Task]:
        """Get pending tasks available for assignment."""
        # storage.get_tasks_by_status doesn't exist
        logger.warning(
            "get_pending_tasks not implemented - SQLiteBackend lacks get_tasks_by_status"
        )
        return []

    async def get_agent_tasks(
        self, agent_id: str, status: Optional[TaskStatus] = None
    ) -> list[Task]:
        """Get tasks assigned to a specific agent."""
        # storage.search_tasks doesn't exist
        logger.warning("get_agent_tasks not implemented - SQLiteBackend lacks search_tasks")
        return []

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        return await self.storage.delete_task(task_id)

    async def get_task_dependencies(self, task_id: str) -> list[Task]:
        """Get tasks that depend on this task."""
        # Task model doesn't have dependencies field
        logger.warning("get_task_dependencies not implemented - Task model lacks dependencies")
        return []

    async def get_task_summary(self, task_id: str) -> dict[str, Any]:
        """Get task summary including progress and stats."""
        task = await self.get_task(task_id)
        if not task:
            return {}

        # Basic summary since Task model is simple
        return {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "usage_count": task.usage_count,
        }
