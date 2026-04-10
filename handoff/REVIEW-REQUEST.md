# REVIEW-REQUEST — Step 12: Document Structure Extraction

**Builder**: Bob
**Date**: 2026-04-09
**Step**: 12 — Document Structure Extraction (Markdown/Text/RST/PDF parsing, zero LLM)

## Files Modified (3)

1. **`src/mindvault/extract.py`** — Added `extract_document_structure` + 3 parser functions:
   - `extract_document_structure(doc_files)` — main entry point, dispatches by extension
   - `_parse_markdown` — parses `#` headers (depth 1-3) into nodes with parent-child `contains` edges via stack, `[link](url)` → `references` edges (internal only, skips http/anchors), `` ```lang``` `` → `has_code_example` edges with language nodes, `[[wikilink]]` → `references` edges
   - `_parse_text` — RST underline headers (`===`, `---`, etc.) and plain .txt uppercase-line sections
   - `_parse_pdf` — `pdftotext` subprocess with `shutil.which` guard + 30s timeout, silent skip on failure
   - All nodes: `file_type: "document"`, `source_location: "line N"`
   - All edges: `confidence: "EXTRACTED"`, `confidence_score: 1.0`
   - Node ID: `{filestem}_{heading_slug}` via `_sanitize_id`
   - Internal dedup via `seen_ids` set (first node wins)

2. **`src/mindvault/compile.py`** — Integration + merge expansion:
   - `_merge_extractions` changed from `(ast_result, sem_result)` to `(*results)` variadic
   - Node deduplication by ID in merge (first occurrence wins across all results)
   - Merge order: AST → doc_structure → semantic (AST nodes take priority)
   - `compile()` now calls 3 extractors: `extract_ast` → `extract_document_structure` → `extract_semantic`

3. **`src/mindvault/__init__.py`** — Export `extract_document_structure`

## Test Results (all 3 PASS)

| # | Test | Result | Detail |
|---|------|--------|--------|
| 1 | Markdown structure extraction | PASS | README.md → 12 nodes, 13 edges, 0 input_tokens, 0 output_tokens |
| 2 | Full pipeline integration | PASS | 453 nodes, 559 edges (was ~271 without doc structure — 67% increase) |
| 3 | Empty document | PASS | 0 nodes, no errors |

## Review Focus Areas

1. **Markdown parser code-block tracking**: `in_code_block` toggle prevents false header detection inside fenced code blocks. The toggle tracks `` ``` `` lines. Edge case: nested code blocks (rare) would cause toggle confusion — acceptable tradeoff.

2. **Variadic `_merge_extractions`**: The old 2-arg version simply concatenated nodes. The new version deduplicates by node ID (first wins). This is a behavior change — previously if AST and semantic both produced a node with the same ID, both would appear. Now only the first survives. This matches the brief spec ("first wins") and prevents graph bloat.

3. **PDF silent skip**: Two levels of safety — `shutil.which("pdftotext")` returns `None` if binary not installed (returns immediately), and `subprocess.run` has a 30s timeout. Both paths return without error.

4. **RST header detection**: Uses "previous line is text + current line is all same char (from `=-~^` etc.)" heuristic. This matches the RST spec but doesn't distinguish header levels (all are flat nodes). Acceptable since RST files are rare in most codebases.

## Acceptance Criteria Check

| # | Criterion | Status |
|---|-----------|--------|
| 1 | README.md: 5+ section nodes extracted | YES (12 nodes) |
| 2 | Token usage: 0 | YES (input_tokens=0, output_tokens=0) |
| 3 | Pipeline integration: total nodes increased | YES (271 → 453, +67%) |
| 4 | Empty document: no crash | YES (0 nodes returned) |
| 5 | All 3 tests PASS | YES |
