# REVIEW-REQUEST — Step 5: Integration Layer + CLI

**Builder**: Bob
**Date**: 2026-04-10
**Step**: 5 — Integration Layer + CLI

## Files Modified

All files in `src/mindvault/`:

### 1. pipeline.py — Full implementation from stub
- `run(source_dir, output_dir)` — Calls `compile()` then `index_markdown()` on wiki dir. Returns combined stats with `index_docs` count.
- `run_incremental(source_dir, output_dir)` — Detects dirty files via `cache.get_dirty_files`, extracts AST for dirty only, merges into existing `graph.json`, re-clusters, re-generates wiki + index. Falls back to full `run()` if no `graph.json` exists.

### 2. query.py — Full implementation from stub
- `query(question, output_dir, mode, budget)` — 3-layer pipeline:
  1. BM25 search (0 tokens) → top 3 wiki docs
  2. Graph traversal (BFS depth 2 / DFS depth 4) → matched nodes + neighbors
  3. Wiki page reading → budget-limited context text
- Budget enforcement: reserves tokens for graph edge text, allocates rest to wiki. 10-token margin.
- Helpers: `_keyword_match`, `_bfs_traverse`, `_dfs_traverse`

### 3. hooks.py — Full implementation from stub
- `install_git_hook` — Appends to `.git/hooks/post-commit`, preserves existing content, skips if already installed.
- `install_claude_hooks` — Adds PostToolUse + Stop hooks to `settings.json`. Appends to arrays. **Opt-in only** (not called by install).
- `mark_dirty` — Stores dirty file paths in `.mindvault_dirty.json` (deduped JSON array).
- `flush` — Reads dirty list, runs `run_incremental`, clears dirty list.

### 4. watch.py — Full implementation from stub
- `watch(source_dir, output_dir, debounce)` — Polling-based mtime detection (no watchdog).
- Code files → `run_incremental` immediately. Doc/image files → `mark_dirty` only.
- Handles `KeyboardInterrupt` for clean shutdown.

### 5. cli.py — Extended (not rewritten)
- Existing argparse structure preserved. Added 3 new subcommands: `update`, `mark-dirty`, `flush`.
- All 9 subcommands now have real implementations routed via command handler dict.
- `cmd_query`: 3-section formatted output (Search/Graph/Wiki).
- `cmd_status`: loads graph.json, shows counts + last updated timestamp.
- `cmd_lint`: shows broken links, orphan pages, isolated nodes, ambiguous edges.

## Verification Results

All 6 test scenarios from ARCHITECT-BRIEF section 5.6:

| # | Test | Result | Detail |
|---|------|--------|--------|
| 1 | `pipeline.run` — nodes > 0, index_docs > 0 | PASS | 91 nodes, 17 index_docs |
| 2 | `query("detect file")` — tokens_used < 2000 | PASS | 1991 tokens |
| 3 | `mindvault status` | PASS | 91 nodes, 146 edges, 10 communities |
| 4 | `mindvault query "detect file"` | PASS | 3-layer formatted output |
| 5 | `mindvault lint` | PASS | 17 pages, 358 broken wikilinks, 0 ambiguous |
| 6 | `mark_dirty + flush` | PASS | 1 file processed, incremental ran |

## Review Focus Areas

1. **Budget margin (query.py)**: Uses `budget - graph_tokens - 10` margin. Test result: 1991/2000. Tight but passing. May need a larger margin for queries that match many graph edges.

2. **run_incremental merge logic (pipeline.py)**: Removes all edges with `source_file` matching dirty files and adds new ones. This could miss edges from _other_ files pointing to entities in dirty files. The brief doesn't specify cross-file edge preservation.

3. **flush source_dir inference (hooks.py)**: `flush()` infers `source_dir` as `output_dir.parent`. Works for standard `project/mindvault-out/` layout. Would break for custom output paths — but the brief doesn't mention custom paths for flush.

4. **watch.py full scan cost**: Each poll does `os.walk` + `getmtime` over the whole source tree. Acceptable for typical projects but could be slow for monorepos with 100k+ files.

5. **Broken wikilinks (358)**: These are node-level `[[slug]]` refs in community wiki pages pointing to individual nodes that don't have dedicated wiki pages. Same known gap from Step 3. Not a regression.

## Notes for Richard

- All 5 files were stubs (`raise NotImplementedError`). Now fully functional.
- No new dependencies added. watch.py uses stdlib `time.sleep` + `os.walk` as specified.
- Claude Code hooks install is strictly opt-in per brief section 5.3 constraint.
- `cli.py` argparse structure preserved — existing `--version`, subparser dest, help text all unchanged.
