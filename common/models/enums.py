"""Enumerations used across the Metagen system."""

from enum import Enum


class TurnStatus(str, Enum):
    """Status of a conversation turn."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"
    PARTIAL = "partial"
    ABANDONED = "abandoned"  # For turns that were in-flight when the system was shut down


class ToolUsageStatus(str, Enum):
    """Status of tool usage."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCELLED = "CANCELLED"
    PENDING_APPROVAL = "PENDING_APPROVAL"  # Waiting for user approval
    ABANDONED = "ABANDONED"  # For tools that were in-flight when the system was shut down


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"  # Task created but not started
    IN_PROGRESS = "in_progress"  # Task currently being executed
    COMPLETED = "completed"  # Task finished successfully
    FAILED = "failed"  # Task failed with error
    CANCELLED = "cancelled"  # Task cancelled by user
    PAUSED = "paused"  # Task paused for user input
    ABANDONED = "abandoned"  # Task was in-flight when system shut down


class ToolExecutionStage(str, Enum):
    """Stages of tool execution lifecycle (used by agents)."""

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"  # For tools that were in-flight when the system was shut down


class ParameterType(str, Enum):
    """Supported parameter types for tasks."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
