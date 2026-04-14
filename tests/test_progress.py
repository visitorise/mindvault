"""Unit tests for mindvault.progress module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from mindvault.progress import Progress


class TestProgressEnabledBehavior:
    """Verify enabled parameter behavior."""

    def test_enabled_when_true(self):
        """Progress should be enabled when enabled=True."""
        p = Progress(total_steps=3, enabled=True)
        assert p._enabled

    def test_disabled_when_false(self):
        """Progress should be disabled when enabled=False."""
        p = Progress(total_steps=3, enabled=False)
        assert not p._enabled


class TestProgressStepCounter:
    """Verify step counter behavior."""

    def test_step_increments_counter(self):
        """step() should increment the counter."""
        p = Progress(total_steps=5)
        assert p.current_step == 0
        p.step("First step")
        assert p.current_step == 1
        p.step("Second step")
        assert p.current_step == 2

    def test_step_formats_correctly(self, capsys):
        """step() should print formatted message."""
        p = Progress(total_steps=5, enabled=True)
        p.step("Detecting files")
        captured = capsys.readouterr()
        assert "[Step 1/5] Detecting files..." in captured.err

    def test_step_respects_total_steps(self, capsys):
        """step() should respect total_steps in format."""
        p = Progress(total_steps=10, enabled=True)
        p.step("Test")
        captured = capsys.readouterr()
        assert "[Step 1/10]" in captured.err

    def test_sequential_steps(self, capsys):
        """step() should increment counter and print sequential step numbers."""
        p = Progress(total_steps=5, enabled=True)
        p.step("Step 1")
        p.done()
        p.step("Step 2")
        p.done()
        p.step("Step 3")
        p.done()
        p.step("Step 4")
        p.done()
        p.step("Step 5")
        p.done()
        captured = capsys.readouterr()
        assert "[Step 1/5] Step 1..." in captured.err
        assert "[Step 2/5] Step 2..." in captured.err
        assert "[Step 3/5] Step 3..." in captured.err
        assert "[Step 4/5] Step 4..." in captured.err
        assert "[Step 5/5] Step 5..." in captured.err
        assert "[OK]" in captured.err


class TestProgressOutput:
    """Verify output methods."""

    def test_done_prints_to_stderr(self, capsys):
        """done() should print to stderr."""
        p = Progress(total_steps=3, enabled=True)
        p.done("Processing complete")
        captured = capsys.readouterr()
        assert "[OK] Processing complete" in captured.err

    def test_done_empty_message(self, capsys):
        """done() with no message should print just [OK]."""
        p = Progress(total_steps=3, enabled=True)
        p.done()
        captured = capsys.readouterr()
        assert captured.err.strip() == "[OK]"

    def test_info_prints_to_stderr(self, capsys):
        """info() should print to stderr."""
        p = Progress(total_steps=3, enabled=True)
        p.info("Some info message")
        captured = capsys.readouterr()
        assert "[INFO] Some info message" in captured.err

    def test_warn_prints_to_stderr(self, capsys):
        """warn() should print to stderr."""
        p = Progress(total_steps=3, enabled=True)
        p.warn("Warning message")
        captured = capsys.readouterr()
        assert "[WARN] Warning message" in captured.err


class TestProgressDisabledOutput:
    """Verify output is suppressed when disabled."""

    def test_step_no_output_when_disabled(self, capsys):
        """step() should not print when disabled."""
        p = Progress(total_steps=3, enabled=False)
        p.step("Test step")
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_done_no_output_when_disabled(self, capsys):
        """done() should not print when disabled."""
        p = Progress(total_steps=3, enabled=False)
        p.done("Message")
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_info_no_output_when_disabled(self, capsys):
        """info() should not print when disabled."""
        p = Progress(total_steps=3, enabled=False)
        p.info("Message")
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_warn_no_output_when_disabled(self, capsys):
        """warn() should not print when disabled."""
        p = Progress(total_steps=3, enabled=False)
        p.warn("Message")
        captured = capsys.readouterr()
        assert captured.err == ""
