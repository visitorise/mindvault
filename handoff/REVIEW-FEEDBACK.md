# Review Feedback — Step 13
Date: 2026-04-14
Ready for Builder: NO

## Must Fix

- [rules.py:178 + hooks.py:503 + cli.py:558] — **Scope filtering is effectively dead code.** The hook script combines command+output into one string and calls `mindvault rules check "$COMBINED"` with no context argument. `cmd_rules` also calls `check_rules(args.text, rules)` with no context. Both default to `context="both"`. But `check_rules` line 178 skips any rule where `scope != "both" and scope != context`. Since context is always "both", rules with `scope: "command"` or `scope: "output"` will never match through the hook or CLI. The spec defines scope as a first-class schema field and the test at test_rules.py:277-279 even validates that command-scoped rules don't match `context="both"`, confirming the behavior is intentional in the test but broken in the integration. **Fix**: Either (a) the hook should make two separate `check_rules` calls — one with `context="command"` for the command text and one with `context="output"` for stdout+stderr, or (b) the CLI `check` subcommand needs a `--context` argument so the hook can pass it. The current combined-text approach with default context means scope is useless.

- [hooks.py:474] — **`eval` on tool output is a command injection vector.** The rules hook uses `eval $(echo "$INPUT" | python3 -c "..." )` to extract variables. Python `repr()` produces Python string literals, not POSIX-safe shell assignments. A tool output containing carefully crafted quotes (e.g. stdout with `'); malicious_command; echo ('`) could break out of the quoting when `eval`'d. This is inherited from the lore hook (same pattern at line 248) but now applied to a broader tool matcher (`Bash|Edit|Write` vs lore's `Bash` only), expanding the attack surface. **Fix**: Replace `eval` with a safer extraction pattern. Options: (a) write extracted values to a temp file and `source` it, (b) use `read` with a delimiter from python output, or (c) rewrite the hook in Python entirely (eliminate bash eval).

## Should Fix

- [rules.py:230-234] — **`add_rule` does not persist `scope` or `enabled` fields.** The new rule dict written by `add_rule` only includes `id`, `trigger`, `type`, `message`, and optionally `lore_ref`. The `scope` and `enabled` fields are absent from the written YAML. They get defaults when re-read through `_normalize_rule`, but a user cannot set `scope` or `enabled` via `add_rule()` or the CLI. **Fix**: Add `scope` and `enabled` parameters to `add_rule()` and persist them. Also add `--scope` and `--enabled` CLI arguments in `cli.py`.

- [cli.py:554] — **`mindvault rules check` requires positional `text` argument but argparse allows `nargs="?"` with `default=None`.** If a user runs `mindvault rules check` without text, `args.text` is None and the code prints an error and exits. This works, but the UX is poor — argparse won't show that `text` is required for `check`. The argument also shows as a positional for `add`, `remove`, and `list` where it makes no sense. **Fix**: Move the `text` argument handling into the `check` action logic, or use a subparser per action.

- [test_rules.py:200-214] — **Lore suggestion test (scenario 7) doesn't verify trigger content.** The test asserts `<lore-rule-suggestion>` and `mindvault rules add` appear in stdout but does not verify the trigger pattern contains keywords from the title ("Redis", "Cache", "Rollback"). If `_suggest_rule` generated an empty or wrong trigger, the test would still pass. **Fix**: Add assertion that at least one of `redis`, `cache`, or `rollback` appears in the captured output's trigger pattern.

- [hooks.py:492] — **Hook combines command+output into a single string with space separator.** `COMBINED="$CMD $STDOUT $STDERR"` could create false-positive regex matches where the trigger pattern spans the boundary between command and output. For example, a rule with trigger `foo bar` could match if the command ends with `foo` and stdout starts with `bar`. Minor but worth documenting as a known limitation.

## Escalate to Architect

- **Scope field has no working integration path.** The spec defines `scope` as a schema field (`"command" | "output" | "both"`) but the hook concatenates command+output into one string and checks it as a whole. Fixing this (Must Fix #1) requires either two separate `mindvault rules check` invocations per hook call (doubling latency vs the <1s constraint) or a richer CLI interface. Arch should decide whether scope is worth the added complexity in v1 or should be deferred to v2.

## Cleared

- **rules.py core logic**: 5 public functions implemented per spec. YAML+JSON fallback works correctly. Invalid regex handling at both load time (`_normalize_rule`) and runtime (`check_rules`). Project-over-global merge priority correct. `enabled` field filtering correct. Atomic writes via tempfile+os.replace.
- **pyproject.toml**: `pyyaml>=6.0` added to dependencies at line 32.
- **__init__.py**: All 5 functions (`load_rules`, `check_rules`, `add_rule`, `remove_rule`, `list_rules`) present in both lazy imports (lines 50-54) and `__all__` (lines 109-113).
- **cli.py**: All 4 subcommands (add/remove/list/check) registered and dispatched. `cmd_install` includes rules hook installation at step 7 (line 84-89). Command dispatch dict includes `"rules": cmd_rules` (line 748).
- **lore.py**: `_suggest_rule` outputs correct `<lore-rule-suggestion>` tag format per ARCHITECT-BRIEF 13.4. Trigger auto-generated from title keywords (3+ chars, up to 3). Called from `record()` at line 131.
- **hooks.py**: Rules hook registered for `Bash|Edit|Write` matcher. Version marker `MINDVAULT_RULES_HOOK_VERSION=1` present. Auto-upgrade logic follows existing lore hook pattern.
- **test_rules.py**: All 10 architect-specified scenarios have coverage across 24 tests. Tests exercise actual behavior (regex matching, file I/O, merge priority), not just existence. Good edge cases: invalid regex, disabled rules, empty files, nonexistent files.
- **format_rule_output**: Correctly renders `<rules-warning>` and `<rules-block>` tags with optional lore reference.
