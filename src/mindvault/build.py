"""NetworkX graph construction from extraction results."""

from __future__ import annotations

import networkx as nx


def build_graph(extraction: dict) -> nx.DiGraph:
    """Build a NetworkX DiGraph from extraction result.

    Args:
        extraction: Dict with 'nodes' and 'edges' lists from extract_ast/extract_semantic.

    Returns:
        NetworkX DiGraph with nodes and edges populated.
    """
    G = nx.DiGraph()

    seen_nodes: set[str] = set()
    for node in extraction.get("nodes", []):
        nid = node["id"]
        if nid in seen_nodes:
            continue  # Keep first occurrence
        seen_nodes.add(nid)
        attrs = {k: v for k, v in node.items() if k != "id"}
        G.add_node(nid, **attrs)

    for edge in extraction.get("edges", []):
        src = edge["source"]
        tgt = edge["target"]
        # Skip dangling edges
        if src not in seen_nodes or tgt not in seen_nodes:
            continue
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        G.add_edge(src, tgt, **attrs)

    return G
