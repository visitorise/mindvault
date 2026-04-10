"""GRAPH_REPORT.md generation."""

from __future__ import annotations

from datetime import datetime

import networkx as nx


def generate_report(
    G: nx.DiGraph,
    communities: dict[int, list[str]],
    cohesion: dict[int, float],
    labels: dict[int, str],
    gods: list[dict],
    surprises: list[dict],
    detection: dict,
    source_path: str,
    questions: list[str] | None = None,
) -> str:
    """Generate a markdown report string summarizing the knowledge graph.

    Args:
        G: NetworkX DiGraph.
        communities: Dict mapping community_id to list of node_ids.
        cohesion: Dict mapping community_id to cohesion score.
        labels: Dict mapping community_id to human-readable label.
        gods: List of god node dicts from analyze.god_nodes.
        surprises: List of surprising connection dicts.
        detection: Dict from detect() with total_files, total_words.
        source_path: Path string of the source directory.
        questions: Optional list of suggested questions.

    Returns:
        Markdown string of the report.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# MindVault Graph Report",
        f"Generated: {now}",
        f"Source: {source_path}",
        "",
        "## Overview",
        f"- Nodes: {G.number_of_nodes()}",
        f"- Edges: {G.number_of_edges()}",
        f"- Communities: {len(communities)}",
        f"- Source files: {detection.get('total_files', 0)} ({detection.get('total_words', 0)} words)",
        "",
        "## Communities",
        "| # | Label | Nodes | Cohesion |",
        "|---|-------|-------|----------|",
    ]

    for cid in sorted(communities.keys()):
        lbl = labels.get(cid, f"Community {cid}")
        count = len(communities[cid])
        score = cohesion.get(cid, 0.0)
        lines.append(f"| {cid} | {lbl} | {count} | {score:.2f} |")

    lines.append("")
    lines.append("## God Nodes")
    lines.append("| Node | Connections | Source |")
    lines.append("|------|------------|--------|")

    for g in gods:
        lbl = g.get("label", g.get("id", "?"))
        edges = g.get("edges", 0)
        # Look up source file from graph
        nid = g.get("id", "")
        src = ""
        if nid and nid in G:
            src = G.nodes[nid].get("source_file", "")
        lines.append(f"| {lbl} | {edges} | {src} |")

    lines.append("")
    lines.append("## Surprising Connections")
    if surprises:
        for s in surprises:
            src_label = G.nodes[s["source"]].get("label", s["source"]) if s["source"] in G else s["source"]
            tgt_label = G.nodes[s["target"]].get("label", s["target"]) if s["target"] in G else s["target"]
            rel = s.get("relation", "related")
            src_comm = labels.get(s.get("source_community"), f"Community {s.get('source_community')}")
            tgt_comm = labels.get(s.get("target_community"), f"Community {s.get('target_community')}")
            lines.append(f"- **{src_label}** -> {rel} -> **{tgt_label}**")
            lines.append(f"  Communities: {src_comm} <-> {tgt_comm}")
    else:
        lines.append("- No surprising cross-community connections found.")

    lines.append("")
    lines.append("## Suggested Questions")
    if questions:
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. {q}")
    else:
        lines.append("1. What hidden dependencies exist in this codebase?")

    return "\n".join(lines) + "\n"
