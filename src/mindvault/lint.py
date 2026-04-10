"""Wiki and graph consistency checks."""

from __future__ import annotations

import json
import re
from pathlib import Path


def lint_wiki(wiki_dir: Path, graph_path: Path) -> dict:
    """Check wiki for consistency issues.

    Args:
        wiki_dir: Directory containing wiki pages.
        graph_path: Path to graph.json.

    Returns:
        Dict with keys: broken_links, orphan_pages, total_pages.
    """
    wiki_dir = Path(wiki_dir)
    if not wiki_dir.exists():
        return {"broken_links": [], "orphan_pages": [], "total_pages": 0}

    md_files = list(wiki_dir.glob("*.md"))
    total_pages = len(md_files)

    # Build set of existing slugs (filenames without .md)
    existing_slugs = {f.stem.lower() for f in md_files}

    # Find all wikilinks and track references
    wikilink_pattern = re.compile(r"\[\[([^\]]+)\]\]")
    broken_links: list[dict] = []
    referenced_slugs: set[str] = set()

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        for match in wikilink_pattern.finditer(content):
            link_slug = match.group(1).lower().strip()
            referenced_slugs.add(link_slug)
            if link_slug not in existing_slugs:
                broken_links.append({
                    "file": md_file.name,
                    "link": match.group(1),
                })

    # Orphan pages: exist but never referenced (exclude INDEX.md)
    orphan_pages: list[str] = []
    for md_file in md_files:
        slug = md_file.stem.lower()
        if slug == "index":
            continue
        if slug not in referenced_slugs:
            orphan_pages.append(md_file.name)

    return {
        "broken_links": broken_links,
        "orphan_pages": orphan_pages,
        "total_pages": total_pages,
    }


def lint_graph(graph_path: Path) -> dict:
    """Check graph for structural issues.

    Args:
        graph_path: Path to graph.json.

    Returns:
        Dict with keys: isolated_nodes, ambiguous_edges, total_nodes, total_edges.
    """
    graph_path = Path(graph_path)
    if not graph_path.exists():
        return {"isolated_nodes": [], "ambiguous_edges": 0, "total_nodes": 0, "total_edges": 0}

    data = json.loads(graph_path.read_text(encoding="utf-8"))

    # Reconstruct adjacency from link data
    nodes = data.get("nodes", [])
    links = data.get("links", [])

    # Build degree map
    degree: dict[str, int] = {}
    for n in nodes:
        nid = n.get("id", "")
        degree[nid] = 0

    for link in links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        if src in degree:
            degree[src] += 1
        if tgt in degree:
            degree[tgt] += 1

    isolated_nodes = [nid for nid, deg in degree.items() if deg == 0]

    # Count AMBIGUOUS edges
    ambiguous_edges = 0
    for link in links:
        if link.get("confidence") == "AMBIGUOUS":
            ambiguous_edges += 1

    return {
        "isolated_nodes": isolated_nodes,
        "ambiguous_edges": ambiguous_edges,
        "total_nodes": len(nodes),
        "total_edges": len(links),
    }
