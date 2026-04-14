"""Unit tests for mindvault.rules module — 10 test scenarios from ARCHITECT-BRIEF 13.5."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mindvault.rules import (
    load_rules,
    check_rules,
    add_rule,
    remove_rule,
    list_rules,
    format_rule_output,
    _read_rules_file,
    _write_rules_file,
    _normalize_rule,
    RULES_FILENAME,
)


def _make_rules_yaml(path: Path, rules: list[dict], version: int = 1) -> None:
    """Helper: write a rules.yaml file using YAML or JSON."""
    try:
        import yaml
        data = {"version": version, "rules": rules}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    except ImportError:
        data = {"version": version, "rules": rules}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# --- Scenario 1: rules.yaml parsing + rule loading ---

class TestLoadRules:
    def test_parse_and_load(self, tmp_path):
        """Scenario 1: rules.yaml parsing + rule loading."""
        rules_path = tmp_path / RULES_FILENAME
        _make_rules_yaml(rules_path, [
            {"id": "no-redis", "trigger": "redis|Redis", "type": "warn",
             "message": "Redis blocked", "lore_ref": "redis.md"},
        ])
        rules = load_rules(tmp_path)
        assert len(rules) == 1
        assert rules[0]["id"] == "no-redis"
        assert rules[0]["type"] == "warn"
        assert rules[0]["message"] == "Redis blocked"
        assert rules[0]["lore_ref"] == "redis.md"

    def test_empty_file(self, tmp_path):
        """Scenario 8: empty rules file handling."""
        rules_path = tmp_path / RULES_FILENAME
        rules_path.write_text("", encoding="utf-8")
        rules = load_rules(tmp_path)
        assert rules == []

    def test_missing_file(self, tmp_path):
        """No rules file at all."""
        rules = load_rules(tmp_path)
        assert rules == []


# --- Scenario 2: text matching with regex ---

class TestCheckRules:
    def test_regex_matching(self, tmp_path):
        """Scenario 2: text matching with regex."""
        rules = [_normalize_rule({
            "id": "no-redis", "trigger": "redis|Redis|REDIS",
            "type": "warn", "message": "No redis please",
        })]
        matched = check_rules("Let's install Redis cache", rules)
        assert len(matched) == 1
        assert matched[0]["id"] == "no-redis"

    def test_no_match(self):
        rules = [_normalize_rule({
            "id": "no-redis", "trigger": "redis",
            "type": "warn", "message": "No redis",
        })]
        matched = check_rules("Let's use SQLite", rules)
        assert matched == []


# --- Scenario 3: warn/block distinction ---

class TestWarnBlockTypes:
    def test_warn_type(self):
        """Scenario 3: warn/block distinction."""
        rules = [_normalize_rule({
            "id": "r1", "trigger": "redis", "type": "warn", "message": "warning msg",
        })]
        matched = check_rules("redis install", rules)
        output = format_rule_output(matched)
        assert "<rules-warning>" in output
        assert "</rules-warning>" in output
        assert "<rules-block>" not in output

    def test_block_type(self):
        rules = [_normalize_rule({
            "id": "r2", "trigger": "git push", "type": "block", "message": "blocked msg",
        })]
        matched = check_rules("git push origin main", rules)
        output = format_rule_output(matched)
        assert "<rules-block>" in output
        assert "</rules-block>" in output


# --- Scenario 4: project rules override global ---

class TestProjectOverridesGlobal:
    def test_project_overrides_global(self, tmp_path):
        """Scenario 4: project rules override global by ID."""
        # Global rule
        global_dir = tmp_path / "home" / ".mindvault"
        global_dir.mkdir(parents=True)
        _make_rules_yaml(global_dir / RULES_FILENAME, [
            {"id": "shared-rule", "trigger": "foo", "type": "warn", "message": "global msg"},
        ])

        # Project rule with same ID
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _make_rules_yaml(project_dir / RULES_FILENAME, [
            {"id": "shared-rule", "trigger": "foo", "type": "block", "message": "project msg"},
        ])

        with patch("mindvault.rules.Path.home", return_value=tmp_path / "home"):
            rules = load_rules(project_dir)

        assert len(rules) == 1
        assert rules[0]["type"] == "block"
        assert rules[0]["message"] == "project msg"


# --- Scenario 5: CLI add/remove/list/check ---

class TestCLIOperations:
    def test_add_and_list(self, tmp_path):
        """Scenario 5: CLI add/remove/list/check."""
        add_rule(tmp_path, "test-rule", "pattern", "warn", "test message")
        rules = list_rules(tmp_path)
        assert len(rules) == 1
        assert rules[0]["id"] == "test-rule"

    def test_remove(self, tmp_path):
        add_rule(tmp_path, "test-rule", "pattern", "warn", "msg")
        assert remove_rule(tmp_path, "test-rule") is True
        assert list_rules(tmp_path) == []

    def test_remove_nonexistent(self, tmp_path):
        assert remove_rule(tmp_path, "nonexistent") is False

    def test_check(self, tmp_path):
        add_rule(tmp_path, "no-redis", "redis", "warn", "no redis")
        rules = load_rules(tmp_path)
        matched = check_rules("install redis", rules)
        assert len(matched) == 1

    def test_add_with_lore_ref(self, tmp_path):
        add_rule(tmp_path, "r1", "pat", "warn", "msg", lore_ref="some.md")
        rules = load_rules(tmp_path)
        assert rules[0]["lore_ref"] == "some.md"

    def test_add_invalid_regex(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid regex"):
            add_rule(tmp_path, "bad", "[invalid", "warn", "msg")

    def test_add_invalid_type(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid rule type"):
            add_rule(tmp_path, "bad", "pat", "invalid_type", "msg")


# --- Scenario 6: hook integration (Bash output rule violation) ---

class TestHookIntegration:
    def test_bash_output_detection(self, tmp_path):
        """Scenario 6: hook integration — Bash output rule violation detection."""
        add_rule(tmp_path, "no-redis", "redis", "warn", "Redis not allowed")
        rules = load_rules(tmp_path)

        # Simulate tool output containing redis
        bash_output = "Successfully installed redis==7.0.0"
        matched = check_rules(bash_output, rules)
        assert len(matched) == 1

        output = format_rule_output(matched)
        assert "<rules-warning>" in output
        assert "no-redis" in output


# --- Scenario 7: Lore -> Rules suggestion ---

class TestLoreRuleSuggestion:
    def test_lore_records_with_suggestion(self, tmp_path, capsys):
        """Scenario 7: Lore -> Rules suggestion on record."""
        from mindvault.lore import record

        record(
            output_dir=tmp_path,
            title="Redis Cache Rollback",
            context="Redis caused sync issues",
            outcome="Rolled back to SQLite",
            lore_type="rollback",
        )

        captured = capsys.readouterr()
        assert "<lore-rule-suggestion>" in captured.out
        assert "mindvault rules add" in captured.out
        # Verify trigger contains at least one keyword from the title
        out_lower = captured.out.lower()
        assert any(kw in out_lower for kw in ("redis", "cache", "rollback")), \
            f"Trigger should contain a keyword from the title, got: {captured.out}"


# --- Scenario 8: empty rules file (covered in TestLoadRules.test_empty_file) ---

# --- Scenario 9: invalid regex handling ---

class TestInvalidRegex:
    def test_invalid_regex_skipped(self, tmp_path):
        """Scenario 9: invalid regex in rules file -> skip with warning, don't crash."""
        rules_path = tmp_path / RULES_FILENAME
        # Write raw JSON with invalid regex
        data = {"version": 1, "rules": [
            {"id": "bad-regex", "trigger": "[unclosed", "type": "warn", "message": "msg"},
            {"id": "good-rule", "trigger": "redis", "type": "warn", "message": "good msg"},
        ]}
        rules_path.write_text(json.dumps(data), encoding="utf-8")

        # load_rules should skip bad regex and keep good one
        rules = load_rules(tmp_path)
        assert len(rules) == 1
        assert rules[0]["id"] == "good-rule"

    def test_invalid_regex_in_check(self):
        """Even if a bad regex sneaks through, check_rules won't crash."""
        rules = [{"id": "bad", "trigger": "[bad", "type": "warn",
                  "message": "m", "enabled": True, "scope": "both"}]
        matched = check_rules("some text", rules)
        assert matched == []


# --- Scenario 10: enabled: false rules are ignored ---

class TestDisabledRules:
    def test_disabled_rule_ignored(self, tmp_path):
        """Scenario 10: enabled: false rules are ignored."""
        rules_path = tmp_path / RULES_FILENAME
        data = {"version": 1, "rules": [
            {"id": "disabled-rule", "trigger": "redis", "type": "warn",
             "message": "msg", "enabled": False},
            {"id": "enabled-rule", "trigger": "redis", "type": "block",
             "message": "active msg", "enabled": True},
        ]}
        rules_path.write_text(json.dumps(data), encoding="utf-8")

        rules = load_rules(tmp_path)
        # Both loaded (normalization preserves enabled field)
        assert len(rules) == 2

        # But check_rules skips disabled
        matched = check_rules("redis install", rules)
        assert len(matched) == 1
        assert matched[0]["id"] == "enabled-rule"


# --- Additional edge cases ---

class TestScopeFiltering:
    def test_command_scope_matches_command_and_both_context(self):
        """Command-scoped rules match context="command" and context="both" (both = check everything)."""
        rules = [_normalize_rule({
            "id": "r1", "trigger": "redis", "type": "warn",
            "message": "m", "scope": "command",
        })]
        assert len(check_rules("redis", rules, context="command")) == 1
        assert len(check_rules("redis", rules, context="output")) == 0
        assert len(check_rules("redis", rules, context="both")) == 1

    def test_both_scope_matches_all(self):
        rules = [_normalize_rule({
            "id": "r1", "trigger": "redis", "type": "warn",
            "message": "m", "scope": "both",
        })]
        assert len(check_rules("redis", rules, context="command")) == 1
        assert len(check_rules("redis", rules, context="output")) == 1
        assert len(check_rules("redis", rules, context="both")) == 1


class TestFormatOutput:
    def test_lore_ref_in_output(self):
        matched = [{"id": "r1", "type": "warn", "message": "msg", "lore_ref": "redis.md"}]
        output = format_rule_output(matched)
        assert 'Related lore: mindvault lore search --query "redis.md"' in output

    def test_no_lore_ref(self):
        matched = [{"id": "r1", "type": "warn", "message": "msg", "lore_ref": None}]
        output = format_rule_output(matched)
        assert "Related lore" not in output
