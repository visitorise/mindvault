"""Claude Code hook generator + git hook installer."""

from __future__ import annotations

import json
from pathlib import Path

_GIT_HOOK_MARKER = "# MindVault auto-update"

# Bump this whenever the hook script gains a behavior change so old
# broken installs get auto-overwritten on the next `mindvault install`.
MINDVAULT_HOOK_VERSION = 5

_PROMPT_HOOK_SCRIPT_TEMPLATE = '''#!/bin/bash
# MindVault auto-context hook
# MINDVAULT_HOOK_VERSION=5
#
# Smart context injection: only injects when the prompt is likely
# code/project-related. Skips conversational, short, and command prompts.
#
# v5: Smart skip (conversational/short prompts), strict budget cap,
#     node ID truncation, head-limit safety net.

# 1) Read stdin (Claude Code hook contract)
INPUT="$(cat 2>/dev/null || true)"
[ -z "$INPUT" ] && exit 0

# 2) Extract prompt + cwd from JSON payload.
PROMPT=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
    p = (
        data.get("prompt")
        or data.get("userInput")
        or data.get("message")
        or data.get("input")
        or ""
    )
    print(p)
except Exception:
    print(raw)
' 2>/dev/null)

# 3) Smart skip — don't inject for non-code prompts
[ ${#PROMPT} -lt 20 ] && exit 0
case "$PROMPT" in
    /*) exit 0 ;;
esac

# Skip purely conversational / short response prompts (Python classifier)
SHOULD_SKIP=$(printf '%s' "$PROMPT" | python3 -c '
import sys, re
p = sys.stdin.read().strip().lower()

# Skip: telegram prefix
if p.startswith("[텔레그램") or p.startswith("[telegram"):
    print("skip"); sys.exit()

# Skip: very short (likely yes/no/ok/confirmation)
if len(p) < 30 and not any(c in p for c in [".", "/", "_", "(", "{"]):
    print("skip"); sys.exit()

# Skip: conversational patterns (no technical content)
CONV_PATTERNS = [
    r"^(응|ㅇ|ㅋ|ㅎ|ㅇㅋ|ok|yes|no|nah|sure|yep|nope|alright|thanks|thx|고마워|ㄱㅅ|맞아|그래|좋아|알겠어|확인|완료)\s*[.!?]*$",
    r"^(어|음|아|와|오|헐|대박|진짜|정말|그렇구나|그렇네)\s*[.!?]*$",
]
for pat in CONV_PATTERNS:
    if re.match(pat, p):
        print("skip"); sys.exit()

# Has technical indicators → inject
TECH_INDICATORS = [
    r"\b(bug|fix|error|import|function|class|module|file|test|build|deploy|commit|push|merge|install)\b",
    r"\b(코드|파일|함수|에러|버그|수정|빌드|배포|커밋|테스트|설치|구현|리팩토링)\b",
    r"[A-Z][a-z]+[A-Z]",  # camelCase
    r"[a-z]+_[a-z]+",     # snake_case
    r"\.\w{2,4}\b",       # file extensions (.py, .ts, .json)
    r"[/\\]\w+",          # file paths
]
for pat in TECH_INDICATORS:
    if re.search(pat, p, re.IGNORECASE):
        print("inject"); sys.exit()

# Default: inject if > 50 chars (probably a real question), skip if short
if len(p) > 50:
    print("inject")
else:
    print("skip")
' 2>/dev/null)

[ "$SHOULD_SKIP" = "skip" ] && exit 0

# 4) Need mindvault and a search index
MINDVAULT="{{MINDVAULT_PATH}}"
if [ ! -x "$MINDVAULT" ]; then
    command -v mindvault >/dev/null 2>&1 && MINDVAULT="mindvault" || exit 0
fi

QUERY_ARGS=""
if [ -f "$HOME/.mindvault/search_index.json" ]; then
    QUERY_ARGS="--global"
elif [ ! -f "mindvault-out/search_index.json" ]; then
    exit 0
fi

# 5) Timeout wrapper
TIMEOUT_CMD=""
if command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_CMD="gtimeout 10"
elif command -v timeout >/dev/null 2>&1; then
    TIMEOUT_CMD="timeout 10"
fi

# 6) Run query with strict budget (2000 tokens) and hard line limit.
# Budget 2000 = ~8KB of context, enough for 3 search results + key wiki excerpt.
RESULT=$($TIMEOUT_CMD "$MINDVAULT" query "$PROMPT" --budget 2000 $QUERY_ARGS 2>/dev/null | head -30)

# 7) Final size guard: truncate to 4000 chars max (~1000 tokens)
if [ ${#RESULT} -gt 4000 ]; then
    RESULT="${RESULT:0:4000}
... (truncated)"
fi

# 8) Emit wrapped context
if [ -n "$RESULT" ]; then
    echo "<mindvault-context>"
    echo "$RESULT"
    echo "</mindvault-context>"
fi

exit 0
'''
_GIT_HOOK_TEMPLATE = """
# MindVault auto-update
mindvault_update() {{
  MINDVAULT="{mindvault_path}"
  if [ -x "$MINDVAULT" ] || command -v mindvault &>/dev/null && MINDVAULT="mindvault"; then
    "$MINDVAULT" update --quiet &
  fi
}}
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

    git_hook_content = _GIT_HOOK_TEMPLATE.format(mindvault_path=_resolve_mindvault_path())

    # Check if already installed
    if hook_file.exists():
        existing = hook_file.read_text(encoding="utf-8")
        if _GIT_HOOK_MARKER in existing:
            return True  # Already installed
        # Append to existing hook
        content = existing.rstrip("\n") + "\n" + git_hook_content
    else:
        content = "#!/bin/sh\n" + git_hook_content

    hook_file.write_text(content, encoding="utf-8")
    hook_file.chmod(0o755)
    return True


def _resolve_mindvault_path() -> str:
    """Return the absolute path to the mindvault binary being used."""
    import shutil
    path = shutil.which("mindvault")
    if path:
        return str(Path(path).resolve())
    return "mindvault"


def install_prompt_hook() -> bool:
    """Install the UserPromptSubmit hook script and register in settings.json.

    This hook automatically runs mindvault query on every user prompt
    and injects results as context. Claude doesn't need to decide —
    the system forces it.

    The hook script embeds the absolute path to the mindvault binary
    resolved at install time, so it works even when installed inside a
    virtualenv or a non-standard location.

    Pre-0.4.2 installs wrote a broken v1 script that read a nonexistent
    env var and used `timeout` (missing on macOS). We detect old copies
    by checking for the MINDVAULT_HOOK_VERSION=2 marker and overwrite
    them in place. Otherwise identical content is a no-op write.

    Returns:
        True if installed successfully.
    """
    # 1. Write the hook script
    hooks_dir = Path.home() / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "mindvault-hook.sh"

    mindvault_bin = _resolve_mindvault_path()
    script = _PROMPT_HOOK_SCRIPT_TEMPLATE.replace("{{MINDVAULT_PATH}}", mindvault_bin)

    # Auto-upgrade: overwrite any prior install that does not carry the
    # current version marker OR if the embedded path has changed (e.g.
    # user reinstalled in a different venv).
    needs_write = True
    if hook_path.exists():
        try:
            existing = hook_path.read_text(encoding="utf-8")
            if (f"MINDVAULT_HOOK_VERSION={MINDVAULT_HOOK_VERSION}" in existing
                    and mindvault_bin in existing):
                needs_write = False  # same version, same path
        except (OSError, UnicodeDecodeError):
            pass

    if needs_write:
        hook_path.write_text(script, encoding="utf-8")
    hook_path.chmod(0o755)

    # 2. Register in settings.json
    settings_path = Path.home() / ".claude" / "settings.json"
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            settings = {}

    hooks = settings.setdefault("hooks", {})
    prompt_hooks = hooks.setdefault("UserPromptSubmit", [])

    # Check if already present
    already_installed = any(
        "mindvault-hook" in str(h.get("hooks", h.get("command", "")))
        for h in prompt_hooks
    )
    if not already_installed:
        prompt_hooks.append({
            "hooks": [{
                "type": "command",
                "command": str(hook_path),
            }]
        })

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


_LORE_HOOK_SCRIPT_TEMPLATE = '''#!/bin/bash
# MindVault Lore detection hook (PostToolUse)
# MINDVAULT_LORE_HOOK_VERSION=4
#
# Detects lore-worthy events from Bash tool output (stdout + stderr + command)
# and either auto-records, suggests, or shows a one-time onboarding notice.
#
# v4: Fixed NUL-byte corruption — $() strips NUL; now writes to temp file.

# Read stdin JSON (Claude Code PostToolUse spec)
INPUT=$(cat)
if [ -z "$INPUT" ]; then
    exit 0
fi

# Extract fields safely: Python outputs null-byte separated values to a temp
# file. Command substitution $() strips NUL bytes, so we redirect to a file
# and read from it instead.
_MV_TMP=$(mktemp)
trap 'rm -f "$_MV_TMP"' EXIT

printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    tool = d.get('tool_name', d.get('toolName', ''))
    stdout = d.get('stdout', d.get('output', ''))[:2000]
    stderr = d.get('stderr', '')[:1000]
    cmd = d.get('command', d.get('input', ''))[:500]
    sys.stdout.buffer.write(tool.encode() + b'\\0')
    sys.stdout.buffer.write(cmd.encode() + b'\\0')
    sys.stdout.buffer.write(stdout.encode() + b'\\0')
    sys.stdout.buffer.write(stderr.encode() + b'\\0')
except:
    sys.stdout.buffer.write(b'\\0\\0\\0\\0')
" > "$_MV_TMP" 2>/dev/null

# Parse null-byte separated values from file (preserves NUL unlike $())
{
    IFS= read -r -d '' TOOL_NAME
    IFS= read -r -d '' CMD
    IFS= read -r -d '' STDOUT
    IFS= read -r -d '' STDERR
} < "$_MV_TMP" 2>/dev/null || true

# Only process Bash tool calls
if [ "$TOOL_NAME" != "Bash" ]; then
    exit 0
fi

# Combine stdout + stderr + command for comprehensive pattern matching
COMBINED="$STDOUT $STDERR $CMD"
if [ -z "$COMBINED" ] || [ ${#COMBINED} -lt 5 ]; then
    exit 0
fi

LORE_CONFIG="$HOME/.mindvault/lore-config.json"

# ---- Pattern detection (all 5 patterns) ----
detect_pattern() {
    DETECTED=""
    LORE_TYPE=""
    SUGGESTED_TITLE=""
    CONTEXT_SNIPPET=""

    # 1. rollback — git revert/reset
    if echo "$COMBINED" | grep -qiE "Revert|revert.*commit|reset.*hard|HEAD is now at"; then
        DETECTED="rollback"
        LORE_TYPE="rollback"
        SUGGESTED_TITLE="Code rollback detected"
        CONTEXT_SNIPPET=$(echo "$STDOUT" | grep -iE "Revert|reset|HEAD" | head -3)
    # 2. test_failure — test failures
    elif echo "$COMBINED" | grep -qiE "FAILED|ERRORS|tests? failed|AssertionError|pytest.*failed|jest.*fail|error TS"; then
        DETECTED="test_failure"
        LORE_TYPE="failure"
        SUGGESTED_TITLE="Test failure detected"
        CONTEXT_SNIPPET=$(echo "$COMBINED" | grep -iE "FAILED|Error|assert" | head -3)
    # 3. dependency — package changes
    elif echo "$COMBINED" | grep -qiE "npm install|pip install|added [0-9]+ package|Successfully installed|removing.*package"; then
        DETECTED="dependency"
        LORE_TYPE="decision"
        SUGGESTED_TITLE="Dependency change"
        CONTEXT_SNIPPET=$(echo "$COMBINED" | grep -iE "install|added|remov" | head -3)
    # 4. architecture — major file restructure
    elif echo "$CMD" | grep -qiE "mv .*src/|mkdir -p .*src/|rename|restructur"; then
        DETECTED="architecture"
        LORE_TYPE="decision"
        SUGGESTED_TITLE="Architecture change detected"
        CONTEXT_SNIPPET="$CMD"
    # 5. build_fix — build failure then fix
    elif echo "$COMBINED" | grep -qiE "build failed|compilation error|Build error|error\\[E|error:.*cannot find"; then
        DETECTED="build_fix"
        LORE_TYPE="failure"
        SUGGESTED_TITLE="Build failure detected"
        CONTEXT_SNIPPET=$(echo "$COMBINED" | grep -iE "error|failed|Build" | head -3)
    fi
}

detect_pattern

if [ -z "$DETECTED" ]; then
    exit 0
fi

# ---- Configured mode: use user settings ----
if [ -f "$LORE_CONFIG" ]; then
    ACTION=$(python3 -c "
import json
try:
    with open('"'"'$LORE_CONFIG'"'"') as f:
        cfg = json.load(f)
    print(cfg.get('"'"'patterns'"'"', {}).get('"'"'$DETECTED'"'"', '"'"'ask'"'"'))
except: print('"'"'ask'"'"')
" 2>/dev/null)

    if [ "$ACTION" = "ignore" ]; then
        exit 0
    fi

    MINDVAULT="{{MINDVAULT_PATH}}"
    if [ ! -x "$MINDVAULT" ]; then
        command -v mindvault >/dev/null 2>&1 && MINDVAULT="mindvault" || exit 0
    fi

    if [ "$ACTION" = "auto" ]; then
        # Auto-record with actual context from the output
        SAFE_CONTEXT=$(echo "$CONTEXT_SNIPPET" | head -3 | tr '"' "'" | tr '\n' ' ')
        SAFE_CMD=$(echo "$CMD" | head -1 | tr '"' "'")
        $MINDVAULT lore record \
            --title "$SUGGESTED_TITLE" \
            --type "$LORE_TYPE" \
            --context "Command: $SAFE_CMD | Output: $SAFE_CONTEXT" \
            --outcome "Auto-recorded. Review and add resolution details." 2>/dev/null
        echo "<lore-auto-recorded>"
        echo "Lore auto-recorded: $SUGGESTED_TITLE (type: $LORE_TYPE)"
        echo "Context: $SAFE_CONTEXT"
        echo "Review with: mindvault lore list"
        echo "</lore-auto-recorded>"
    else
        # Ask mode — suggest to AI with actual context
        echo "<lore-suggestion>"
        echo "Detected: $SUGGESTED_TITLE"
        echo "Context: $CONTEXT_SNIPPET"
        echo "Suggested command: mindvault lore record --title \"...\" --type $LORE_TYPE --context \"...\" --outcome \"...\""
        echo "Ask the user if they want to record this decision/failure in Lore."
        echo "</lore-suggestion>"
    fi

    exit 0
fi

# ---- Not configured: lazy onboarding (one-time notice) ----
# Only write .lore-noticed AFTER user runs setup, not here
NOTICE_FLAG="$HOME/.mindvault/.lore-noticed"
if [ -f "$NOTICE_FLAG" ]; then
    exit 0
fi

# Show notice but do NOT write the flag yet — user must opt in via setup
echo "<lore-notice>"
echo "MindVault detected a significant event: $SUGGESTED_TITLE"
echo "MindVault Lore can automatically track decisions, failures, and learnings"
echo "so your AI remembers WHY things changed — not just WHAT changed."
echo ""
echo "Currently: manual only (mindvault lore record --title '...')"
echo "Setup automation: mindvault lore setup"
echo ""
echo "Tell the user about this feature and ask if they want to set it up now."
echo "If the user declines, run: touch $NOTICE_FLAG"
echo "</lore-notice>"

exit 0
'''


def install_lore_hook() -> bool:
    """Install the PostToolUse lore detection hook.

    Detects lore-worthy events (rollbacks, test failures) from Bash
    tool output and either auto-records, suggests, or ignores based
    on user configuration. Shows a one-time notice on first detection
    if lore is not yet configured (lazy onboarding).

    Returns:
        True if installed successfully.
    """
    hooks_dir = Path.home() / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "mindvault-lore-hook.sh"

    mindvault_bin = _resolve_mindvault_path()
    script = _LORE_HOOK_SCRIPT_TEMPLATE.replace("{{MINDVAULT_PATH}}", mindvault_bin)

    needs_write = True
    if hook_path.exists():
        try:
            existing = hook_path.read_text(encoding="utf-8")
            if "MINDVAULT_LORE_HOOK_VERSION=4" in existing and mindvault_bin in existing:
                needs_write = False
        except (OSError, UnicodeDecodeError):
            pass

    if needs_write:
        hook_path.write_text(script, encoding="utf-8")
    hook_path.chmod(0o755)

    # Register in settings.json
    settings_path = Path.home() / ".claude" / "settings.json"
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            settings = {}

    hooks = settings.setdefault("hooks", {})
    post_tool_hooks = hooks.setdefault("PostToolUse", [])

    already_installed = any(
        "mindvault-lore-hook" in str(h.get("hooks", h.get("command", "")))
        for h in post_tool_hooks
    )
    if not already_installed:
        post_tool_hooks.append({
            "matcher": "Bash",
            "hooks": [{
                "type": "command",
                "command": str(hook_path),
            }],
        })

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


MINDVAULT_RULES_HOOK_VERSION = 3

_RULES_HOOK_SCRIPT_TEMPLATE = '''#!/bin/bash
# MindVault Rules Engine hook (PostToolUse)
# MINDVAULT_RULES_HOOK_VERSION=3
#
# Checks tool input/output against project rules and injects
# <rules-warning> or <rules-block> tags when violations are found.
#
# v3: Fixed NUL-byte corruption (temp file) + deduplicate scope:both matches.

# Read stdin JSON (Claude Code PostToolUse spec)
INPUT=$(cat)
if [ -z "$INPUT" ]; then
    exit 0
fi

# Extract fields safely: write NUL-separated values to temp file
# ($() strips NUL bytes, so we redirect to a file instead).
_MV_TMP=$(mktemp)
trap 'rm -f "$_MV_TMP"' EXIT

printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    tool = d.get('tool_name', d.get('toolName', ''))
    stdout = d.get('stdout', d.get('output', ''))[:2000]
    stderr = d.get('stderr', '')[:1000]
    cmd = d.get('command', d.get('input', ''))[:500]
    sys.stdout.buffer.write(tool.encode() + b'\\0')
    sys.stdout.buffer.write(cmd.encode() + b'\\0')
    sys.stdout.buffer.write(stdout.encode() + b'\\0')
    sys.stdout.buffer.write(stderr.encode() + b'\\0')
except:
    sys.stdout.buffer.write(b'\\0\\0\\0\\0')
" > "$_MV_TMP" 2>/dev/null

# Parse null-byte separated values from file (preserves NUL unlike $())
{
    IFS= read -r -d '' TOOL_NAME
    IFS= read -r -d '' CMD
    IFS= read -r -d '' STDOUT
    IFS= read -r -d '' STDERR
} < "$_MV_TMP" 2>/dev/null || true

if [ -z "$CMD" ] && [ -z "$STDOUT" ] && [ -z "$STDERR" ]; then
    exit 0
fi

MINDVAULT="{{MINDVAULT_PATH}}"
if [ ! -x "$MINDVAULT" ]; then
    command -v mindvault >/dev/null 2>&1 && MINDVAULT="mindvault" || exit 0
fi

# Run rules check with separate contexts for proper scope filtering.
# Command check: only matches rules with scope "command" or "both".
# Output check: only matches rules with scope "output" or "both".
OUTPUT_TEXT="${STDOUT}
---MINDVAULT_SEPARATOR---
${STDERR}"

RESULT=""
if [ -n "$CMD" ]; then
    R1=$($MINDVAULT rules check --context command "$CMD" 2>/dev/null)
    if [ -n "$R1" ] && echo "$R1" | grep -qE "<rules-(warning|block)>"; then
        RESULT="$R1"
    fi
fi

if [ -n "$STDOUT" ] || [ -n "$STDERR" ]; then
    R2=$($MINDVAULT rules check --context output "$OUTPUT_TEXT" 2>/dev/null)
    if [ -n "$R2" ] && echo "$R2" | grep -qE "<rules-(warning|block)>"; then
        if [ -n "$RESULT" ]; then
            RESULT="${RESULT}
${R2}"
        else
            RESULT="$R2"
        fi
    fi
fi

# Deduplicate rules matched in both command and output contexts (scope:both)
if [ -n "$RESULT" ]; then
    printf '%s' "$RESULT" | python3 -c "
import sys, re
text = sys.stdin.read()
blocks = re.findall(r'(<rules-(?:warning|block)>.*?</rules-(?:warning|block)>)', text, re.DOTALL)
seen = set()
for block in blocks:
    m = re.search(r'Rule: (.+)', block)
    if m:
        rid = m.group(1).strip()
        if rid not in seen:
            seen.add(rid)
            print(block)
    else:
        print(block)
" 2>/dev/null
fi

exit 0
'''


def install_rules_hook() -> bool:
    """Install the PostToolUse rules engine hook.

    Checks tool input/output against project rules and injects
    warning/block tags when violations are detected.

    Returns:
        True if installed successfully.
    """
    hooks_dir = Path.home() / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "mindvault-rules-hook.sh"

    mindvault_bin = _resolve_mindvault_path()
    script = _RULES_HOOK_SCRIPT_TEMPLATE.replace("{{MINDVAULT_PATH}}", mindvault_bin)

    needs_write = True
    if hook_path.exists():
        try:
            existing = hook_path.read_text(encoding="utf-8")
            if (f"MINDVAULT_RULES_HOOK_VERSION={MINDVAULT_RULES_HOOK_VERSION}" in existing
                    and mindvault_bin in existing):
                needs_write = False
        except (OSError, UnicodeDecodeError):
            pass

    if needs_write:
        hook_path.write_text(script, encoding="utf-8")
    hook_path.chmod(0o755)

    # Register in settings.json
    settings_path = Path.home() / ".claude" / "settings.json"
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            settings = {}

    hooks = settings.setdefault("hooks", {})
    post_tool_hooks = hooks.setdefault("PostToolUse", [])

    already_installed = any(
        "mindvault-rules-hook" in str(h.get("hooks", h.get("command", "")))
        for h in post_tool_hooks
    )
    if not already_installed:
        post_tool_hooks.append({
            "matcher": "Bash|Edit|Write",
            "hooks": [{
                "type": "command",
                "command": str(hook_path),
            }],
        })

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


def check_prompt_hook() -> list[dict]:
    """Diagnose the UserPromptSubmit hook installation end-to-end.

    Returns a list of ``{name, ok, detail}`` dicts covering:
        1. Hook file exists on disk
        2. Hook carries the current MINDVAULT_HOOK_VERSION marker
        3. Hook is executable
        4. Hook is registered in Claude Code settings.json
        5. `mindvault` CLI is on PATH
        6. A global or local search index is present
        7. Feeding a sample JSON prompt to the hook produces non-empty
           wrapped output (`<mindvault-context>`). This is the check
           that would have caught the v1 silent-failure bug immediately.

    Used by ``mindvault doctor`` to give users an actionable diagnosis
    without needing to trace through shell scripts by hand.
    """
    import subprocess

    results: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        results.append({"name": name, "ok": ok, "detail": detail})

    # 1. Hook file exists
    hook_path = Path.home() / ".claude" / "hooks" / "mindvault-hook.sh"
    if not hook_path.exists():
        add("hook file", False, f"missing: {hook_path}")
        return results
    add("hook file", True, str(hook_path))

    # 2. Version marker
    try:
        hook_content = hook_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        add("hook readable", False, f"cannot read: {e}")
        return results

    marker = f"MINDVAULT_HOOK_VERSION={MINDVAULT_HOOK_VERSION}"
    if marker in hook_content:
        add("hook version", True, f"v{MINDVAULT_HOOK_VERSION}")
    else:
        add(
            "hook version",
            False,
            f"outdated — run `mindvault install` to upgrade to v{MINDVAULT_HOOK_VERSION}",
        )

    # 3. Executable
    import os as _os
    if _os.access(hook_path, _os.X_OK):
        add("hook executable", True, "chmod +x")
    else:
        add("hook executable", False, "run `chmod +x ~/.claude/hooks/mindvault-hook.sh`")

    # 4. Registered in settings.json
    settings_path = Path.home() / ".claude" / "settings.json"
    registered = False
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            prompt_hooks = (
                settings.get("hooks", {}).get("UserPromptSubmit", [])
            )
            for entry in prompt_hooks:
                hooks_list = entry.get("hooks", [])
                for h in hooks_list:
                    if "mindvault-hook" in str(h.get("command", "")):
                        registered = True
                        break
        except (json.JSONDecodeError, OSError):
            pass
    add(
        "hook registered",
        registered,
        "UserPromptSubmit in settings.json" if registered
        else "missing — run `mindvault install`",
    )

    # 5. mindvault on PATH
    try:
        which = subprocess.run(
            ["which", "mindvault"], capture_output=True, text=True, timeout=5,
        )
        cli_ok = which.returncode == 0
        add(
            "mindvault CLI",
            cli_ok,
            which.stdout.strip() if cli_ok else "not found on PATH",
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        add("mindvault CLI", False, f"check failed: {e}")
        return results

    # 6. Search index present
    global_index = Path.home() / ".mindvault" / "search_index.json"
    local_index = Path("mindvault-out") / "search_index.json"
    if global_index.exists():
        add("search index", True, f"global: {global_index}")
    elif local_index.exists():
        add("search index", True, f"local: {local_index}")
    else:
        add(
            "search index",
            False,
            "no global or local index — run `mindvault global <root>` or `mindvault install`",
        )

    # 7. End-to-end smoke test: feed stdin JSON, expect <mindvault-context>
    sample = '{"sessionId":"doctor","prompt":"mindvault doctor smoke test query","cwd":"/tmp"}'
    try:
        proc = subprocess.run(
            ["bash", str(hook_path)],
            input=sample,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = proc.stdout or ""
        if "<mindvault-context>" in out and len(out.strip()) > len("<mindvault-context></mindvault-context>"):
            add("end-to-end", True, f"{len(out)} bytes injected")
        else:
            add(
                "end-to-end",
                False,
                "hook ran but emitted no context — check index and mindvault query output",
            )
    except subprocess.TimeoutExpired:
        add("end-to-end", False, "hook timed out after 30s")
    except OSError as e:
        add("end-to-end", False, f"could not execute: {e}")

    return results


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
