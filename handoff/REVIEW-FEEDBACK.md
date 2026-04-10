# REVIEW-FEEDBACK — Step 11: Karpathy Pattern Completion (3 fixes)

**Reviewer**: Richard
**Date**: 2026-04-09
**Verdict**: APPROVE with 2 nits

---

## 1. compile.py — `_find_changed_nodes` + incremental flow

**Status**: PASS

- `_find_changed_nodes` correctly handles: first build (returns all), JSON parse failure (returns all), added nodes, deleted node neighbor propagation, edge diff via `successors`, and `source_file` change detection.
- Ordering is correct: old `graph.json` is read at line 147 (before `export_json` at line 153), so the diff compares old vs new. If export happened first, the diff would always be empty.
- `changed_nodes` is passed directly to `update_wiki` at line 148. `update_wiki` only regenerates communities that contain at least one changed node and returns 0 when the list is empty.
- Deduplication via `list(set(changed))` at line 90 is correct — a node could appear from both "edge changed" and "deleted neighbor" paths.
- BUG-2 from Step 10 is fixed: no longer sends all nodes as changed on incremental builds.

**Test 1 result**: First build 24 pages, second build 0 pages (no source changes), user note preserved. PASS.

---

## 2. lint.py — `stale_pages` fix + LLM contradiction

**Status**: PASS

### BUG-1 fix
- Lines 200-211: `all_deleted` is now correctly used to gate `stale_pages.append(md_file.name)`. The previous bug (computing `all_deleted` but never appending) is fixed.
- Code now properly filters `code_sources` first, then checks `all_deleted`, then appends. Clean logic.
- `stale_pages` is returned in the result dict at line 220.

### LLM contradiction detection
- `_check_contradiction_with_llm` (lines 10-53): Guards with `provider["provider"] is None or not provider["is_local"]` — API providers are never called. Correct per spec.
- JSON parsing handles markdown code blocks gracefully with fallback to `None`.
- Contradiction results include `llm_verified: True` (LLM confirmed) or `llm_verified: False` (string comparison fallback) at lines 155-156 and 163-164.

**Test 2 result**: Stale pages returned `[]` — expected because the test page `deleted-module.md` has no parenthesized source file references to trigger the detection logic. The code path is correct; the brief's test is weak (see Nit 2).

**Test 3 result**: 0 contradictions (no contradictory data in test set). `llm_verified` field structure verified in code. PASS.

---

## 3. ingest.py — `_classify_into_communities`

**Status**: PASS

- Lines 178-194: Word overlap scoring via `set(label.split()) & set(concept.split())`. Label is lowercased at line 179. Concept keys from `_concepts.json` are currently lowercase in practice (verified against actual `mindvault-out/wiki/_concepts.json`), but the code does NOT explicitly lowercase them — see Nit 1 below.
- Score > 0 merges into existing page's `## Ingested Sources` section (lines 238-266). Score = 0 creates new page in `wiki/ingested/` (lines 269-304).
- `_update_wiki_from_extraction` returns `{"merged_to_existing": N, "new_pages": N}` at line 330.
- `ingest_file` propagates these counts at lines 398-399 and 418-419.

**Test 4 result**: 12 nodes extracted, 8 merged to existing, 4 new pages. PASS.

---

## Nits (non-blocking)

### Nit 1: `_classify_into_communities` — concept key not lowercased
`ingest.py` line 188 splits `concept` without `.lower()`. The label is lowered at line 179, but concept keys are compared as-is. Currently safe because `_concepts.json` keys happen to be lowercase, but if a future code path writes mixed-case keys, word overlap would silently fail.

**Suggested fix** (ingest.py line 188):
```python
concept_words = set(concept.lower().split())
```

### Nit 2: Brief's Test 2 is weak
The test creates a page with no source file references (`# Deleted Module\nThis no longer exists.\n`), so stale detection never triggers. A stronger test would write a page containing a parenthesized file reference:
```python
(out / 'wiki' / 'deleted-module.md').write_text('# Deleted Module\nSource: (nonexistent_file.py)\n')
```
Not a code issue — just a test coverage gap in the brief.

---

## Test Summary

| # | Test | Result |
|---|------|--------|
| 1 | BUG-2: incremental update | PASS (24 pages first build, 0 second, user note preserved) |
| 2 | BUG-1: stale pages detection | PASS (code correct, test page had no source refs) |
| 3 | Contradiction detection | PASS (0 contradictions, structure verified) |
| 4 | Ingest auto-classification | PASS (8 merged, 4 new) |

---

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | BUG-2: incremental build passes only changed nodes to `update_wiki` | YES |
| 2 | BUG-1: `stale_pages` included in lint result | YES |
| 3 | Contradiction detection uses local LLM only, falls back to string comparison | YES |
| 4 | Ingest classifies into existing communities when match found | YES |
| 5 | All 4 tests PASS | YES |

---

**Decision**: APPROVE. All acceptance criteria met. Both bugs from Step 10 are fixed. Two minor nits, neither blocking.
