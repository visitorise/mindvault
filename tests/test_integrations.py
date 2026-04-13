"""Unit tests for mindvault.integrations AI tool auto-integration.

Locks 0.2.5 → 0.2.8 behavior: the AI_TOOLS list covers 10 tools,
AGENTS.md detection works for Codex CLI + Antigravity, GEMINI.md and
QWEN.md create new vendor-specific rules files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mindvault.integrations import (
    AI_TOOLS,
    detect_ai_tools,
    install_integration,
    install_all_integrations,
)


class TestAiToolsRegistry:
    def test_count_is_ten(self):
        """Any change here should be a deliberate release note."""
        assert len(AI_TOOLS) == 10

    def test_all_tools_have_required_keys(self):
        required = {"name", "detect_files", "rules_file", "type"}
        for tool in AI_TOOLS:
            missing = required - set(tool.keys())
            assert not missing, f"{tool.get('name', '?')} missing keys: {missing}"

    def test_names_are_unique(self):
        names = [t["name"] for t in AI_TOOLS]
        assert len(names) == len(set(names))

    def test_agents_md_standard_is_present(self):
        agents = [t for t in AI_TOOLS if "AGENTS.md" in t["name"]]
        assert len(agents) == 1, "Exactly one AGENTS.md entry expected"
        # Must cover Codex CLI and Antigravity in the label
        assert "Codex" in agents[0]["name"]
        assert "Antigravity" in agents[0]["name"]

    def test_gemini_cli_is_separate_from_code_assist(self):
        names = {t["name"] for t in AI_TOOLS}
        assert "Google Gemini CLI" in names
        assert "Gemini Code Assist" in names

    def test_qwen_code_is_present(self):
        names = {t["name"] for t in AI_TOOLS}
        assert "Qwen Code" in names


class TestDetection:
    def test_detects_agents_md(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("")
        detected = detect_ai_tools(tmp_path)
        names = {t["name"] for t in detected}
        assert "AGENTS.md (Codex CLI, Antigravity)" in names

    def test_detects_gemini_cli_via_gemini_md(self, tmp_path: Path):
        (tmp_path / "GEMINI.md").write_text("")
        detected = detect_ai_tools(tmp_path)
        names = {t["name"] for t in detected}
        assert "Google Gemini CLI" in names

    def test_detects_qwen_code(self, tmp_path: Path):
        (tmp_path / "QWEN.md").write_text("")
        detected = detect_ai_tools(tmp_path)
        names = {t["name"] for t in detected}
        assert "Qwen Code" in names

    def test_detects_claude_code(self, tmp_path: Path):
        (tmp_path / "CLAUDE.md").write_text("# Existing\n")
        detected = detect_ai_tools(tmp_path)
        names = {t["name"] for t in detected}
        assert "Claude Code" in names

    def test_detects_claude_code_via_env_var(self, tmp_path: Path, monkeypatch):
        """Claude Code detected via CLAUDECODE=1 even without CLAUDE.md."""
        monkeypatch.setenv("CLAUDECODE", "1")
        detected = detect_ai_tools(tmp_path)
        names = {t["name"] for t in detected}
        assert "Claude Code" in names
        # detected_file should be None for env-var detection
        claude = next(t for t in detected if t["name"] == "Claude Code")
        assert claude["detected_file"] is None

    def test_detects_claude_code_via_global_config(self, tmp_path: Path, monkeypatch):
        """Claude Code detected via ~/.claude/ directory."""
        monkeypatch.delenv("CLAUDECODE", raising=False)
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        (fake_home / ".claude").mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        detected = detect_ai_tools(tmp_path / "project")
        names = {t["name"] for t in detected}
        assert "Claude Code" in names

    def test_empty_directory_detects_nothing(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("CLAUDECODE", raising=False)
        # Point home to a dir without .claude/
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        project = tmp_path / "empty_project"
        project.mkdir()
        detected = detect_ai_tools(project)
        assert detected == []


class TestInstall:
    def test_install_creates_agents_md_block(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("")
        tool = next(t for t in AI_TOOLS if "AGENTS.md" in t["name"])
        assert install_integration(tmp_path, tool) is True
        content = (tmp_path / "AGENTS.md").read_text()
        assert "MindVault" in content
        assert "mindvault query" in content

    def test_install_is_idempotent(self, tmp_path: Path):
        (tmp_path / "GEMINI.md").write_text("")
        tool = next(t for t in AI_TOOLS if t["name"] == "Google Gemini CLI")
        assert install_integration(tmp_path, tool) is True
        # Second run should be a no-op (returns False = already installed)
        assert install_integration(tmp_path, tool) is False

    def test_install_all_handles_multiple_tools(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("")
        (tmp_path / "GEMINI.md").write_text("")
        (tmp_path / "QWEN.md").write_text("")
        results = install_all_integrations(tmp_path)
        # All three should be detected and installed
        installed = [r for r in results if r["status"] == "installed"]
        assert len(installed) >= 3
        installed_names = {r["name"] for r in installed}
        assert "AGENTS.md (Codex CLI, Antigravity)" in installed_names
        assert "Google Gemini CLI" in installed_names
        assert "Qwen Code" in installed_names
