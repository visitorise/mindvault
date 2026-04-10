"""Graph-to-wiki compilation (incremental)."""

from __future__ import annotations

from pathlib import Path

from mindvault.detect import detect
from mindvault.extract import extract_ast
from mindvault.build import build_graph
from mindvault.cluster import cluster, score_cohesion
from mindvault.analyze import god_nodes, surprising_connections, suggest_questions
from mindvault.wiki import generate_wiki, _community_label
from mindvault.export import export_json, export_html
from mindvault.report import generate_report


def _generate_labels(G, communities: dict[int, list[str]]) -> dict[int, str]:
    """Generate human-readable labels for each community."""
    labels: dict[int, str] = {}
    for cid, members in communities.items():
        labels[cid] = _community_label(G, members)
    return labels


def compile(source_dir: Path, output_dir: Path, incremental: bool = True) -> dict:
    """Full pipeline: detect -> extract_ast -> build_graph -> cluster -> analyze -> generate_wiki + export + report.

    Args:
        source_dir: Root directory of the project to compile.
        output_dir: Directory for MindVault output.
        incremental: If True, only reprocess changed files (not yet implemented, runs full).

    Returns:
        Dict with stats: {nodes, edges, communities, wiki_pages, total_words}.
    """
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Detect files
    detection = detect(source_dir)
    code_files = [source_dir / f for f in detection["files"].get("code", [])]

    # 2. Extract AST (extract_semantic is still stub, skip)
    extraction = extract_ast(code_files)

    # 3. Build graph
    G = build_graph(extraction)

    # 4. Cluster communities
    communities = cluster(G)
    cohesion = score_cohesion(G, communities)

    # 5. Generate labels
    labels = _generate_labels(G, communities)

    # 6. Analyze
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    questions = suggest_questions(G, communities, labels)

    # 7. Generate wiki
    wiki_pages = generate_wiki(G, communities, labels, output_dir, cohesion=cohesion)

    # 8. Export JSON
    export_json(G, communities, output_dir / "graph.json")

    # 9. Export HTML
    export_html(G, communities, labels, output_dir / "graph.html")

    # 10. Generate report
    report_md = generate_report(
        G, communities, cohesion, labels, gods, surprises,
        detection, str(source_dir), questions,
    )
    (output_dir / "GRAPH_REPORT.md").write_text(report_md, encoding="utf-8")

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(communities),
        "wiki_pages": wiki_pages,
        "total_words": detection.get("total_words", 0),
    }
