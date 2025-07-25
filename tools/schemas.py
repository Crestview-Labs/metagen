"""Common Pydantic schemas for tools."""

from typing import Any, Optional

from pydantic import BaseModel, Field


# Simple input/output schemas
class StringInput(BaseModel):
    """Simple string input."""

    text: str = Field(..., description="Input text")


class StringOutput(BaseModel):
    """Simple string output."""

    result: str = Field(..., description="Output text")


# File operation schemas
class FileReadInput(BaseModel):
    """Input for file reading operations."""

    path: str = Field(..., description="File path to read")
    encoding: str = Field("utf-8", description="File encoding")
    offset: Optional[int] = Field(None, description="Line offset to start reading from")
    limit: Optional[int] = Field(None, description="Maximum number of lines to read")


class FileReadOutput(BaseModel):
    """Output from file reading operations."""

    content: str = Field(..., description="File content")
    lines_read: int = Field(..., description="Number of lines read")
    total_lines: Optional[int] = Field(None, description="Total lines in file")
    encoding: str = Field(..., description="Encoding used")


class FileWriteInput(BaseModel):
    """Input for file writing operations."""

    path: str = Field(..., description="File path to write")
    content: str = Field(..., description="Content to write")
    encoding: str = Field("utf-8", description="File encoding")
    create_directories: bool = Field(
        True, description="Create parent directories if they don't exist"
    )


class FileWriteOutput(BaseModel):
    """Output from file writing operations."""

    success: bool = Field(..., description="Whether write was successful")
    bytes_written: int = Field(..., description="Number of bytes written")
    path: str = Field(..., description="Path written to")


class FileSearchInput(BaseModel):
    """Input for file search operations."""

    pattern: str = Field(..., description="Search pattern (regex or glob)")
    directory: str = Field(".", description="Directory to search in")
    recursive: bool = Field(True, description="Search recursively")
    file_pattern: Optional[str] = Field(None, description="File name pattern to match")
    max_results: int = Field(100, description="Maximum number of results")


class FileSearchOutput(BaseModel):
    """Output from file search operations."""

    matches: list[dict[str, Any]] = Field(
        ..., description="List of matches with file path and matching lines"
    )
    total_matches: int = Field(..., description="Total number of matches found")
    files_searched: int = Field(..., description="Number of files searched")


# Web operation schemas
class WebSearchInput(BaseModel):
    """Input for web search operations."""

    query: str = Field(..., description="Search query")
    max_results: int = Field(10, description="Maximum number of results")


class WebSearchOutput(BaseModel):
    """Output from web search operations."""

    results: list[dict[str, str]] = Field(
        ..., description="Search results with title, url, snippet"
    )
    total_results: int = Field(..., description="Total number of results")
    search_time_ms: float = Field(..., description="Search time in milliseconds")


class WebFetchInput(BaseModel):
    """Input for web fetch operations."""

    url: str = Field(..., description="URL to fetch")
    timeout: int = Field(30, description="Timeout in seconds")
    headers: dict[str, str] = Field(default_factory=dict, description="Additional headers")


class WebFetchOutput(BaseModel):
    """Output from web fetch operations."""

    content: str = Field(..., description="Fetched content")
    status_code: int = Field(..., description="HTTP status code")
    content_type: str = Field(..., description="Content type")
    content_length: int = Field(..., description="Content length in bytes")


# Analysis schemas (for LLM tools)
class EntityExtractionInput(BaseModel):
    """Input for entity extraction."""

    text: str = Field(..., description="Text to extract entities from")
    entity_types: list[str] = Field(
        default=["person", "organization", "location", "date", "email", "url"],
        description="Types of entities to extract",
    )


class Entity(BaseModel):
    """Extracted entity."""

    text: str = Field(..., description="Entity text")
    type: str = Field(..., description="Entity type")
    confidence: float = Field(..., description="Confidence score (0-1)")
    context: Optional[str] = Field(None, description="Surrounding context")


class EntityExtractionOutput(BaseModel):
    """Output from entity extraction."""

    entities: list[Entity] = Field(..., description="Extracted entities")
    summary: str = Field(..., description="Brief summary of entities found")


class HierarchicalSummaryInput(BaseModel):
    """Input for hierarchical summarization."""

    text: str = Field(..., description="Text to summarize")
    max_levels: int = Field(3, description="Maximum hierarchy levels")
    target_length: int = Field(500, description="Target length for top-level summary")


class SummaryNode(BaseModel):
    """Node in hierarchical summary."""

    level: int = Field(..., description="Hierarchy level (0 = top)")
    title: str = Field(..., description="Section title")
    summary: str = Field(..., description="Section summary")
    key_points: list[str] = Field(..., description="Key points")
    children: list["SummaryNode"] = Field(default_factory=list, description="Child nodes")


class HierarchicalSummaryOutput(BaseModel):
    """Output from hierarchical summarization."""

    root: SummaryNode = Field(..., description="Root of summary hierarchy")
    total_nodes: int = Field(..., description="Total number of summary nodes")


# Update forward references
SummaryNode.model_rebuild()
