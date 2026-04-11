"""Unit tests for the 0.4.0 canonical ID scheme.

Locks the contract of ``_make_canonical_id`` + ``_make_ref_id`` +
``_rel_path_slug`` so any future refactor has an immediate trip-wire.
"""

from __future__ import annotations

from pathlib import Path

from mindvault.extract import (
    _make_canonical_id,
    _make_ref_id,
    _rel_path_slug,
    _sanitize_id,
)


class TestRelPathSlug:
    def test_uses_index_root_relative_path(self, tmp_path: Path):
        """index_root strips the project prefix."""
        f = tmp_path / "src" / "auth" / "utils.py"
        f.parent.mkdir(parents=True)
        f.write_text("x")
        assert _rel_path_slug(f, tmp_path) == "src__auth__utils_py"

    def test_single_file_at_root(self, tmp_path: Path):
        f = tmp_path / "plan.md"
        f.write_text("x")
        assert _rel_path_slug(f, tmp_path) == "plan_md"

    def test_without_index_root_uses_full_parts(self, tmp_path: Path):
        """No index_root → full path parts are used. Still collision-safe."""
        f = tmp_path / "notes" / "plan.md"
        f.parent.mkdir()
        f.write_text("x")
        slug = _rel_path_slug(f, None)
        # Should at least include the filename component
        assert "plan_md" in slug
        # Should include the directory component
        assert "notes" in slug

    def test_path_not_under_index_root(self, tmp_path: Path):
        """File outside index_root falls back gracefully (no crash)."""
        other = tmp_path / "other"
        other.mkdir()
        f = other / "file.py"
        f.write_text("x")
        unrelated_root = tmp_path / "different_root"
        unrelated_root.mkdir()
        slug = _rel_path_slug(f, unrelated_root)
        assert "file_py" in slug

    def test_special_chars_sanitized(self, tmp_path: Path):
        """Non-[a-z0-9_] chars in path components become underscores."""
        f = tmp_path / "my folder" / "file-name.md"
        f.parent.mkdir()
        f.write_text("x")
        slug = _rel_path_slug(f, tmp_path)
        assert slug == "my_folder__file_name_md"


class TestMakeCanonicalId:
    def test_basic_format(self, tmp_path: Path):
        f = tmp_path / "notes" / "plan.md"
        f.parent.mkdir()
        f.write_text("x")
        cid = _make_canonical_id(f, "header", "Auth Rewrite Plan", tmp_path)
        assert cid == "notes__plan_md::header::auth_rewrite_plan"

    def test_file_level_node_has_empty_local(self, tmp_path: Path):
        f = tmp_path / "notes" / "plan.md"
        f.parent.mkdir()
        f.write_text("x")
        cid = _make_canonical_id(f, "file", "", tmp_path)
        assert cid == "notes__plan_md::file::"

    def test_code_function(self, tmp_path: Path):
        f = tmp_path / "src" / "auth" / "utils.py"
        f.parent.mkdir(parents=True)
        f.write_text("x")
        cid = _make_canonical_id(f, "function", "validate", tmp_path)
        assert cid == "src__auth__utils_py::function::validate"

    def test_same_stem_different_dirs_produce_distinct_ids(self, tmp_path: Path):
        """The whole point of the refactor: no more collisions on shared stems."""
        a = tmp_path / "src" / "auth" / "utils.py"
        b = tmp_path / "src" / "db" / "utils.py"
        for p in (a, b):
            p.parent.mkdir(parents=True)
            p.write_text("x")
        id_a = _make_canonical_id(a, "function", "validate", tmp_path)
        id_b = _make_canonical_id(b, "function", "validate", tmp_path)
        assert id_a != id_b
        assert id_a == "src__auth__utils_py::function::validate"
        assert id_b == "src__db__utils_py::function::validate"

    def test_kind_sanitized(self, tmp_path: Path):
        f = tmp_path / "plan.md"
        f.write_text("x")
        cid = _make_canonical_id(f, "SomeWeird-Kind!", "name", tmp_path)
        # kind becomes sanitized lowercase
        assert "::someweird_kind_::" in cid

    def test_empty_entity_name_allowed(self, tmp_path: Path):
        f = tmp_path / "plan.md"
        f.write_text("x")
        cid = _make_canonical_id(f, "file", "", tmp_path)
        assert cid.endswith("::file::")

    def test_unicode_entity_name_collapses_to_underscores(self, tmp_path: Path):
        """Non-ASCII entity names are sanitized — IDs stay ASCII-safe.

        The `label` field preserves the original Unicode, so UI/search still
        work; only the internal ID slug is ASCII.
        """
        f = tmp_path / "plan.md"
        f.write_text("x")
        cid = _make_canonical_id(f, "header", "한글 제목", tmp_path)
        assert cid.startswith("plan_md::header::")
        # The Unicode collapses to underscores via _sanitize_id
        assert cid == "plan_md::header::_____"

    def test_round_trip_stability(self, tmp_path: Path):
        """Same inputs always produce the same ID (deterministic)."""
        f = tmp_path / "src" / "a.py"
        f.parent.mkdir()
        f.write_text("x")
        ids = {
            _make_canonical_id(f, "function", "foo", tmp_path)
            for _ in range(20)
        }
        assert len(ids) == 1


class TestMakeRefId:
    def test_format(self):
        assert _make_ref_id("missing_helper") == "__unresolved__::ref::missing_helper"

    def test_sanitizes_input(self):
        assert _make_ref_id("Some-Thing!") == "__unresolved__::ref::some_thing_"

    def test_distinct_from_canonical_ids(self):
        """Ref IDs must never collide with canonical IDs (different prefix)."""
        ref = _make_ref_id("foo")
        # Canonical IDs start with a path-like slug (letters), refs start
        # with the literal ``__unresolved__``
        assert ref.startswith("__unresolved__::")


class TestIdCollisionProperties:
    def test_file_vs_header_separated_by_kind(self, tmp_path: Path):
        """Same file, same local, different kind → different IDs."""
        f = tmp_path / "plan.md"
        f.write_text("x")
        file_id = _make_canonical_id(f, "file", "", tmp_path)
        header_id = _make_canonical_id(f, "header", "", tmp_path)
        assert file_id != header_id
        assert file_id.split("::")[1] == "file"
        assert header_id.split("::")[1] == "header"

    def test_function_vs_class_separated_by_kind(self, tmp_path: Path):
        """A Python file can have `class User` and `def User()` with same name.

        Both would produce colliding IDs under the old scheme. Under 0.4.0
        they're separated by the `kind` component.
        """
        f = tmp_path / "src" / "user.py"
        f.parent.mkdir()
        f.write_text("x")
        class_id = _make_canonical_id(f, "class", "User", tmp_path)
        func_id = _make_canonical_id(f, "function", "User", tmp_path)
        assert class_id != func_id
