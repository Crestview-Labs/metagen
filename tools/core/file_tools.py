"""File operation tools."""

import re
from pathlib import Path
from typing import Any

from tools.base import BaseCoreTool
from tools.schemas import (
    FileReadInput,
    FileReadOutput,
    FileSearchInput,
    FileSearchOutput,
    FileWriteInput,
    FileWriteOutput,
)


class ReadFileTool(BaseCoreTool):
    """Tool for reading files from the filesystem."""

    def __init__(self, root_directory: str = "."):
        # TODO: Make root_directory configurable via environment variable or registry config
        super().__init__(
            name="read_file",
            description="Read content from a file",
            input_schema=FileReadInput,
            output_schema=FileReadOutput,
        )
        self.root_directory = Path(root_directory).resolve()

    async def _execute_impl(self, input_data: FileReadInput) -> FileReadOutput:  # type: ignore[override]
        """Read file content."""
        file_path = Path(input_data.path)

        # Security: ensure path is within root directory
        if not file_path.is_absolute():
            file_path = self.root_directory / file_path

        resolved_path = file_path.resolve()
        if not str(resolved_path).startswith(str(self.root_directory)):
            raise ValueError(f"Path {input_data.path} is outside root directory")

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {input_data.path}")

        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {input_data.path}")

        # Read file
        with open(resolved_path, "r", encoding=input_data.encoding) as f:
            if input_data.offset is not None or input_data.limit is not None:
                # Read specific lines
                lines = f.readlines()
                total_lines = len(lines)

                start = input_data.offset or 0
                end = start + (input_data.limit or len(lines))

                selected_lines = lines[start:end]
                content = "".join(selected_lines)
                lines_read = len(selected_lines)
            else:
                # Read entire file
                content = f.read()
                lines_read = content.count("\n") + (
                    1 if content and not content.endswith("\n") else 0
                )
                total_lines = lines_read

        return FileReadOutput(
            content=content,
            lines_read=lines_read,
            total_lines=total_lines,
            encoding=input_data.encoding,
        )


class WriteFileTool(BaseCoreTool):
    """Tool for writing files to the filesystem."""

    def __init__(self, root_directory: str = "."):
        super().__init__(
            name="write_file",
            description="Write content to a file",
            input_schema=FileWriteInput,
            output_schema=FileWriteOutput,
        )
        self.root_directory = Path(root_directory).resolve()

    async def _execute_impl(self, input_data: FileWriteInput) -> FileWriteOutput:  # type: ignore[override]
        """Write file content."""
        file_path = Path(input_data.path)

        # Security: ensure path is within root directory
        if not file_path.is_absolute():
            file_path = self.root_directory / file_path

        resolved_path = file_path.resolve()
        if not str(resolved_path).startswith(str(self.root_directory)):
            raise ValueError(f"Path {input_data.path} is outside root directory")

        # Create directories if needed
        if input_data.create_directories:
            resolved_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        content_bytes = input_data.content.encode(input_data.encoding)
        resolved_path.write_bytes(content_bytes)

        return FileWriteOutput(
            success=True, bytes_written=len(content_bytes), path=str(resolved_path)
        )


class SearchFilesTool(BaseCoreTool):
    """Tool for searching files by content pattern."""

    def __init__(self, root_directory: str = "."):
        super().__init__(
            name="search_files",
            description="Search for patterns in files",
            input_schema=FileSearchInput,
            output_schema=FileSearchOutput,
        )
        self.root_directory = Path(root_directory).resolve()

    async def _execute_impl(self, input_data: FileSearchInput) -> FileSearchOutput:  # type: ignore[override]
        """Search files for pattern."""
        search_dir = Path(input_data.directory)
        if not search_dir.is_absolute():
            search_dir = self.root_directory / search_dir

        # Security check
        resolved_dir = search_dir.resolve()
        if not str(resolved_dir).startswith(str(self.root_directory)):
            raise ValueError(f"Search directory {input_data.directory} is outside root directory")

        if not resolved_dir.exists():
            raise FileNotFoundError(f"Directory not found: {input_data.directory}")

        # Compile regex pattern
        try:
            pattern = re.compile(input_data.pattern, re.MULTILINE | re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")

        # Find files to search
        if input_data.file_pattern:
            if input_data.recursive:
                file_pattern = f"**/{input_data.file_pattern}"
            else:
                file_pattern = input_data.file_pattern

            files = list(resolved_dir.glob(file_pattern))
        else:
            if input_data.recursive:
                files = [f for f in resolved_dir.rglob("*") if f.is_file()]
            else:
                files = [f for f in resolved_dir.iterdir() if f.is_file()]

        # Search files
        matches: list[dict[str, Any]] = []
        files_searched = 0

        for file_path in files:
            if len(matches) >= input_data.max_results:
                break

            try:
                # Skip binary files
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    files_searched += 1

                    # Find all matches in file
                    for match in pattern.finditer(content):
                        if len(matches) >= input_data.max_results:
                            break

                        # Get line number and context
                        lines = content[: match.start()].split("\n")
                        line_num = len(lines)

                        # Get the full line containing the match
                        line_start = content.rfind("\n", 0, match.start()) + 1
                        line_end = content.find("\n", match.end())
                        if line_end == -1:
                            line_end = len(content)

                        matches.append(
                            {
                                "file": str(file_path.relative_to(self.root_directory)),
                                "line": line_num,
                                "match": match.group(),
                                "context": content[line_start:line_end].strip(),
                            }
                        )

            except (UnicodeDecodeError, PermissionError):
                # Skip files we can't read
                continue

        return FileSearchOutput(
            matches=matches, total_matches=len(matches), files_searched=files_searched
        )

    def _format_display(self, output: FileSearchOutput) -> str:  # type: ignore[override]
        """Custom formatting for search results."""
        if not output.matches:
            return "No matches found."

        lines = [f"Found {output.total_matches} matches in {output.files_searched} files:"]
        for match in output.matches[:10]:  # Show first 10
            lines.append(f"\n{match['file']}:{match['line']}")
            lines.append(f"  {match['context']}")

        if output.total_matches > 10:
            lines.append(f"\n... and {output.total_matches - 10} more matches")

        return "\n".join(lines)
