"""Lore — decision/failure recording system for persistent learning.

Records decisions, failures, and learnings as structured markdown files.
Lore entries are automatically indexed into the search index, making them
queryable via `mindvault query` and injected into AI sessions via the
auto-context hook.

Storage: mindvault-out/lore/YYYY-MM-DD-slug.md
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from mindvault.index import (
    _tokenize,
    _extract_title,
    _extract_headings,
    _hash_content,
    _compute_idf,
    load_index,
)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename (Codex finding #9)."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _escape_yaml_value(value: str) -> str:
    """Escape a string value for safe YAML frontmatter (Codex finding #8)."""
    if any(c in value for c in (":", "[", "]", "{", "}", "#", "&", "*", "!", "|", ">", "'", '"', "%", "@", "`", "---", "\n")):
        escaped = value.replace('"', '\\"').replace("\n", " ")
        return f'"{escaped}"'
    return value


# Valid lore entry types
LORE_TYPES = ("decision", "failure", "learning", "rollback", "tradeoff")


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = re.sub(r"[^a-z0-9\s-]", "", text.lower())
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:60] or "untitled"


def record(
    output_dir: Path,
    title: str,
    context: str,
    outcome: str,
    lore_type: str = "decision",
    tags: list[str] | None = None,
) -> Path:
    """Record a lore entry.

    Args:
        output_dir: MindVault output directory (mindvault-out/).
        title: Short title of the decision/failure.
        context: Why this decision was made / what happened.
        outcome: What was the result / what was learned.
        lore_type: One of: decision, failure, learning, rollback, tradeoff.
        tags: Optional list of tags for categorization.

    Returns:
        Path to the created lore file.
    """
    if lore_type not in LORE_TYPES:
        raise ValueError(f"Invalid lore type: {lore_type}. Must be one of {LORE_TYPES}")

    lore_dir = Path(output_dir) / "lore"
    lore_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = _slugify(title)
    filename = f"{date_str}-{slug}.md"

    # Avoid collisions
    filepath = lore_dir / filename
    counter = 2
    while filepath.exists():
        filepath = lore_dir / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    tags_str = ", ".join(_escape_yaml_value(t) for t in tags) if tags else ""
    safe_title = _escape_yaml_value(title)
    content = f"""---
title: {safe_title}
type: {lore_type}
date: {date_str}
tags: [{tags_str}]
---

# {title}

## Context

{context}

## Outcome

{outcome}
"""

    filepath.write_text(content, encoding="utf-8")

    # Auto-index the new entry
    index_path = Path(output_dir) / "search_index.json"
    if index_path.exists():
        _index_lore_entry(filepath, output_dir, index_path)

    return filepath


def list_entries(output_dir: Path, lore_type: str | None = None) -> list[dict]:
    """List all lore entries.

    Args:
        output_dir: MindVault output directory.
        lore_type: Optional filter by type.

    Returns:
        List of dicts with keys: path, title, type, date, tags.
    """
    lore_dir = Path(output_dir) / "lore"
    if not lore_dir.exists():
        return []

    entries = []
    for md_file in sorted(lore_dir.glob("*.md"), reverse=True):
        meta = _parse_frontmatter(md_file)
        if lore_type and meta.get("type") != lore_type:
            continue
        entries.append({
            "path": str(md_file),
            "filename": md_file.name,
            "title": meta.get("title", md_file.stem),
            "type": meta.get("type", "decision"),
            "date": meta.get("date", ""),
            "tags": meta.get("tags", []),
        })

    return entries


def search_lore(output_dir: Path, query: str, top_k: int = 5) -> list[dict]:
    """Search lore entries using BM25.

    Args:
        output_dir: MindVault output directory.
        query: Search query string.
        top_k: Number of results to return.

    Returns:
        List of matching entries with scores.
    """
    from mindvault.search import search as bm25_search

    index_path = Path(output_dir) / "search_index.json"
    if not index_path.exists():
        return []

    results = bm25_search(query, index_path, top_k=top_k * 3)
    # Filter to lore entries only
    lore_results = [r for r in results if r["path"].startswith("lore/")]
    return lore_results[:top_k]


def index_all_lore(output_dir: Path) -> int:
    """Index all lore entries into the search index.

    Args:
        output_dir: MindVault output directory.

    Returns:
        Number of lore entries indexed.
    """
    lore_dir = Path(output_dir) / "lore"
    if not lore_dir.exists():
        return 0

    index_path = Path(output_dir) / "search_index.json"
    index_data = load_index(index_path)
    docs = index_data.get("docs", {})
    count = 0

    # Track existing lore files
    current_lore_keys: set[str] = set()

    for md_file in lore_dir.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        content_hash = _hash_content(content)
        key = f"lore/{md_file.name}"
        current_lore_keys.add(key)

        if key in docs and docs[key].get("hash") == content_hash:
            continue

        meta = _parse_frontmatter(md_file)
        title = meta.get("title", md_file.stem)

        # Include type and tags in searchable text
        extra_text = f"type: {meta.get('type', '')} tags: {' '.join(meta.get('tags', []))}"
        full_text = f"{extra_text}\n{content}"

        docs[key] = {
            "title": title,
            "headings": _extract_headings(content),
            "tokens": _tokenize(full_text),
            "hash": content_hash,
        }
        count += 1

    # Remove deleted lore entries from index (Codex finding #3)
    deleted_lore = [k for k in docs if k.startswith("lore/") and k not in current_lore_keys]
    for k in deleted_lore:
        del docs[k]
        count += 1

    if count > 0:
        index_data["docs"] = docs
        index_data["doc_count"] = len(docs)
        index_data["idf"] = _compute_idf(docs)
        _atomic_write_json(index_path, index_data)

    return count


def _index_lore_entry(filepath: Path, output_dir: Path, index_path: Path) -> None:
    """Index a single lore entry into the search index."""
    index_data = load_index(index_path)
    docs = index_data.get("docs", {})

    content = filepath.read_text(encoding="utf-8")
    content_hash = _hash_content(content)
    key = f"lore/{filepath.name}"

    meta = _parse_frontmatter(filepath)
    title = meta.get("title", filepath.stem)

    extra_text = f"type: {meta.get('type', '')} tags: {' '.join(meta.get('tags', []))}"
    full_text = f"{extra_text}\n{content}"

    docs[key] = {
        "title": title,
        "headings": _extract_headings(content),
        "tokens": _tokenize(full_text),
        "hash": content_hash,
    }

    index_data["docs"] = docs
    index_data["doc_count"] = len(docs)
    index_data["idf"] = _compute_idf(docs)
    _atomic_write_json(index_path, index_data)


# Lore detection patterns with descriptions and defaults
LORE_PATTERNS = {
    "rollback": {
        "label": "Code rollback (git revert/reset)",
        "description": "Records why code was rolled back",
        "default": "auto",
    },
    "test_failure": {
        "label": "Repeated test failure",
        "description": "Records persistent test failures and their resolution",
        "default": "ask",
    },
    "dependency": {
        "label": "Dependency changes (install/remove)",
        "description": "Records why packages were added or removed",
        "default": "ignore",
    },
    "architecture": {
        "label": "Architecture changes (major file restructure)",
        "description": "Records why project structure was changed",
        "default": "ask",
    },
    "build_fix": {
        "label": "Build failure fix",
        "description": "Records what was broken and how it was fixed",
        "default": "auto",
    },
}

LORE_ACTIONS = ("auto", "ask", "ignore")


def setup_lore(interactive: bool = True) -> dict:
    """Interactive lore configuration setup (lazy onboarding).

    Args:
        interactive: If True, prompts user. If False, uses defaults.

    Returns:
        The saved configuration dict.
    """
    config_dir = Path.home() / ".mindvault"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "lore-config.json"

    if not interactive:
        # Use recommended defaults
        config = {
            "version": 1,
            "patterns": {k: v["default"] for k, v in LORE_PATTERNS.items()},
        }
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        return config

    print()
    print("━━ MindVault Lore Setup ━━")
    print()
    print("Lore automatically tracks decisions, failures, and learnings")
    print("so your AI remembers WHY things changed across sessions.")
    print()
    print("For each event type, choose:")
    print("  [auto]   — record automatically (no interruption)")
    print("  [ask]    — AI will ask you before recording")
    print("  [ignore] — skip entirely")
    print()

    patterns: dict[str, str] = {}
    for key, info in LORE_PATTERNS.items():
        default = info["default"]
        label = info["label"]
        desc = info["description"]

        # Show recommended marker
        choices = []
        for action in LORE_ACTIONS:
            marker = " ← recommended" if action == default else ""
            choices.append(f"{action}{marker}")

        print(f"  {label}")
        print(f"    → {desc}")
        print(f"    Options: {' | '.join(choices)}")

        while True:
            answer = input(f"    Choice [{default}]: ").strip().lower()
            if not answer:
                answer = default
            if answer in LORE_ACTIONS:
                patterns[key] = answer
                break
            print(f"    Invalid. Choose: {', '.join(LORE_ACTIONS)}")
        print()

    config = {"version": 1, "patterns": patterns}
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    # Install the lore hook
    from mindvault.hooks import install_lore_hook
    install_lore_hook()

    # Mark as noticed so the one-time notice doesn't show again (Codex finding #6)
    notice_flag = config_dir / ".lore-noticed"
    notice_flag.touch()

    print("✓ Lore configuration saved")
    print("✓ Lore detection hook installed")
    print()
    print("You can change settings later with: mindvault lore setup")

    return config


def load_lore_config() -> dict | None:
    """Load lore configuration. Returns None if not configured."""
    config_path = Path.home() / ".mindvault" / "lore-config.json"
    if not config_path.exists():
        return None
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _parse_frontmatter(filepath: Path) -> dict:
    """Parse YAML-like frontmatter from a markdown file."""
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}

    end = text.find("---", 3)
    if end == -1:
        return {}

    front = text[3:end].strip()
    meta: dict = {}
    for line in front.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "tags":
            # Parse [tag1, tag2] format
            m = re.match(r"\[(.*)\]", value)
            if m:
                meta[key] = [t.strip() for t in m.group(1).split(",") if t.strip()]
            else:
                meta[key] = [t.strip() for t in value.split(",") if t.strip()]
        else:
            meta[key] = value
    return meta
