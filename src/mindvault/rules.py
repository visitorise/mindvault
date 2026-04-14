"""Rules Engine — project-level rules that inject warnings when AI violates them.

Rules are stored as YAML (with JSON fallback) at:
  - mindvault-out/rules.yaml  (project-level, higher priority)
  - ~/.mindvault/rules.yaml   (global, lower priority)

Each rule has a regex trigger that is matched against tool input/output.
Matched rules produce <rules-warning> or <rules-block> tags injected into
the AI context via a PostToolUse hook.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

# YAML with JSON fallback
try:
    import yaml

    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False

RULES_FILENAME = "rules.yaml"
_RULES_VERSION = 1

# Valid rule types
RULE_TYPES = ("warn", "block")

# Valid scope values
RULE_SCOPES = ("command", "output", "both")


def _read_rules_file(path: Path) -> list[dict]:
    """Read rules from a YAML (or JSON fallback) file.

    Returns an empty list on missing/empty/malformed files.
    """
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    data = None
    if _HAS_YAML:
        try:
            data = yaml.safe_load(text)
        except Exception:
            pass

    if data is None:
        # JSON fallback
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return []

    if not isinstance(data, dict):
        return []

    rules = data.get("rules", [])
    if not isinstance(rules, list):
        return []

    return rules


def _write_rules_file(path: Path, rules: list[dict]) -> None:
    """Write rules to a YAML (or JSON fallback) file atomically."""
    data = {"version": _RULES_VERSION, "rules": rules}

    if _HAS_YAML:
        content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        content = json.dumps(data, indent=2, ensure_ascii=False)

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _normalize_rule(rule: dict) -> dict | None:
    """Validate and normalize a single rule dict. Returns None if invalid."""
    if not isinstance(rule, dict):
        return None

    rule_id = rule.get("id")
    trigger = rule.get("trigger")
    if not rule_id or not trigger:
        return None

    # Validate regex
    try:
        re.compile(trigger)
    except re.error:
        print(f"Warning: invalid regex in rule '{rule_id}': {trigger}", file=sys.stderr)
        return None

    return {
        "id": str(rule_id),
        "trigger": str(trigger),
        "type": rule.get("type", "warn") if rule.get("type") in RULE_TYPES else "warn",
        "message": str(rule.get("message", "")),
        "lore_ref": rule.get("lore_ref"),
        "scope": rule.get("scope", "both") if rule.get("scope") in RULE_SCOPES else "both",
        "enabled": rule.get("enabled", True),
    }


def load_rules(output_dir: Path) -> list[dict]:
    """Load project + global rules. Project rules override global when IDs conflict.

    Args:
        output_dir: Project output directory (e.g. mindvault-out/).

    Returns:
        Merged list of normalized, valid rules.
    """
    output_dir = Path(output_dir)

    # Global rules
    global_path = Path.home() / ".mindvault" / RULES_FILENAME
    global_rules = _read_rules_file(global_path)

    # Project rules
    project_path = output_dir / RULES_FILENAME
    project_rules = _read_rules_file(project_path)

    # Merge: project overrides global by ID
    rules_by_id: dict[str, dict] = {}

    for raw in global_rules:
        normed = _normalize_rule(raw)
        if normed:
            rules_by_id[normed["id"]] = normed

    for raw in project_rules:
        normed = _normalize_rule(raw)
        if normed:
            rules_by_id[normed["id"]] = normed  # override global

    return list(rules_by_id.values())


def check_rules(text: str, rules: list[dict], context: str = "both") -> list[dict]:
    """Check text against rules and return all matching rules.

    Args:
        text: Text to check (e.g. tool command + output).
        rules: List of normalized rule dicts.
        context: Which scope to match: "command", "output", or "both".

    Returns:
        List of matched rule dicts.
    """
    matched = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue

        scope = rule.get("scope", "both")
        # context="both" means check everything — match all scopes.
        # Only filter when context is specifically "command" or "output".
        if context != "both" and scope != "both" and scope != context:
            continue

        trigger = rule.get("trigger", "")
        try:
            if re.search(trigger, text, re.IGNORECASE):
                matched.append(rule)
        except re.error:
            # Skip invalid regex silently at runtime
            continue

    return matched


def add_rule(
    output_dir: Path,
    rule_id: str,
    trigger: str,
    rule_type: str,
    message: str,
    lore_ref: str | None = None,
    scope: str = "both",
    enabled: bool = True,
) -> Path:
    """Add a rule to the project rules file.

    Args:
        output_dir: Project output directory.
        rule_id: Unique rule identifier.
        trigger: Regex pattern.
        rule_type: "warn" or "block".
        message: Message to inject on match.
        lore_ref: Optional related lore entry.
        scope: Rule scope — "command", "output", or "both".
        enabled: Whether the rule is active.

    Returns:
        Path to the rules file.
    """
    output_dir = Path(output_dir)
    rules_path = output_dir / RULES_FILENAME

    # Validate regex
    try:
        re.compile(trigger)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {trigger!r} ({e})")

    if rule_type not in RULE_TYPES:
        raise ValueError(f"Invalid rule type: {rule_type!r}. Must be one of {RULE_TYPES}")

    if scope not in RULE_SCOPES:
        raise ValueError(f"Invalid scope: {scope!r}. Must be one of {RULE_SCOPES}")

    existing = _read_rules_file(rules_path)

    # Remove existing rule with same ID (update semantics)
    existing = [r for r in existing if r.get("id") != rule_id]

    new_rule: dict = {
        "id": rule_id,
        "trigger": trigger,
        "type": rule_type,
        "message": message,
        "scope": scope,
        "enabled": enabled,
    }
    if lore_ref:
        new_rule["lore_ref"] = lore_ref

    existing.append(new_rule)
    _write_rules_file(rules_path, existing)

    return rules_path


def remove_rule(output_dir: Path, rule_id: str) -> bool:
    """Remove a rule by ID from the project rules file.

    Args:
        output_dir: Project output directory.
        rule_id: Rule ID to remove.

    Returns:
        True if the rule was found and removed.
    """
    output_dir = Path(output_dir)
    rules_path = output_dir / RULES_FILENAME

    existing = _read_rules_file(rules_path)
    before_count = len(existing)
    filtered = [r for r in existing if r.get("id") != rule_id]

    if len(filtered) == before_count:
        return False

    _write_rules_file(rules_path, filtered)
    return True


def list_rules(output_dir: Path) -> list[dict]:
    """List all active rules (project + global merged).

    Args:
        output_dir: Project output directory.

    Returns:
        List of all normalized, enabled rules.
    """
    all_rules = load_rules(output_dir)
    return [r for r in all_rules if r.get("enabled", True)]


def format_rule_output(matched: list[dict]) -> str:
    """Format matched rules as hook output tags.

    Args:
        matched: List of matched rule dicts from check_rules().

    Returns:
        Formatted string with <rules-warning> or <rules-block> tags.
    """
    parts = []
    for rule in matched:
        tag = "rules-block" if rule["type"] == "block" else "rules-warning"
        lines = [f"<{tag}>"]
        lines.append(f"Rule: {rule['id']}")
        lines.append(rule["message"])
        if rule.get("lore_ref"):
            lines.append(f'Related lore: mindvault lore search --query "{rule["lore_ref"]}"')
        lines.append(f"</{tag}>")
        parts.append("\n".join(lines))
    return "\n".join(parts)
