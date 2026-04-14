"""Search layer — BM25 + TF-IDF hybrid search (local, zero tokens).

v0.8.0: Hybrid scoring (BM25 + cosine similarity), title/heading boost,
dynamic score threshold, and query token expansion.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from .index import index_markdown, load_index


def _is_cjk(char: str) -> bool:
    """Check if a character is CJK (Chinese/Japanese/Korean)."""
    cp = ord(char)
    return (
        (0x3000 <= cp <= 0x9FFF)
        or (0xAC00 <= cp <= 0xD7AF)  # Hangul Syllables
        or (0xF900 <= cp <= 0xFAFF)
    )


def _tokenize(text: str) -> list[str]:
    """Tokenize text for BM25. Handles Korean/CJK and English.

    - Strips punctuation
    - English tokens: remove if len <= 2
    - Korean/CJK tokens: keep all (1-char is meaningful)
    """
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    tokens = []
    for t in cleaned.split():
        if not t:
            continue
        has_cjk = any(_is_cjk(c) for c in t)
        if has_cjk or len(t) > 2:
            tokens.append(t)
    return tokens


def _expand_query_tokens(tokens: list[str]) -> list[str]:
    """Expand query tokens with sub-tokens from compound identifiers.

    Splits camelCase, snake_case, and kebab-case into components.
    Returns original tokens + expanded sub-tokens (deduplicated).
    """
    expanded = list(tokens)
    for t in tokens:
        # Split camelCase: "runIncremental" → ["run", "incremental"]
        parts = re.sub(r'([a-z])([A-Z])', r'\1 \2', t).lower().split()
        # Split snake_case / kebab-case
        if '_' in t or '-' in t:
            parts = re.split(r'[_-]', t.lower())
        for p in parts:
            if p and p not in expanded and (len(p) > 2 or any(_is_cjk(c) for c in p)):
                expanded.append(p)
    return expanded


def _snippet(content_tokens: list[str], query_tokens: set[str], width: int = 30) -> str:
    """Build a snippet around the first matching token."""
    text = " ".join(content_tokens)
    for qt in query_tokens:
        pos = text.find(qt)
        if pos >= 0:
            start = max(0, pos - width)
            end = min(len(text), pos + len(qt) + width)
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(text) else ""
            return prefix + text[start:end] + suffix
    return text[:100] + ("..." if len(text) > 100 else "")


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two sparse TF-IDF vectors."""
    # Only iterate over shared keys for dot product
    common_keys = set(vec_a) & set(vec_b)
    if not common_keys:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in common_keys)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _title_heading_boost(doc: dict, query_tokens: set[str]) -> float:
    """Compute a multiplicative boost for title/heading matches.

    - Query token in title: +1.0
    - Query token in headings: +0.5
    Returns a multiplier >= 1.0.
    """
    boost = 1.0
    title_lower = doc.get("title", "").lower()
    headings_text = " ".join(doc.get("headings", [])).lower()

    for qt in query_tokens:
        if qt in title_lower:
            boost += 1.0
        elif qt in headings_text:
            boost += 0.5
    return boost


def search(query: str, index_path: Path, top_k: int = 5) -> list[dict]:
    """Hybrid BM25 + TF-IDF cosine search with title/heading boost.

    Scoring: final = (α * BM25_norm + (1-α) * cosine) * title_boost
    where α = 0.7 (BM25-dominant, cosine as tiebreaker).

    Args:
        query: Search query string.
        index_path: Path to the search index JSON.
        top_k: Number of top results to return.

    Returns:
        List of dicts: [{path, title, score, snippet, headings}, ...].
    """
    index_path = Path(index_path)
    index_data = load_index(index_path)
    docs = index_data.get("docs", {})
    idf = index_data.get("idf", {})

    if not docs:
        return []

    raw_tokens = _tokenize(query)
    if not raw_tokens:
        return []

    query_tokens = _expand_query_tokens(raw_tokens)
    query_token_set = set(query_tokens)

    # BM25 parameters
    k1 = 1.5
    b = 0.75
    alpha = 0.7  # BM25 weight in hybrid score

    # Average document length
    doc_lengths = {path: len(doc["tokens"]) for path, doc in docs.items()}
    avgdl = sum(doc_lengths.values()) / len(doc_lengths) if doc_lengths else 1.0

    # Build query TF-IDF vector for cosine similarity
    query_tf = Counter(query_tokens)
    query_vec: dict[str, float] = {}
    for qt, tf in query_tf.items():
        idf_val = idf.get(qt, 0.0)
        if idf_val > 0:
            query_vec[qt] = (1 + math.log(tf)) * idf_val

    raw_results = []

    for path, doc in docs.items():
        tokens = doc["tokens"]
        dl = len(tokens)
        if dl == 0:
            continue

        tf_counts = Counter(tokens)

        # --- BM25 score ---
        bm25_score = 0.0
        for qt in query_tokens:
            tf = tf_counts.get(qt, 0)
            idf_val = idf.get(qt)

            # CJK fuzzy: prefix/substring matching
            if tf == 0 and any(_is_cjk(c) for c in qt):
                for doc_token, count in tf_counts.items():
                    if doc_token.startswith(qt) or qt in doc_token:
                        tf += count
                        if idf_val is None:
                            idf_val = idf.get(doc_token)

            if tf == 0 or idf_val is None:
                continue
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / avgdl)
            bm25_score += idf_val * numerator / denominator

        # --- TF-IDF cosine score ---
        doc_vec: dict[str, float] = {}
        for token, count in tf_counts.items():
            idf_val = idf.get(token, 0.0)
            if idf_val > 0:
                doc_vec[token] = (1 + math.log(count)) * idf_val
        cosine_score = _cosine_similarity(query_vec, doc_vec)

        if bm25_score > 0 or cosine_score > 0:
            raw_results.append({
                "path": path,
                "doc": doc,
                "bm25": bm25_score,
                "cosine": cosine_score,
            })

    if not raw_results:
        return []

    # Normalize BM25 scores to [0, 1] for hybrid combination
    max_bm25 = max(r["bm25"] for r in raw_results) or 1.0
    max_cosine = max(r["cosine"] for r in raw_results) or 1.0

    results = []
    for r in raw_results:
        bm25_norm = r["bm25"] / max_bm25
        cosine_norm = r["cosine"] / max_cosine
        hybrid = alpha * bm25_norm + (1 - alpha) * cosine_norm

        # Title/heading boost
        boost = _title_heading_boost(r["doc"], query_token_set)
        final_score = hybrid * boost

        results.append({
            "path": r["path"],
            "title": r["doc"]["title"],
            "score": round(final_score * 100, 2),  # scale to 0-100+ range
            "snippet": _snippet(r["doc"]["tokens"], query_token_set),
            "headings": r["doc"].get("headings", []),
        })

    # Sort by score descending
    results.sort(key=lambda r: r["score"], reverse=True)

    # Dynamic threshold: drop results below 20% of top score
    if results:
        threshold = results[0]["score"] * 0.2
        results = [r for r in results if r["score"] >= threshold]

    return results[:top_k]


def build_index(docs_dir: Path, index_path: Path) -> int:
    """Index all markdown files (wrapper for index.index_markdown).

    Args:
        docs_dir: Directory containing markdown files to index.
        index_path: Path to write the search index.

    Returns:
        Number of documents indexed.
    """
    return index_markdown(Path(docs_dir), Path(index_path))
