"""Pydantic models for three-tier memory system."""

import os
from dataclasses import dataclass, fields
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


# Configuration
@dataclass
class MemoryConfig:
    """Centralized configuration for memory management"""

    # Compaction settings
    compaction_token_threshold: int = 10000  # Tokens needed before compaction
    compaction_min_turns: int = 5  # Minimum turns before considering compaction
    compaction_max_tokens_per_batch: int = 50000  # Max tokens to compact at once

    # Search settings
    search_max_memories: int = 100  # Max semantic memories to search through
    search_result_limit: int = 10  # Max results to return
    search_cache_ttl: int = 3600  # Cache TTL in seconds

    # Context building
    context_recent_turns_limit: int = 10  # Recent turns to include
    context_compact_memories_limit: int = 2  # Compact memories to include
    context_semantic_memories_limit: int = 3  # Semantic memories to include
    context_max_tokens: int = 100000  # Max context size

    # Background processing
    scheduler_check_interval: int = 300  # Check every 5 minutes
    semantic_processing_delay: int = 600  # Wait 10 min after compaction

    # Runtime modification
    def update(self, **kwargs: Any) -> None:
        """Update configuration at runtime"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                raise ValueError(f"Unknown config key: {key}")

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        """Load config from environment variables"""
        config = cls()
        # Override from env vars like MEMORY_COMPACTION_TOKEN_THRESHOLD
        for field in fields(cls):
            env_key = f"MEMORY_{field.name.upper()}"
            if env_value := os.getenv(env_key):
                setattr(config, field.name, type(getattr(config, field.name))(env_value))
        return config


# Memory Content Classification
class MemoryContentType(str, Enum):
    """Content classification for compact and semantic memories"""

    TASK = "task"  # Task-related content including task-specific preferences
    EKG = "ekg"  # Enterprise Knowledge Graph - factual information about entities and relationships
    GENERAL = "general"  # Task-agnostic user preferences and general knowledge


# Compact Memory Models
class CompactMemory(BaseModel):
    """Model for compact memories (medium-term)"""

    id: str = Field(..., description="Unique compact memory ID")
    created_at: datetime = Field(..., description="When this compact memory was created")
    start_time: datetime = Field(..., description="Start time of conversations covered")
    end_time: datetime = Field(..., description="End time of conversations covered")
    task_ids: Optional[list[str]] = Field(
        None, description="Task IDs covered (null for general conversations)"
    )
    summary: str = Field(..., description="Compressed summary of conversations")
    key_points: list[str] = Field(default_factory=list, description="Important points")
    entities: dict[str, list[str]] = Field(default_factory=dict, description="Extracted entities")
    semantic_labels: list[str] = Field(default_factory=list, description="Semantic tags")
    turn_count: int = Field(..., description="Number of turns compacted")
    token_count: int = Field(..., description="Original token count")
    compressed_token_count: int = Field(..., description="Compressed token count")
    processed: bool = Field(False, description="Whether processed into semantic memories")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# Long-term Memory Models
class LongTermMemory(BaseModel):
    """Model for long-term memories"""

    id: str = Field(..., description="Unique long-term memory ID")
    created_at: datetime = Field(..., description="When this memory was created")
    updated_at: datetime = Field(..., description="When this memory was last updated")
    task_id: Optional[str] = Field(
        None, description="Task ID if this memory relates to a specific task"
    )
    content: str = Field(..., description="Memory content")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# LLM Schema Models for Structured Output
class CompactMemorySchema(BaseModel):
    """Schema for LLM-generated compact memories"""

    summary: str = Field(..., description="Concise summary of the conversations")
    key_points: list[str] = Field(..., description="Important points to remember")
    entities: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Extracted entities by type (people, projects, tools, etc.)",
    )
    semantic_labels: list[str] = Field(
        default_factory=list, description="Semantic tags describing the topics"
    )


class UserPreferenceSchema(BaseModel):
    """Schema for user preferences extracted by LLM"""

    topic: str = Field(
        ...,
        description=(
            "Topic of the preference (e.g., 'tool_usage', 'tone', 'style', 'output_format')"
        ),
    )
    title: str = Field(..., description="Brief title for the preference")
    content: str = Field(..., description="Full description of the preference")
    summary: str = Field(..., description="Brief summary of the preference")
    tags: list[str] = Field(default_factory=list, description="Related tags")


class LongTermMemorySchema(BaseModel):
    """Schema for LLM-generated long-term memories"""

    content: str = Field(..., description="Memory content")
    task_id: Optional[str] = Field(
        None, description="Task ID if this memory relates to a specific task"
    )


class Memory(BaseModel):
    """Generic memory object for search results"""

    id: str = Field(..., description="Memory ID")
    type: str = Field(..., description="Memory type (turn, compact, semantic)")
    title: str = Field(..., description="Memory title")
    summary: str = Field(..., description="Memory summary")
    content: Union[str, dict[str, Any]] = Field(..., description="Memory content")
    relevance_score: Optional[float] = Field(None, description="Search relevance score")


class SearchResults(BaseModel):
    """Results from memory search"""

    memories: list[Memory] = Field(default_factory=list, description="Found memories")
    total_count: int = Field(0, description="Total memories found")
    search_time_ms: Optional[float] = Field(None, description="Search duration")


class RelevantMemoryIdsSchema(BaseModel):
    """Schema for LLM to return relevant memory IDs"""

    memory_ids: list[str] = Field(default_factory=list, description="IDs of relevant memories")
    reasoning: str = Field(..., description="Explanation of why these memories are relevant")


# Tool Analysis Models
class ToolUsageStats(BaseModel):
    """Statistics for tool usage"""

    count: int = Field(0, description="Number of times used")
    success_count: int = Field(0, description="Number of successful uses")
    error_count: int = Field(0, description="Number of failed uses")
    common_args: dict[str, list[Any]] = Field(default_factory=dict, description="Common arguments")
    common_errors: list[str] = Field(default_factory=list, description="Common error messages")


class ToolAnalysis(BaseModel):
    """Analysis of tool usage in conversations"""

    tool_stats: dict[str, ToolUsageStats] = Field(
        default_factory=dict, description="Statistics by tool"
    )
    tool_sequences: list[str] = Field(default_factory=list, description="Common tool sequences")
    tool_errors: list[dict[str, str]] = Field(
        default_factory=list, description="Recent tool errors"
    )


# Context Building Models
class ContextMemory(BaseModel):
    """Memory formatted for context"""

    type: str = Field(..., description="Memory type")
    content: str = Field(..., description="Formatted content for context")
    token_count: int = Field(..., description="Estimated token count")


class Context(BaseModel):
    """Built context for LLM"""

    memories: list[ContextMemory] = Field(default_factory=list, description="Context memories")
    total_tokens: int = Field(0, description="Total estimated tokens")
    truncated: bool = Field(False, description="Whether context was truncated")


# Global config instance
memory_config = MemoryConfig.from_env()
