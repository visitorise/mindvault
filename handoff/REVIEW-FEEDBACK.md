# REVIEW-FEEDBACK — Step 5: Integration Layer + CLI

**Reviewer**: Richard
**Date**: 2026-04-10
**Verdict**: PASS (3 advisory notes, 1 minor fix recommended)

---

## Checklist Results

| # | Check | Result |
|---|-------|--------|
| 1 | `pipeline.run()` calls compile + index_markdown, returns index_docs | PASS |
| 2 | `query()` implements 3 layers (search -> graph -> wiki) | PASS |
| 3 | Budget enforced (tokens_used < budget) | PASS (1991/2000) |
| 4 | `install_git_hook` preserves existing post-commit content | PASS |
| 5 | `install_claude_hooks` opt-in only | PASS -- not called by cmd_install |
| 6 | CLI has all 9 subcommands | PASS -- install, query, ingest, lint, status, watch, update, mark-dirty, flush |
| 7 | `mindvault status` works with mindvault-out/ | PASS |
| 8 | `mindvault query` shows formatted 3-layer output | PASS |

## Test Results (Section 5.6)

| # | Test | Result | Detail |
|---|------|--------|--------|
| 1 | pipeline.run -- nodes > 0, index_docs > 0 | PASS | 91 nodes, 17 index_docs |
| 2 | query("detect file") -- tokens_used < 2000 | PASS | 1991 tokens |
| 3 | mindvault status | PASS | 91 nodes, 146 edges, 10 communities |
| 4 | mindvault query "detect file" | PASS | 3-section output (Search/Graph/Wiki) |
| 5 | mindvault lint | PASS | 17 pages, 358 broken wikilinks, 0 ambiguous |
| 6 | mark_dirty + flush | PASS | files_processed: 1, changed: 0 (correct -- file hash unchanged) |

---

## Advisory Notes (non-blocking)

### A1. Budget margin is tight -- 1991/2000 (9 tokens spare)

`query.py:164` uses `budget - graph_tokens - 10` margin. With 4 matched nodes and 38 graph edges, the result lands at 1991. A query matching more graph edges could exceed budget. The `wiki_token_budget` floor of 100 tokens (line 165-166) provides a safety net -- wiki content gets cut, but `tokens_used` still counts graph edge text which is not budget-capped.

**Risk**: Low. The budget is approximate (`len(text) // 4`) and serves as a soft limit. No hard failure occurs if exceeded.

**Suggestion for later**: Cap `tokens_used` by truncating graph edge text contribution, or increase margin from 10 to 50.

### A2. `flush()` dirty list vs `run_incremental()` cache are independent systems

`mark_dirty()` writes to `.mindvault_dirty.json` (JSON file path list). `flush()` calls `run_incremental()` which internally uses `cache.get_dirty_files()` (SHA256 hash comparison). The dirty JSON list only serves as a "should we bother calling run_incremental?" gate -- the actual change detection is hash-based.

This means:
- If a file is marked dirty but content hasn't changed -> `run_incremental` returns `{changed: 0}` (correct)
- If a file changes but is never `mark_dirty`'d -> `flush` won't trigger, but `watch` or manual `update` will catch it (correct)

The two-system design is coherent but could confuse future contributors. No action needed now.

### A3. CLI `--mode hybrid` accepted but not implemented

`cli.py:273` includes `"hybrid"` in `choices=["bfs", "dfs", "hybrid"]`, but `query.py` only has `if mode == "dfs" ... else` -- so `hybrid` silently falls back to BFS. Either remove `hybrid` from choices or implement it.

---

## Minor Fix Recommended

### F1. `cmd_lint` default path logic

`cli.py:135`: `if args.path != ".mindvault"` -- the default is `".mindvault"` (line 285) which then maps to `Path("mindvault-out")`. This works but the string `.mindvault` as a sentinel is fragile and confusing. Consider changing the default to `"mindvault-out"` directly and dropping the conditional.

---

## Code Quality Notes

- All lazy imports (inside functions) are correct -- avoids circular import issues.
- `watch.py` properly filters `SKIP_DIRS` during os.walk (line 20).
- `hooks.py` idempotency is solid -- both git hook and claude hooks check-before-add.
- `run_incremental` fallback to full `run()` when graph.json doesn't exist (line 69) is the right call.
- `cmd_status` gracefully handles missing mindvault-out/ with informative message.
- Broken wikilinks (358) are a known gap from Step 3 -- node-level `[[slug]]` refs in community pages pointing to non-existent individual wiki pages. Not a regression.

---

## Cleared

1. **pipeline.py** -- `run()` calls `compile()` then `index_markdown()` on wiki dir, returns combined stats including `index_docs`. `run_incremental()` loads existing graph, merges dirty-file extractions, re-clusters, re-generates wiki + index, updates cache. Falls back to full `run()` when no graph.json exists.

2. **query.py** -- 3-layer pipeline: BM25 search (0 tokens) -> graph traversal (BFS depth 2 / DFS depth 4) -> wiki page reading (budget-limited). Budget enforcement via char-to-token approximation with 10-token margin. Helpers `_keyword_match`, `_bfs_traverse`, `_dfs_traverse` are correct.

3. **hooks.py** -- `install_git_hook` preserves existing content, uses marker-based idempotency, sets 755. `install_claude_hooks` is opt-in only, appends to existing hook arrays. `mark_dirty` deduplicates via list check. `flush` triggers `run_incremental` and clears dirty list.

4. **watch.py** -- Polling-based mtime detection with SKIP_DIRS filtering. Code files trigger immediate `run_incremental`, doc files trigger `mark_dirty` only. Handles KeyboardInterrupt cleanly. No external dependencies.

5. **cli.py** -- All 9 subcommands wired via command handler dict. Formatted 3-section query output. Status shows graph/wiki/index stats with timestamp. Lint shows broken links, orphans, isolated nodes, ambiguous edges. argparse structure preserved from prior steps.

6. **All 6 tests PASS. All 8 acceptance criteria met.**

---

**Step 5 is approved. All acceptance criteria met. Ship it.**
