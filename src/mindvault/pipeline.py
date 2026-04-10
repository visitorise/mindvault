"""Pipeline orchestrator: detect -> extract -> graph -> wiki -> index."""

from __future__ import annotations

import json
from pathlib import Path

from mindvault.compile import compile
from mindvault.index import index_markdown, update_index
from mindvault.detect import detect
from mindvault.extract import extract_ast
from mindvault.build import build_graph
from mindvault.cluster import cluster, score_cohesion
from mindvault.wiki import generate_wiki, _community_label
from mindvault.export import export_json, export_html
from mindvault.report import generate_report
from mindvault.cache import get_dirty_files, update_cache


def run(source_dir: Path, output_dir: Path = None, **kwargs) -> dict:
    """Full pipeline orchestrator.

    Args:
        source_dir: Root directory of the project.
        output_dir: Directory for MindVault output (default: source_dir/mindvault-out).
        **kwargs: Additional options passed to sub-steps.

    Returns:
        Dict with stats: {nodes, edges, communities, wiki_pages, index_docs, total_words}.
    """
    source_dir = Path(source_dir)
    if output_dir is None:
        output_dir = source_dir / "mindvault-out"
    output_dir = Path(output_dir)

    # Run compile (detect -> extract -> graph -> cluster -> wiki -> export)
    result = compile(source_dir, output_dir, **kwargs)

    # Build search index on wiki pages
    wiki_dir = output_dir / "wiki"
    index_path = output_dir / "search_index.json"
    index_docs = 0
    if wiki_dir.exists():
        index_docs = index_markdown(wiki_dir, index_path)

    result["index_docs"] = index_docs
    return result


def run_incremental(source_dir: Path, output_dir: Path = None) -> dict:
    """Incremental pipeline: only process changed files.

    Args:
        source_dir: Root directory of the project.
        output_dir: Directory for MindVault output.

    Returns:
        Dict with stats: {changed, nodes, edges, communities, wiki_pages, index_docs}
        or {changed: 0} if nothing changed.
    """
    source_dir = Path(source_dir)
    if output_dir is None:
        output_dir = source_dir / "mindvault-out"
    output_dir = Path(output_dir)

    # If output doesn't exist yet, run full pipeline
    graph_path = output_dir / "graph.json"
    if not graph_path.exists():
        return run(source_dir, output_dir)

    # Detect files
    detection = detect(source_dir)
    code_files = [source_dir / f for f in detection["files"].get("code", [])]

    # Check which files changed
    dirty_files = get_dirty_files(code_files, output_dir)

    if not dirty_files:
        return {"changed": 0}

    # Extract AST for dirty files only
    extraction = extract_ast(dirty_files)

    # Load existing graph data
    existing_data = json.loads(graph_path.read_text(encoding="utf-8"))
    existing_nodes = {n["id"]: n for n in existing_data.get("nodes", [])}
    existing_links = existing_data.get("links", [])

    # Merge: add new nodes, update existing
    for node in extraction["nodes"]:
        existing_nodes[node["id"]] = node

    # For edges, collect source files of dirty files and remove old edges from those files
    dirty_sources = {str(f) for f in dirty_files}
    kept_links = [
        link for link in existing_links
        if link.get("source_file") not in dirty_sources
    ]
    # Add new edges
    for edge in extraction["edges"]:
        kept_links.append({
            "source": edge["source"],
            "target": edge["target"],
            "relation": edge.get("relation", ""),
            "confidence": edge.get("confidence", ""),
            "confidence_score": edge.get("confidence_score", 1.0),
            "source_file": edge.get("source_file", ""),
            "weight": edge.get("weight", 1.0),
        })

    # Rebuild graph from merged data
    merged_extraction = {
        "nodes": list(existing_nodes.values()),
        "edges": kept_links,
    }
    G = build_graph(merged_extraction)

    # Re-cluster
    communities = cluster(G)
    cohesion = score_cohesion(G, communities)
    labels = {}
    for cid, members in communities.items():
        labels[cid] = _community_label(G, members)

    # Regenerate wiki
    wiki_pages = generate_wiki(G, communities, labels, output_dir, cohesion=cohesion)

    # Re-export
    export_json(G, communities, output_dir / "graph.json")
    export_html(G, communities, labels, output_dir / "graph.html")

    # Update search index
    wiki_dir = output_dir / "wiki"
    index_path = output_dir / "search_index.json"
    index_docs = 0
    if wiki_dir.exists():
        index_docs = update_index(wiki_dir, index_path)

    # Update cache for processed files
    for f in dirty_files:
        update_cache(f, output_dir)

    return {
        "changed": len(dirty_files),
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(communities),
        "wiki_pages": wiki_pages,
        "index_docs": index_docs,
    }
