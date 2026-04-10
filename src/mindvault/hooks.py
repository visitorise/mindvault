"""Claude Code hook generator + git hook installer."""

from __future__ import annotations

import json
from pathlib import Path

_GIT_HOOK_MARKER = "# MindVault auto-update"
_GIT_HOOK_CONTENT = """
# MindVault auto-update
mindvault_update() {
  if command -v mindvault &>/dev/null; then
    mindvault update --quiet &
  fi
}
mindvault_update
"""

DIRTY_FILENAME = ".mindvault_dirty.json"


def install_git_hook(repo_dir: Path) -> bool:
    """Install post-commit hook for auto-update.

    Args:
        repo_dir: Path to the git repository root.

    Returns:
        True if hook was installed successfully.
    """
    repo_dir = Path(repo_dir)
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        return False

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "post-commit"

    # Check if already installed
    if hook_file.exists():
        existing = hook_file.read_text(encoding="utf-8")
        if _GIT_HOOK_MARKER in existing:
            return True  # Already installed
        # Append to existing hook
        content = existing.rstrip("\n") + "\n" + _GIT_HOOK_CONTENT
    else:
        content = "#!/bin/sh\n" + _GIT_HOOK_CONTENT

    hook_file.write_text(content, encoding="utf-8")
    hook_file.chmod(0o755)
    return True


def install_claude_hooks(settings_path: Path = None) -> bool:
    """Add PostToolUse + Stop hooks to Claude Code settings.

    This is opt-in only — not called automatically by install.

    Args:
        settings_path: Path to Claude Code settings.json.

    Returns:
        True if hooks were added successfully.
    """
    if settings_path is None:
        settings_path = Path.home() / ".claude" / "settings.json"
    settings_path = Path(settings_path)

    # Load existing settings or create new
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            settings = {}

    hooks = settings.setdefault("hooks", {})

    # PostToolUse hook
    post_tool_hooks = hooks.setdefault("PostToolUse", [])
    mv_post_hook = {
        "matcher": "Write|Edit",
        "command": 'mindvault mark-dirty "$FILE_PATH"',
    }
    # Check if already present
    already_has_post = any(
        h.get("command", "").startswith("mindvault mark-dirty")
        for h in post_tool_hooks
    )
    if not already_has_post:
        post_tool_hooks.append(mv_post_hook)

    # Stop hook
    stop_hooks = hooks.setdefault("Stop", [])
    mv_stop_hook = {
        "command": "mindvault flush",
    }
    already_has_stop = any(
        h.get("command", "").startswith("mindvault flush")
        for h in stop_hooks
    )
    if not already_has_stop:
        stop_hooks.append(mv_stop_hook)

    # Write settings
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


def mark_dirty(file_path: Path, output_dir: Path) -> None:
    """Flag a file as needing re-extraction.

    Args:
        file_path: Path to the file that changed.
        output_dir: MindVault output directory.
    """
    file_path = Path(file_path)
    output_dir = Path(output_dir)
    dirty_file = output_dir / DIRTY_FILENAME

    dirty_set: list[str] = []
    if dirty_file.exists():
        try:
            dirty_set = json.loads(dirty_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            dirty_set = []

    file_str = str(file_path.resolve())
    if file_str not in dirty_set:
        dirty_set.append(file_str)

    output_dir.mkdir(parents=True, exist_ok=True)
    dirty_file.write_text(
        json.dumps(dirty_set, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def flush(output_dir: Path) -> dict:
    """Process all dirty files. Called at session end.

    Args:
        output_dir: MindVault output directory.

    Returns:
        Dict with stats: {changed, files_processed} or {changed: 0}.
    """
    output_dir = Path(output_dir)
    dirty_file = output_dir / DIRTY_FILENAME

    if not dirty_file.exists():
        return {"changed": 0}

    try:
        dirty_list = json.loads(dirty_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"changed": 0}

    if not dirty_list:
        return {"changed": 0}

    # Find source_dir from output_dir (go up one level if output_dir is mindvault-out)
    # Try to find source by checking parent
    source_dir = output_dir.parent
    if not (source_dir / "src").exists() and not any(source_dir.glob("*.py")):
        # Fallback: use output_dir parent
        source_dir = output_dir.parent

    from mindvault.pipeline import run_incremental
    result = run_incremental(source_dir, output_dir)

    # Clear dirty list
    dirty_file.write_text("[]", encoding="utf-8")

    result["files_processed"] = len(dirty_list)
    return result
