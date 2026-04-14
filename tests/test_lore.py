"""Unit tests for mindvault.lore module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mindvault.lore import (
    record,
    list_entries,
    index_all_lore,
    _slugify,
    _parse_frontmatter,
    _escape_yaml_value,
    _atomic_write_json,
    LORE_TYPES,
)


class TestSlugify:
    def test_basic(self):
        assert _slugify("Redis Cache Rollback") == "redis-cache-rollback"

    def test_korean(self):
        # Korean chars get stripped, but that's OK — date prefix ensures uniqueness
        slug = _slugify("캐시 롤백")
        assert isinstance(slug, str)

    def test_special_chars(self):
        assert _slugify("test/slash & special!") == "testslash-special"

    def test_max_length(self):
        long_title = "a" * 100
        assert len(_slugify(long_title)) <= 60


class TestRecord:
    def test_creates_file(self, tmp_path):
        filepath = record(
            output_dir=tmp_path,
            title="Test Decision",
            context="Some context",
            outcome="Good outcome",
        )
        assert filepath.exists()
        assert filepath.name.endswith(".md")
        assert "Test Decision" in filepath.read_text()

    def test_creates_lore_directory(self, tmp_path):
        record(tmp_path, "Test", "ctx", "out")
        assert (tmp_path / "lore").is_dir()

    def test_frontmatter_format(self, tmp_path):
        filepath = record(
            tmp_path, "My Decision", "why", "result",
            lore_type="failure", tags=["tag1", "tag2"],
        )
        content = filepath.read_text()
        assert "title: My Decision" in content
        assert "type: failure" in content
        assert "tags: [tag1, tag2]" in content

    def test_invalid_type_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid lore type"):
            record(tmp_path, "Test", "ctx", "out", lore_type="invalid")

    def test_collision_avoidance(self, tmp_path):
        f1 = record(tmp_path, "Same Title", "ctx1", "out1")
        f2 = record(tmp_path, "Same Title", "ctx2", "out2")
        assert f1 != f2
        assert f1.exists()
        assert f2.exists()

    def test_auto_indexes_when_index_exists(self, tmp_path):
        # Create a minimal search index
        index_path = tmp_path / "search_index.json"
        index_path.write_text(json.dumps({
            "version": 1, "doc_count": 0, "docs": {}, "idf": {},
        }))

        record(tmp_path, "Indexed Entry", "ctx", "out", tags=["test"])

        index = json.loads(index_path.read_text())
        lore_keys = [k for k in index["docs"] if k.startswith("lore/")]
        assert len(lore_keys) == 1
        assert index["docs"][lore_keys[0]]["title"] == "Indexed Entry"


class TestListEntries:
    def test_empty(self, tmp_path):
        assert list_entries(tmp_path) == []

    def test_lists_all(self, tmp_path):
        record(tmp_path, "Entry 1", "ctx", "out", lore_type="decision")
        record(tmp_path, "Entry 2", "ctx", "out", lore_type="failure")
        entries = list_entries(tmp_path)
        assert len(entries) == 2

    def test_filter_by_type(self, tmp_path):
        record(tmp_path, "Decision", "ctx", "out", lore_type="decision")
        record(tmp_path, "Failure", "ctx", "out", lore_type="failure")
        decisions = list_entries(tmp_path, lore_type="decision")
        assert len(decisions) == 1
        assert decisions[0]["type"] == "decision"


class TestIndexAllLore:
    def test_indexes_entries(self, tmp_path):
        index_path = tmp_path / "search_index.json"
        index_path.write_text(json.dumps({
            "version": 1, "doc_count": 0, "docs": {}, "idf": {},
        }))

        record(tmp_path, "Entry A", "ctx", "out")
        record(tmp_path, "Entry B", "ctx", "out")

        count = index_all_lore(tmp_path)
        # Auto-index already indexed them, so reindex returns 0
        # But docs should exist
        index = json.loads(index_path.read_text())
        lore_keys = [k for k in index["docs"] if k.startswith("lore/")]
        assert len(lore_keys) == 2

    def test_skips_unchanged(self, tmp_path):
        index_path = tmp_path / "search_index.json"
        index_path.write_text(json.dumps({
            "version": 1, "doc_count": 0, "docs": {}, "idf": {},
        }))

        record(tmp_path, "Test", "ctx", "out")
        # First reindex
        index_all_lore(tmp_path)
        # Second reindex should skip (hash unchanged)
        count = index_all_lore(tmp_path)
        assert count == 0


class TestParseFrontmatter:
    def test_parses_tags(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\ntitle: Test\ntags: [a, b, c]\n---\n# Test\n")
        meta = _parse_frontmatter(f)
        assert meta["title"] == "Test"
        assert meta["tags"] == ["a", "b", "c"]

    def test_no_frontmatter(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Just a heading\n")
        assert _parse_frontmatter(f) == {}


class TestDeletedLoreCleanup:
    """Codex finding #3: deleted lore entries should be removed from index."""

    def test_removes_deleted_entries(self, tmp_path):
        index_path = tmp_path / "search_index.json"
        index_path.write_text(json.dumps({
            "version": 1, "doc_count": 0, "docs": {}, "idf": {},
        }))

        f1 = record(tmp_path, "Entry to keep", "ctx", "out")
        f2 = record(tmp_path, "Entry to delete", "ctx", "out")
        index_all_lore(tmp_path)

        index = json.loads(index_path.read_text())
        assert len([k for k in index["docs"] if k.startswith("lore/")]) == 2

        # Delete one entry
        f2.unlink()
        index_all_lore(tmp_path)

        index = json.loads(index_path.read_text())
        lore_keys = [k for k in index["docs"] if k.startswith("lore/")]
        assert len(lore_keys) == 1


class TestYamlEscaping:
    """Codex finding #8: frontmatter injection prevention."""

    def test_escapes_colons(self):
        assert _escape_yaml_value("key: value") == '"key: value"'

    def test_escapes_brackets(self):
        assert _escape_yaml_value("[tag]") == '"[tag]"'

    def test_no_escape_plain(self):
        assert _escape_yaml_value("simple title") == "simple title"

    def test_escapes_newlines(self):
        result = _escape_yaml_value("line1\nline2")
        assert "\n" not in result

    def test_record_with_special_chars(self, tmp_path):
        filepath = record(
            tmp_path, "Title: with colon [and bracket]",
            "ctx", "out", tags=["tag:1", "[special]"],
        )
        content = filepath.read_text()
        # Should not corrupt frontmatter parsing
        meta = _parse_frontmatter(filepath)
        assert meta["type"] == "decision"


class TestAtomicWrite:
    """Codex finding #9: atomic index writes."""

    def test_atomic_write_creates_file(self, tmp_path):
        path = tmp_path / "test.json"
        _atomic_write_json(path, {"key": "value"})
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["key"] == "value"

    def test_atomic_write_overwrites(self, tmp_path):
        path = tmp_path / "test.json"
        _atomic_write_json(path, {"v": 1})
        _atomic_write_json(path, {"v": 2})
        data = json.loads(path.read_text())
        assert data["v"] == 2

    def test_no_temp_files_left(self, tmp_path):
        path = tmp_path / "test.json"
        _atomic_write_json(path, {"ok": True})
        # No .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestLoreHookPatterns:
    """Codex finding #5, #10: all 5 patterns detectable, hook coverage."""

    def test_all_lore_patterns_defined(self):
        from mindvault.lore import LORE_PATTERNS
        assert "rollback" in LORE_PATTERNS
        assert "test_failure" in LORE_PATTERNS
        assert "dependency" in LORE_PATTERNS
        assert "architecture" in LORE_PATTERNS
        assert "build_fix" in LORE_PATTERNS

    def test_hook_script_contains_all_patterns(self):
        from mindvault.hooks import _LORE_HOOK_SCRIPT_TEMPLATE
        for pattern in ("rollback", "test_failure", "dependency", "architecture", "build_fix"):
            assert f'DETECTED="{pattern}"' in _LORE_HOOK_SCRIPT_TEMPLATE, \
                f"Pattern {pattern} missing from hook script"

    def test_hook_script_reads_stderr(self):
        from mindvault.hooks import _LORE_HOOK_SCRIPT_TEMPLATE
        assert "stderr" in _LORE_HOOK_SCRIPT_TEMPLATE

    def test_hook_script_reads_command(self):
        from mindvault.hooks import _LORE_HOOK_SCRIPT_TEMPLATE
        assert "command" in _LORE_HOOK_SCRIPT_TEMPLATE

    def test_hook_version_is_3(self):
        from mindvault.hooks import _LORE_HOOK_SCRIPT_TEMPLATE
        assert "MINDVAULT_LORE_HOOK_VERSION=3" in _LORE_HOOK_SCRIPT_TEMPLATE

    def test_notice_does_not_write_flag(self):
        """Codex finding #6: .lore-noticed should NOT be written by the hook."""
        from mindvault.hooks import _LORE_HOOK_SCRIPT_TEMPLATE
        # The hook should tell the AI to write the flag, not write it directly
        assert 'touch "$NOTICE_FLAG"' not in _LORE_HOOK_SCRIPT_TEMPLATE.split("# ---- Not configured")[1].split("echo")[0]
