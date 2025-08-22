"""Handle iteration limits with graceful completion."""

import logging
from typing import Optional

from common.types import ToolCallResult, ToolErrorType

logger = logging.getLogger(__name__)


class IterationLimitHandler:
    """Manage iteration limits with graceful completion.

    Provides warnings as approaching the limit and guides the LLM
    to provide a summary when the limit is reached.
    """

    def __init__(self, max_iterations: int, debug: bool = False):
        """Initialize the iteration limit handler.

        Args:
            max_iterations: Maximum number of tool iterations allowed
            debug: Enable debug logging
        """
        self.max_iterations = max_iterations
        self.debug = debug

        # Calculate warning thresholds
        self.warning_threshold = int(max_iterations * 0.8)
        self.final_warning_threshold = int(max_iterations * 0.9)

        if self.debug:
            logger.info(
                f"IterationLimitHandler initialized: max={max_iterations}, "
                f"warning at {self.warning_threshold}, final at {self.final_warning_threshold}"
            )

    def check_iteration_limit(
        self, agent_id: str, session_id: str, current_iteration: int
    ) -> Optional[ToolCallResult]:
        """Check if we're approaching or at the iteration limit.

        Args:
            agent_id: Agent ID for the current conversation
            session_id: Session ID for the current conversation
            current_iteration: Current iteration number (1-based)

        Returns:
            ToolCallResult with feedback if approaching/at limit, None otherwise
        """
        # Log current iteration status at debug level
        logger.debug(
            f"Safety check - Agent: {agent_id}, Session: {session_id}, "
            f"Iteration: {current_iteration}/{self.max_iterations}"
        )

        # First warning at 80%
        if current_iteration == self.warning_threshold:
            message = (
                "You're approaching the iteration limit. "
                "Please start working toward completing your response."
            )
            logger.info(
                f"SAFETY INTERVENTION - Iteration warning (80%) - "
                f"Agent: {agent_id}, Session: {session_id}, "
                f"Iteration: {current_iteration}/{self.max_iterations}"
            )
            return self._create_feedback_result(agent_id, session_id, message, is_final=False)

        # Final warning at 90%
        if current_iteration == self.final_warning_threshold:
            message = (
                "Important: You're very close to the iteration limit. "
                "Please summarize your findings and prepare to conclude."
            )
            logger.info(
                f"SAFETY INTERVENTION - Final iteration warning (90%) - "
                f"Agent: {agent_id}, Session: {session_id}, "
                f"Iteration: {current_iteration}/{self.max_iterations}"
            )
            return self._create_feedback_result(agent_id, session_id, message, is_final=False)

        # At limit - request summary
        if current_iteration >= self.max_iterations:
            message = self._create_limit_message()
            logger.warning(
                f"SAFETY INTERVENTION - Iteration limit reached - "
                f"Agent: {agent_id}, Session: {session_id}, "
                f"Iteration: {current_iteration}/{self.max_iterations} - "
                f"Requesting summary from LLM"
            )
            return self._create_feedback_result(agent_id, session_id, message, is_final=True)

        return None

    def _create_feedback_result(
        self, agent_id: str, session_id: str, message: str, is_final: bool = False
    ) -> ToolCallResult:
        """Create a ToolCallResult with iteration limit feedback.

        Args:
            agent_id: Agent ID for the current conversation
            session_id: Session ID for the current conversation
            message: The feedback message
            is_final: Whether this is the final limit (no more iterations allowed)

        Returns:
            ToolCallResult with appropriate feedback
        """
        # Similar to RepetitionDetector, treat as rejected tool with feedback
        return ToolCallResult(
            tool_name="system",
            tool_call_id=None,
            agent_id=agent_id,
            session_id=session_id,
            content=message,
            is_error=is_final,  # Only error if we've hit the hard limit
            error=message if is_final else None,
            error_type=ToolErrorType.INVALID_ARGS if is_final else None,
            user_display=None,
            metadata={"feedback": message},
        )

    def _create_limit_message(self) -> str:
        """Create the message when iteration limit is reached."""
        return (
            "ITERATION LIMIT REACHED: You've reached the maximum number of tool iterations. "
            "Please provide a final response with the following:\n\n"
            "1. A summary of what you've accomplished\n"
            "2. The current status of the task\n"
            "3. Any remaining steps the user can take to continue\n\n"
            "No more tools will be executed in this turn."
        )

    def is_at_limit(self, current_iteration: int) -> bool:
        """Check if the iteration limit has been reached.

        Args:
            current_iteration: Current iteration number

        Returns:
            True if at or beyond the limit
        """
        return current_iteration >= self.max_iterations

    def remaining_iterations(self, current_iteration: int) -> int:
        """Get the number of remaining iterations.

        Args:
            current_iteration: Current iteration number

        Returns:
            Number of iterations remaining
        """
        return max(0, self.max_iterations - current_iteration)
