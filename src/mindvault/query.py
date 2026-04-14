"""3-layer query: search -> graph traverse -> wiki context -> answer."""

from __future__ import annotations

import json
import re
from collections import deque
from datetime import datetime
from pathlib import Path

from mindvault.search import search as bm25_search


def _is_cjk(char: str) -> bool:
    """Check if a character is CJK."""
    cp = ord(char)
    return (
        (0x3000 <= cp <= 0x9FFF)
        or (0xAC00 <= cp <= 0xD7AF)
        or (0xF900 <= cp <= 0xFAFF)
    )


def _keyword_match(question: str, node_id: str, node_label: str) -> bool:
    """Check if any keyword from the question matches a node.

    Korean/CJK tokens are kept regardless of length.
    English tokens must be > 2 chars.
    """
    import re
    cleaned = re.sub(r'[^\w\s]', ' ', question.lower())
    q_tokens = set()
    for t in cleaned.split():
        if not t:
            continue
        has_cjk = any(_is_cjk(c) for c in t)
        if has_cjk or len(t) > 2:
            q_tokens.add(t)

    label_lower = node_label.lower()
    nid_lower = node_id.lower()
    for token in q_tokens:
        if token in label_lower or token in nid_lower:
            return True
    return False


def _bfs_traverse(graph_data: dict, start_nodes: list[str], depth: int = 2) -> dict:
    """BFS traversal from start_nodes up to given depth."""
    nodes_set = {n["id"] for n in graph_data.get("nodes", [])}
    adj: dict[str, list[tuple[str, dict]]] = {}
    for link in graph_data.get("links", []):
        src = link.get("source", "")
        tgt = link.get("target", "")
        if src in nodes_set and tgt in nodes_set:
            adj.setdefault(src, []).append((tgt, link))
            adj.setdefault(tgt, []).append((src, link))

    visited: set[str] = set()
    neighbors: list[str] = []
    edges: list[dict] = []
    queue: deque[tuple[str, int]] = deque()

    for sn in start_nodes:
        if sn in nodes_set:
            queue.append((sn, 0))
            visited.add(sn)

    while queue:
        node, d = queue.popleft()
        if d >= depth:
            continue
        for neighbor, link in adj.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                neighbors.append(neighbor)
                edges.append(link)
                queue.append((neighbor, d + 1))

    return {"neighbors": neighbors, "edges": edges}


def _dfs_traverse(graph_data: dict, start_nodes: list[str], depth: int = 4) -> dict:
    """DFS traversal from start_nodes up to given depth."""
    nodes_set = {n["id"] for n in graph_data.get("nodes", [])}
    adj: dict[str, list[tuple[str, dict]]] = {}
    for link in graph_data.get("links", []):
        src = link.get("source", "")
        tgt = link.get("target", "")
        if src in nodes_set and tgt in nodes_set:
            adj.setdefault(src, []).append((tgt, link))
            adj.setdefault(tgt, []).append((src, link))

    visited: set[str] = set()
    neighbors: list[str] = []
    edges: list[dict] = []

    def dfs(node: str, d: int) -> None:
        if d >= depth:
            return
        for neighbor, link in adj.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                neighbors.append(neighbor)
                edges.append(link)
                dfs(neighbor, d + 1)

    for sn in start_nodes:
        if sn in nodes_set:
            visited.add(sn)
            dfs(sn, 0)

    return {"neighbors": neighbors, "edges": edges}


def _slugify_query(text: str) -> str:
    """Convert question text to a filesystem-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:60]


def _save_query_to_wiki(question: str, result: dict, output_dir: Path) -> Path:
    """Save query result to wiki/queries/ directory."""
    queries_dir = output_dir / "wiki" / "queries"
    queries_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = _slugify_query(question)
    filename = f"{date_str}-{slug}.md"
    filepath = queries_dir / filename

    lines = [
        f"# Q: {question}",
        f"Date: {date_str}",
        "",
        "## Answer Context",
    ]

    # Search results summary
    search_results = result.get("search_results", [])
    if search_results:
        lines.append("")
        lines.append("### Search Results")
        for sr in search_results:
            lines.append(f"- **{sr.get('title', '')}** (score: {sr.get('score', 0)})")
            snippet = sr.get("snippet", "")
            if snippet:
                lines.append(f"  > {snippet}")

    # Graph context summary
    gc = result.get("graph_context", {})
    matched = gc.get("matched_nodes", [])
    if matched:
        lines.append("")
        lines.append("### Graph Context")
        lines.append(f"Matched nodes: {', '.join(matched[:10])}")
        neighbors = gc.get("neighbors", [])
        if neighbors:
            lines.append(f"Neighbors: {', '.join(neighbors[:10])}")

    # Wiki context excerpt
    wiki_ctx = result.get("wiki_context", "")
    if wiki_ctx:
        lines.append("")
        lines.append("### Wiki Context")
        # Truncate to first 500 chars
        excerpt = wiki_ctx[:500]
        if len(wiki_ctx) > 500:
            excerpt += "..."
        lines.append(excerpt)

    # Sources
    lines.append("")
    lines.append("## Sources")
    for sr in search_results:
        path = sr.get("path", "")
        title = sr.get("title", path)
        lines.append(f"- [[{path}]] -- {title}")

    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Update _concepts.json with query keywords
    concepts_path = output_dir / "wiki" / "_concepts.json"
    concepts: dict[str, list[str]] = {}
    if concepts_path.exists():
        try:
            concepts = json.loads(concepts_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            concepts = {}

    # Add query keywords to concepts index
    query_page = f"queries/{filename}"
    for token in question.lower().split():
        token = re.sub(r"[^a-z0-9가-힣]", "", token)
        if len(token) > 2:
            if token not in concepts:
                concepts[token] = []
            if query_page not in concepts[token]:
                concepts[token].append(query_page)

    concepts_path.write_text(json.dumps(concepts, ensure_ascii=False, indent=2), encoding="utf-8")

    # Update search index to include the saved query
    _update_search_index_for_query(filepath, output_dir)

    return filepath


def _update_search_index_for_query(query_file: Path, output_dir: Path) -> None:
    """Add saved query file to search index."""
    index_path = output_dir / "search_index.json"
    if not index_path.exists():
        return

    from mindvault.index import load_index, _tokenize, _extract_title, _extract_headings, _hash_content, _compute_idf

    index_data = load_index(index_path)
    docs = index_data.get("docs", {})

    content = query_file.read_text(encoding="utf-8")
    wiki_dir = output_dir / "wiki"
    rel_path = str(query_file.relative_to(wiki_dir))

    docs[rel_path] = {
        "title": _extract_title(content) or query_file.stem,
        "headings": _extract_headings(content),
        "tokens": _tokenize(content),
        "hash": _hash_content(content),
    }

    index_data["docs"] = docs
    index_data["doc_count"] = len(docs)
    index_data["idf"] = _compute_idf(docs)
    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")


def query(question: str, output_dir: Path, mode: str = "bfs", budget: int = 2000, save: bool = False) -> dict:
    """3-layer query: search -> graph -> wiki -> answer context.

    Args:
        question: Natural language question.
        output_dir: MindVault output directory containing index, graph, wiki.
        mode: Graph traversal mode — "bfs" or "dfs".
        budget: Maximum token budget for context assembly.

    Returns:
        Dict with keys: search_results, graph_context, wiki_context, tokens_used.
    """
    output_dir = Path(output_dir)

    # === Step 1: Search Layer (0 tokens) ===
    index_path = output_dir / "search_index.json"
    search_results = []
    if index_path.exists():
        search_results = bm25_search(question, index_path, top_k=3)

    # === Step 2: Graph Layer ===
    graph_path = output_dir / "graph.json"
    graph_data = {}
    matched_nodes: list[str] = []
    graph_context = {
        "matched_nodes": [],
        "neighbors": [],
        "edges": [],
        "communities": [],
    }

    if graph_path.exists():
        graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = graph_data.get("nodes", [])

        # Find nodes matching question keywords
        for node in nodes:
            nid = node.get("id", "")
            label = node.get("label", "")
            if _keyword_match(question, nid, label):
                matched_nodes.append(nid)

        # Traverse graph
        if matched_nodes:
            if mode == "dfs":
                traversal = _dfs_traverse(graph_data, matched_nodes, depth=4)
            elif mode == "hybrid":
                bfs_result = _bfs_traverse(graph_data, matched_nodes, depth=2)
                dfs_result = _dfs_traverse(graph_data, matched_nodes, depth=4)
                seen = set(bfs_result["neighbors"])
                merged_neighbors = list(bfs_result["neighbors"])
                merged_edges = list(bfs_result["edges"])
                for n, e in zip(dfs_result["neighbors"], dfs_result["edges"]):
                    if n not in seen:
                        seen.add(n)
                        merged_neighbors.append(n)
                        merged_edges.append(e)
                traversal = {"neighbors": merged_neighbors, "edges": merged_edges}
            else:
                traversal = _bfs_traverse(graph_data, matched_nodes, depth=2)

            # Find communities for matched nodes
            communities_data = graph_data.get("communities", {})
            matched_communities = []
            for cid, members in communities_data.items():
                for mn in matched_nodes:
                    if mn in members:
                        matched_communities.append(cid)
                        break

            graph_context = {
                "matched_nodes": matched_nodes,
                "neighbors": traversal["neighbors"],
                "edges": traversal["edges"],
                "communities": matched_communities,
            }

    # === Step 3: Wiki Layer ===
    wiki_dir = output_dir / "wiki"
    wiki_context = ""

    # Strict budget: cap graph context to 25% of budget, rest for wiki.
    # This prevents graph edges from eating the entire budget.
    max_graph_tokens = budget // 4
    graph_edge_chars = sum(len(str(e)) for e in graph_context.get("edges", []))
    graph_tokens = min(graph_edge_chars // 4, max_graph_tokens)

    # If graph used too many tokens, trim edges
    if graph_edge_chars // 4 > max_graph_tokens:
        # Trim edges to fit budget
        trimmed_edges = []
        char_acc = 0
        for e in graph_context.get("edges", []):
            ec = len(str(e))
            if char_acc + ec > max_graph_tokens * 4:
                break
            trimmed_edges.append(e)
            char_acc += ec
        graph_context["edges"] = trimmed_edges

    wiki_token_budget = budget - graph_tokens - 50  # margin for headers
    if wiki_token_budget < 200:
        wiki_token_budget = 200
    char_limit = wiki_token_budget * 4

    if wiki_dir.exists():
        # Collect wiki pages from search results (including lore entries)
        wiki_paths = []
        for sr in search_results:
            wp = wiki_dir / sr["path"]
            if wp.exists():
                wiki_paths.append(wp)
            if sr["path"].startswith("lore/"):
                lore_path = output_dir / sr["path"]
                if lore_path.exists():
                    wiki_paths.append(lore_path)

        # NO fallback to random wiki pages — if search didn't find
        # relevant pages, injecting random ones is worse than nothing.

        # Read wiki content up to budget
        parts = []
        total_chars = 0
        for wp in wiki_paths:
            try:
                content = wp.read_text(encoding="utf-8")
                if total_chars + len(content) > char_limit:
                    remaining = char_limit - total_chars
                    if remaining > 100:
                        parts.append(content[:remaining] + "...")
                        total_chars += remaining
                    break
                parts.append(content)
                total_chars += len(content)
            except (OSError, IOError):
                continue

        wiki_context = "\n\n---\n\n".join(parts)

    # Calculate approximate tokens
    total_text = wiki_context
    for edge in graph_context.get("edges", []):
        total_text += str(edge)
    tokens_used = len(total_text) // 4

    result = {
        "search_results": search_results,
        "graph_context": graph_context,
        "wiki_context": wiki_context,
        "tokens_used": tokens_used,
    }

    if save:
        saved_path = _save_query_to_wiki(question, result, output_dir)
        result["saved_to"] = str(saved_path)

    return result
