"""Tests for agentic loop safety components."""

from agents.safety.iteration_handler import IterationLimitHandler
from agents.safety.repetition_detector import RepetitionDetector
from common.types import ToolErrorType


class TestIterationLimitHandler:
    """Test iteration limit handler."""

    def test_no_warning_below_threshold(self) -> None:
        """Should not warn when below threshold."""
        handler = IterationLimitHandler(max_iterations=10)

        # Check iterations 1-7 (below 80% threshold)
        for i in range(1, 8):
            result = handler.check_iteration_limit("test-agent", "test-session", i)
            assert result is None

    def test_warning_at_80_percent(self) -> None:
        """Should warn at 80% of limit."""
        handler = IterationLimitHandler(max_iterations=10)

        # Check iteration 8 (80% of 10)
        result = handler.check_iteration_limit("test-agent", "test-session", 8)
        assert result is not None
        assert result.tool_name == "system"
        assert "approaching the iteration limit" in result.content
        assert result.is_error is False

    def test_final_warning_at_90_percent(self) -> None:
        """Should give final warning at 90% of limit."""
        handler = IterationLimitHandler(max_iterations=10)

        # Check iteration 9 (90% of 10)
        result = handler.check_iteration_limit("test-agent", "test-session", 9)
        assert result is not None
        assert "very close to the iteration limit" in result.content
        assert result.is_error is False

    def test_hard_limit_reached(self) -> None:
        """Should error when limit is reached."""
        handler = IterationLimitHandler(max_iterations=10)

        # Check iteration 10 (limit reached)
        result = handler.check_iteration_limit("test-agent", "test-session", 10)
        assert result is not None
        assert "ITERATION LIMIT REACHED" in result.content
        assert result.is_error is True
        assert result.error_type == ToolErrorType.INVALID_ARGS

    def test_is_at_limit(self) -> None:
        """Test is_at_limit method."""
        handler = IterationLimitHandler(max_iterations=10)

        assert handler.is_at_limit(9) is False
        assert handler.is_at_limit(10) is True
        assert handler.is_at_limit(11) is True


class TestRepetitionDetector:
    """Test repetition detector."""

    def test_no_repetition_below_threshold(self) -> None:
        """Should not detect repetition below threshold."""
        detector = RepetitionDetector({"exact_threshold": 3})

        # First two calls should be fine
        result1 = detector.check_repetition(
            "test-agent", "test-session", "search", {"query": "test"}
        )
        assert result1 is None

        result2 = detector.check_repetition(
            "test-agent", "test-session", "search", {"query": "test"}
        )
        assert result2 is None

    def test_exact_repetition_detection(self) -> None:
        """Should detect exact repetition at threshold."""
        detector = RepetitionDetector({"exact_threshold": 3})

        # Call same tool 3 times
        detector.check_repetition("test-agent", "test-session", "search", {"query": "test"})
        detector.check_repetition("test-agent", "test-session", "search", {"query": "test"})
        result = detector.check_repetition(
            "test-agent", "test-session", "search", {"query": "test"}
        )

        assert result is not None
        assert result.tool_name == "search"
        assert "3 times with identical arguments" in result.content
        assert result.is_error is True
        assert result.metadata == {"feedback": result.content}

    def test_different_args_not_counted(self) -> None:
        """Different arguments should not count as repetition."""
        detector = RepetitionDetector({"exact_threshold": 3})

        # Call with different args
        result1 = detector.check_repetition(
            "test-agent", "test-session", "search", {"query": "test1"}
        )
        result2 = detector.check_repetition(
            "test-agent", "test-session", "search", {"query": "test2"}
        )
        result3 = detector.check_repetition(
            "test-agent", "test-session", "search", {"query": "test3"}
        )

        assert result1 is None
        assert result2 is None
        assert result3 is None

    def test_pattern_detection(self) -> None:
        """Should detect circular patterns."""
        detector = RepetitionDetector(
            {
                "exact_threshold": 10,  # High so we don't trigger exact
                "pattern_detection": True,
            }
        )

        # Create A->B->A->B pattern
        detector.check_repetition("test-agent", "test-session", "toolA", {"arg": "a"})
        detector.check_repetition("test-agent", "test-session", "toolB", {"arg": "b"})
        detector.check_repetition("test-agent", "test-session", "toolA", {"arg": "a"})
        result = detector.check_repetition("test-agent", "test-session", "toolB", {"arg": "b"})

        assert result is not None
        assert "repeating a pattern" in result.content
        assert "toolA → toolB" in result.content

    def test_tool_limits(self) -> None:
        """Should enforce per-tool limits."""
        detector = RepetitionDetector({"exact_threshold": 10})
        tool_limits = {"execute_command": 2}

        # First two calls ok
        result1 = detector.check_repetition(
            "test-agent", "test-session", "execute_command", {"cmd": "ls"}, tool_limits
        )
        result2 = detector.check_repetition(
            "test-agent", "test-session", "execute_command", {"cmd": "pwd"}, tool_limits
        )
        assert result1 is None
        assert result2 is None

        # Third call exceeds limit
        result3 = detector.check_repetition(
            "test-agent", "test-session", "execute_command", {"cmd": "date"}, tool_limits
        )
        assert result3 is not None
        assert "Tool limit exceeded" in result3.content
        assert "limit: 2" in result3.content

    def test_reset(self) -> None:
        """Reset should clear all state."""
        detector = RepetitionDetector({"exact_threshold": 2})

        # Add some calls
        detector.check_repetition("test-agent", "test-session", "search", {"query": "test"})
        detector.check_repetition("test-agent", "test-session", "search", {"query": "test"})

        # Reset
        detector.reset()

        # Should be able to call again
        result = detector.check_repetition(
            "test-agent", "test-session", "search", {"query": "test"}
        )
        assert result is None
