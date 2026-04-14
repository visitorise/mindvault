# REVIEW-REQUEST — Step 13: Rules Engine (Post-Review Fix)

**Builder**: Bob
**Date**: 2026-04-14
**Step**: 13 — Rules Engine (Phase 2 harness engineering)
**Ready for Review**: YES

## Review Fixes Applied (6/6)

### Must Fix

1. **Scope filtering dead code** (rules.py + hooks.py + cli.py)
   - `check_rules()` line 178: flipped logic — `context="both"` now matches ALL rules regardless of their scope. Only filters when context is specifically "command" or "output".
   - Hook script (v2): makes TWO separate `mindvault rules check` calls — `--context command "$CMD"` and `--context output "$OUTPUT_TEXT"`. Combines results.
   - CLI: added `--context` argument to `rules check` (choices: command, output, both; default: both).
   - Test `test_command_scope_matches_command_and_both_context`: fixed assertion — command-scoped rules now correctly match `context="both"`.

2. **eval command injection in hook** (hooks.py)
   - Rules hook (v2): replaced `eval $(...)` with null-byte separated Python output + `read -d ''` parsing. No shell interpretation of user data.
   - Lore hook (v3): same fix applied. Version bumped from 2 to 3.
   - Updated lore hook version test in test_lore.py to match v3.

### Should Fix

3. **add_rule doesn't persist scope/enabled** (rules.py + cli.py)
   - `add_rule()` now accepts `scope="both"` and `enabled=True` parameters.
   - Both fields are persisted in the YAML output.
   - CLI: added `--scope` (choices: command, output, both) and `--enabled`/`--disabled` arguments.

4. **argparse text argument exposed to all rules subcommands** (cli.py)
   - Moved `text` positional to the end of rules subparser args with explicit help "(only for check action)".
   - Named args (--id, --trigger, etc.) now appear before the optional positional, so argparse help is clearer.

5. **Lore suggestion test doesn't verify trigger content** (test_rules.py)
   - Added assertion: at least one of "redis", "cache", "rollback" must appear in the captured output's trigger pattern.

6. **Hook command+output boundary false positives** (hooks.py)
   - Rules hook now uses `\n---MINDVAULT_SEPARATOR---\n` between stdout and stderr in the output text.
   - Command and output are checked in separate `mindvault rules check` calls (Fix 1), which inherently eliminates cross-boundary false positives.

## Files Modified

| File | Lines Changed | What |
|---|---|---|
| `src/mindvault/rules.py` | 178, 192-244 | Fix 1 (scope logic), Fix 3 (add_rule params) |
| `src/mindvault/hooks.py` | 234-392, 458-510 | Fix 2 (eval removal), Fix 6 (separator) |
| `src/mindvault/cli.py` | 514-527, 553-563, 717-728 | Fix 1 (--context), Fix 3 (--scope/--enabled), Fix 4 (text arg) |
| `tests/test_rules.py` | 200-214, 271-279 | Fix 1 (scope test), Fix 5 (trigger assertion) |
| `tests/test_lore.py` | 256-258 | Lore hook version test updated to v3 |

## Verification

```
$ python3 -m pytest tests/ -v
184 passed in 311.25s
```

All 184 tests pass. Zero regressions.
