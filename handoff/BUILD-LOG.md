# BUILD-LOG — MindVault

## Project Summary
MindVault — 토큰 절약 + 세션 연속성을 위한 3-Layer 지식 관리 도구.
PyPI 독립 패키지. `pip install mindvault && mindvault install`

## Steps

### Step 1 — Project Skeleton + Module Interfaces ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files**: 22 files created (pyproject.toml, README.md, 18 Python modules, SKILL.md, REVIEW-REQUEST.md)
- **Verification**:
  - `pip install -e .` — PASS
  - `mindvault --version` → `mindvault 0.1.0` — PASS
  - All module imports — PASS
  - SKILL.md exists — PASS
- **Notes**: cli.py has working argparse (not stub). All other modules are stubs with NotImplementedError.

### Step 2 — Graph Layer Implementation ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files modified**: 6 (detect.py, cache.py, extract.py, build.py, cluster.py, analyze.py)
- **Verification** (all 5 tests PASS):
  - Test 1: `detect` — 24 files, 3636 words, 19 code files — PASS
  - Test 2: `extract_ast` — 66 nodes, 281 edges — PASS
  - Test 3: `build_graph` — 66 nodes, 79 edges (dangling edges filtered) — PASS
  - Test 4: `cluster + analyze` — 13 communities, 5 god nodes, 5 surprises — PASS
  - Test 5: `cache` — dirty detection + update — PASS
- **Key decisions**:
  - `nx.Graph` → `nx.DiGraph` (as specified)
  - tree-sitter 0.25.2 API: `Parser(lang)` constructor, no `.set_language()`
  - `greedy_modularity_communities` on undirected copy for clustering
  - Node IDs: `{filestem}_{entityname}` with sanitization (lowercase, special→underscore)
  - Call edges extracted recursively from function bodies, cross-file resolution deferred
  - `extract_semantic` remains NotImplementedError stub

### Step 3 — Wiki Layer + Output Generation ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files modified**: 5 (wiki.py, compile.py, report.py, export.py, lint.py)
- **Verification** (all 4 tests PASS):
  - Test 1: `compile` — 70 nodes, 95 edges, 11 communities, 12 wiki pages, 5637 words — PASS
  - Test 2: output files — graph.json, GRAPH_REPORT.md, graph.html, wiki/INDEX.md all exist, 12 wiki pages — PASS
  - Test 3: lint — 12 pages, 193 broken wikilinks (node-level refs to non-existent pages, expected), 0 orphans, 0 ambiguous edges — PASS
  - Test 4: report sections — Overview, God Nodes, Communities all present — PASS
- **Key decisions**:
  - Community labels auto-generated from top-2 nodes by degree (no LLM)
  - Wiki context uses template: "이 커뮤니티는 {top}를 중심으로 {relation} 관계로 연결되어 있다."
  - vis.js HTML: CDN from unpkg, community colors, degree-based node sizing, search, community filter checkboxes
  - `node_link_data(G, edges="links")` to suppress NetworkX 3.6 FutureWarning
  - Broken wikilinks are node-level `[[slug]]` refs pointing to individual nodes (not community pages). This is expected since only community-level and INDEX pages are generated.
  - `extract_semantic` remains NotImplementedError stub (as specified)

### Step 4 — Search Layer Implementation ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files modified**: 2 (index.py, search.py)
- **Verification** (all 5 tests PASS):
  - Test 1: `index_markdown` — 12 documents indexed — PASS
  - Test 2: `search("detect file")` — 1 result, score 2.32 — PASS
  - Test 3: `search("xyznonexistent")` — 0 results (empty list) — PASS
  - Test 4: `update_index` — 0 updated (no changes) — PASS
  - Test 5: `build_index` wrapper — delegates to `index_markdown` correctly — PASS
- **Key decisions**:
  - Pure Python BM25 (Okapi), no external search libraries
  - Tokenization: lowercase + whitespace split + remove <=2 char tokens (shared between index and search)
  - IDF: `log(N / (1 + df))` as specified
  - BM25 params: k1=1.5, b=0.75 (standard)
  - Snippet: +-30 chars around first query token match, fallback to first 100 chars
  - `update_index` signature changed from `(changed_files, index_path)` to `(docs_dir, index_path)` per brief spec — it scans dir and uses SHA256 hash to detect changes
  - `search` signature simplified from `(query, index_path, mode="hybrid")` to `(query, index_path, top_k=5)` — vector/hybrid mode deferred
  - Index JSON stores tokens per doc for BM25 tf computation at search time

### Step 5 — Integration Layer + CLI ✅
- **Builder**: Bob
- **Date**: 2026-04-10
- **Status**: COMPLETE
- **Files modified**: 5 (pipeline.py, query.py, hooks.py, watch.py, cli.py)
- **Verification** (all 6 tests PASS):
  - Test 1: `pipeline.run` — 91 nodes, 17 index_docs — PASS
  - Test 2: `query("detect file")` — 3 search results, 4 graph nodes, tokens_used=1991 (<2000) — PASS
  - Test 3: `mindvault status` — 91 nodes, 146 edges, 10 communities, 17 wiki pages, 17 indexed docs — PASS
  - Test 4: `mindvault query "detect file"` — 3-layer formatted output — PASS
  - Test 5: `mindvault lint` — 17 pages, 358 broken wikilinks (node-level refs), 0 ambiguous edges — PASS
  - Test 6: `mark_dirty + flush` — mark 1 file, flush runs incremental, returns result — PASS
- **Key decisions**:
  - `pipeline.run`: calls `compile()` then `index_markdown()` on wiki dir
  - `pipeline.run_incremental`: uses `cache.get_dirty_files` for dirty detection, merges into existing graph.json, re-clusters, re-generates wiki + index
  - `query.py`: 3-layer pipeline (BM25 → graph BFS/DFS → wiki read). Budget enforcement reserves tokens for graph edges before allocating to wiki content
  - `hooks.py`: git hook appends to existing post-commit (preserves content). Claude hooks are opt-in only (not auto-activated by install). Dirty list stored as JSON array in `.mindvault_dirty.json`
  - `watch.py`: mtime polling with configurable debounce. Code changes trigger `run_incremental`, doc changes only `mark_dirty`
  - `cli.py`: extended existing argparse with 3 new subcommands (update, mark-dirty, flush). All original subcommands now have real implementations

### Step 6 — SKILL.md Completion + Deployment Preparation ✅
- **Builder**: Bob
- **Date**: 2026-04-10
- **Status**: COMPLETE
- **Files created/modified**: 3 (skill/SKILL.md rewritten, README.md rewritten, .gitignore created)
- **Verification** (all 7 tests PASS):
  - Test 1: `mindvault ingest src` — 91 nodes, 146 edges, 10 communities, 11 wiki pages, 11 indexed docs — PASS
  - Test 2: `mindvault query "how does the search layer work"` — 3-layer output, 1992 tokens — PASS
  - Test 3: `mindvault status` — 91 nodes, 146 edges, 10 communities, 11 wiki pages, 11 docs — PASS
  - Test 4: `mindvault lint` — 11 pages, 288 broken wikilinks (node-level, expected), 0 orphans, 0 ambiguous — PASS
  - Test 5: `mindvault install` — skill copied, CLAUDE.md registered — PASS
  - Test 6: Output files — graph.json, graph.html, GRAPH_REPORT.md, wiki/INDEX.md, search_index.json, 10 community pages — PASS
  - Test 7: `git init` + first commit `57e6c05` — 32 files, .gitignore excludes mindvault-out/ — PASS
- **Key decisions**:
  - SKILL.md follows Graphify pattern: YAML frontmatter, step-by-step bash blocks with Python one-liners, interpreter detection via `.mindvault_python` file
  - SKILL.md covers all subcommands: full pipeline, query, lint, status, ingest, install
  - README.md includes token savings table, 3-layer diagram, full commands table
  - Git commit does NOT push (user creates GitHub repo first)

## Known Gaps

- Cross-file call/import resolution: imports create edges to `{module}_module` IDs which may or may not exist as nodes; dangling ones are filtered by `build_graph`
- `extract_semantic` stub — needs LLM integration
- Broken wikilinks: node-level `[[slug]]` references in community pages point to slugs that don't have dedicated wiki pages (193 in self-compile). Could add per-node pages or switch to anchor links.
- `update_wiki` is minimal (returns 0) — needs community tracking for true incremental updates
