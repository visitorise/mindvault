"""Progress indicator for pipeline operations."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class Progress:
    """Step-by-step progress indicator.

    All output goes to stderr to keep stdout clean for actual results.
    Automatically disabled in non-TTY environments (CI/CD).
    """

    def __init__(self, total_steps: int, enabled: bool = True):
        """Initialize progress tracker.

        Args:
            total_steps: Total number of steps in the pipeline.
            enabled: If False, suppress all output. Default True.
        """
        self.current_step = 0
        self.total_steps = total_steps
        self._enabled = enabled

    def step(self, name: str) -> None:
        """Start a new step.

        Args:
            name: Name/description of the current step.
        """
        self.current_step += 1
        if self._enabled:
            print(
                f"[Step {self.current_step}/{self.total_steps}] {name}...",
                file=sys.stderr,
                flush=True,
            )

    def done(self, message: str = "") -> None:
        """Mark current step as complete.

        Args:
            message: Optional completion message to display.
        """
        if self._enabled:
            if message:
                print(f"[OK] {message}", file=sys.stderr, flush=True)
            else:
                print("[OK]", file=sys.stderr, flush=True)

    def info(self, message: str) -> None:
        """Print info message (inline, no step increment)."""
        if self._enabled:
            print(f"[INFO] {message}", file=sys.stderr, flush=True)

    def warn(self, message: str) -> None:
        """Print warning message."""
        if self._enabled:
            print(f"[WARN] {message}", file=sys.stderr, flush=True)
