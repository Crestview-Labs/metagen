"""Detect and provide feedback for repetitive tool calls."""

import hashlib
import json
import logging
from typing import Any, Optional

from common.types import ToolCallResult, ToolErrorType

logger = logging.getLogger(__name__)


class RepetitionDetector:
    """Detect repetitive tool calls and provide corrective feedback.

    Detects two types of repetition:
    1. Exact repetition: Same tool with identical arguments
    2. Pattern repetition: Circular patterns like A->B->A->B
    """

    def __init__(self, config: dict, debug: bool = False):
        """Initialize the repetition detector.

        Args:
            config: Repetition configuration dict containing:
                - exact_threshold: Number of identical calls before intervention
                - pattern_detection: Whether to detect circular patterns
            debug: Enable debug logging
        """
        self.exact_threshold = config.get("exact_threshold", 3)
        self.pattern_detection = config.get("pattern_detection", True)
        self.debug = debug

        # Track tool calls: "tool:args_hash" -> count
        self.call_counts: dict[str, int] = {}

        # Track call history for pattern detection
        self.call_history: list[tuple[str, str]] = []  # (tool_name, args_hash)

        # Track per-tool call counts for limits
        self.tool_call_counts: dict[str, int] = {}

        if self.debug:
            logger.info(
                f"RepetitionDetector initialized: threshold={self.exact_threshold}, "
                f"pattern_detection={self.pattern_detection}"
            )

    def check_repetition(
        self,
        agent_id: str,
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
        tool_limits: Optional[dict[str, int]] = None,
    ) -> Optional[ToolCallResult]:
        """Check for repetition and return feedback if needed.

        Args:
            agent_id: Agent ID for the current conversation
            session_id: Session ID for the current conversation
            tool_name: Name of the tool being called
            args: Arguments for the tool call
            tool_limits: Optional per-tool call limits

        Returns:
            ToolCallResult with feedback if repetition detected, None otherwise
        """
        # Create signature for this call
        args_hash = self._hash_args(args)
        signature = f"{tool_name}:{args_hash}"

        # Log the tool call at debug level
        logger.debug(
            f"Safety check - Agent: {agent_id}, Session: {session_id}, "
            f"Tool: {tool_name}, Args hash: {args_hash[:8]}..."
        )

        # Update counts
        self.call_counts[signature] = self.call_counts.get(signature, 0) + 1
        self.tool_call_counts[tool_name] = self.tool_call_counts.get(tool_name, 0) + 1

        count = self.call_counts[signature]

        # Check per-tool limits first
        if tool_limits and tool_name in tool_limits:
            limit = tool_limits[tool_name]
            tool_count = self.tool_call_counts[tool_name]
            if tool_count > limit:
                logger.warning(
                    f"SAFETY INTERVENTION - Tool limit exceeded - "
                    f"Agent: {agent_id}, Session: {session_id}, "
                    f"Tool: {tool_name}, Count: {tool_count}/{limit}"
                )
                return self._create_limit_feedback(
                    agent_id, session_id, tool_name, tool_count, limit
                )

        # Check exact repetition threshold
        if count >= self.exact_threshold:
            logger.warning(
                f"SAFETY INTERVENTION - Exact repetition detected - "
                f"Agent: {agent_id}, Session: {session_id}, "
                f"Tool: {tool_name}, Identical calls: {count}/{self.exact_threshold}"
            )
            return self._create_repetition_feedback(agent_id, session_id, tool_name, count)

        # Track this call for pattern detection
        self.call_history.append((tool_name, args_hash))
        if len(self.call_history) > 10:
            self.call_history.pop(0)

        # Check for circular patterns
        if self.pattern_detection and self._has_circular_pattern():
            pattern = self._get_pattern_description()
            logger.warning(
                f"SAFETY INTERVENTION - Circular pattern detected - "
                f"Agent: {agent_id}, Session: {session_id}, "
                f"Pattern: {pattern}"
            )
            return self._create_pattern_feedback(agent_id, session_id)

        return None

    def _hash_args(self, args: dict[str, Any]) -> str:
        """Create a hash of arguments for comparison.

        Args:
            args: Tool arguments

        Returns:
            Short hash string for the arguments
        """
        # Sort keys for consistent hashing
        normalized = json.dumps(args, sort_keys=True)
        return hashlib.md5(normalized.encode()).hexdigest()[:8]

    def _create_repetition_feedback(
        self, agent_id: str, session_id: str, tool_name: str, count: int
    ) -> ToolCallResult:
        """Create feedback for exact repetition.

        Args:
            agent_id: Agent ID for the current conversation
            session_id: Session ID for the current conversation
            tool_name: Name of the repeated tool
            count: Number of repetitions

        Returns:
            ToolCallResult with appropriate feedback
        """
        message = (
            f"You've called {tool_name} {count} times with identical arguments. "
            "This repetition isn't productive. Please try a different approach, "
            "use different parameters, or continue with the information you've already gathered."
        )

        # Treat as rejected tool call with feedback
        return ToolCallResult(
            tool_name=tool_name,
            tool_call_id=None,
            agent_id=agent_id,
            session_id=session_id,
            content=message,
            is_error=True,
            error=message,
            error_type=ToolErrorType.INVALID_ARGS,
            user_display=None,
            metadata={"feedback": message},
        )

    def _create_limit_feedback(
        self, agent_id: str, session_id: str, tool_name: str, count: int, limit: int
    ) -> ToolCallResult:
        """Create feedback when tool limit is exceeded.

        Args:
            agent_id: Agent ID for the current conversation
            session_id: Session ID for the current conversation
            tool_name: Name of the tool
            count: Current call count
            limit: Maximum allowed calls

        Returns:
            ToolCallResult with limit feedback
        """
        message = (
            f"Tool limit exceeded: {tool_name} has been called {count} times "
            f"(limit: {limit} per turn). Please complete your task with the "
            f"information you've gathered or try a different approach."
        )

        return ToolCallResult(
            tool_name=tool_name,
            tool_call_id=None,
            agent_id=agent_id,
            session_id=session_id,
            content=message,
            is_error=True,
            error=message,
            error_type=ToolErrorType.INVALID_ARGS,
            user_display=None,
            metadata={"feedback": message},
        )

    def _get_pattern_description(self) -> str:
        """Get a description of the detected pattern."""
        if len(self.call_history) < 4:
            return "No pattern"

        # Check for simple A->B->A->B pattern
        if (
            len(self.call_history) >= 4
            and self.call_history[-4][0] == self.call_history[-2][0]
            and self.call_history[-3][0] == self.call_history[-1][0]
        ):
            return f"{self.call_history[-4][0]} → {self.call_history[-3][0]} (repeating)"

        return "Complex pattern"

    def _has_circular_pattern(self) -> bool:
        """Detect circular patterns like A->B->A->B.

        Returns:
            True if a circular pattern is detected
        """
        if len(self.call_history) < 4:
            return False

        # Check for 2-step patterns (A->B->A->B)
        recent = self.call_history[-4:]
        if recent[0] == recent[2] and recent[1] == recent[3]:
            return True

        # Check for 3-step patterns (A->B->C->A->B->C)
        if len(self.call_history) >= 6:
            recent = self.call_history[-6:]
            if recent[0] == recent[3] and recent[1] == recent[4] and recent[2] == recent[5]:
                return True

        return False

    def _create_pattern_feedback(self, agent_id: str, session_id: str) -> ToolCallResult:
        """Create feedback for circular pattern repetition.

        Args:
            agent_id: Agent ID for the current conversation
            session_id: Session ID for the current conversation

        Returns:
            ToolCallResult with pattern feedback
        """
        # Get the pattern for display
        pattern_length = 2 if len(self.call_history) >= 4 else 0
        if self._has_circular_pattern() and len(self.call_history) >= 6:
            # Check if it's a 3-step pattern
            recent = self.call_history[-6:]
            if recent[0] == recent[3] and recent[1] == recent[4] and recent[2] == recent[5]:
                pattern_length = 3

        if pattern_length > 0:
            pattern_tools = [call[0] for call in self.call_history[-pattern_length:]]
            pattern = " → ".join(pattern_tools)
        else:
            pattern = "circular pattern"

        message = (
            f"You're repeating a pattern: {pattern}\n"
            "This circular behavior isn't making progress. Please:\n"
            "1. Identify what specific information you're trying to find\n"
            "2. Try a completely different approach to get that information\n"
            "3. Or proceed with the information you've already gathered"
        )

        return ToolCallResult(
            tool_name="system",
            tool_call_id=None,
            agent_id=agent_id,
            session_id=session_id,
            content=message,
            is_error=True,
            error=message,
            error_type=ToolErrorType.INVALID_ARGS,
            user_display=None,
            metadata={"feedback": message},
        )

    def reset(self) -> None:
        """Reset the detector state for a new turn."""
        self.call_counts.clear()
        self.call_history.clear()
        self.tool_call_counts.clear()
        if self.debug:
            logger.debug("RepetitionDetector state reset")
