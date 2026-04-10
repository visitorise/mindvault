"""Wiki page generation from graph communities."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import networkx as nx


def _slugify(label: str) -> str:
    """Convert label to slug: lowercase, spaces to hyphens, remove special chars."""
    slug = label.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _community_label(G: nx.DiGraph, members: list[str]) -> str:
    """Generate a human-readable label for a community from its top nodes."""
    if not members:
        return "Empty Community"
    # Pick top 2 nodes by degree
    by_degree = sorted(members, key=lambda n: G.degree(n), reverse=True)
    top = by_degree[:2]
    parts = []
    for nid in top:
        lbl = G.nodes[nid].get("label", nid)
        parts.append(lbl)
    return " & ".join(parts)


def _node_to_community(communities: dict[int, list[str]]) -> dict[str, int]:
    """Build reverse lookup: node_id -> community_id."""
    mapping: dict[str, int] = {}
    for cid, members in communities.items():
        for m in members:
            mapping[m] = cid
    return mapping


def generate_wiki(
    G: nx.DiGraph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    output_dir: Path,
    cohesion: dict[int, float] | None = None,
) -> int:
    """Generate wiki pages from graph communities.

    Args:
        G: NetworkX DiGraph.
        communities: Dict mapping community_id to list of node_ids.
        labels: Dict mapping community_id to human-readable label.
        output_dir: Base output directory (wiki/ will be created inside).
        cohesion: Optional dict mapping community_id to cohesion score.

    Returns:
        Number of pages generated.
    """
    wiki_dir = output_dir / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    if cohesion is None:
        cohesion = {}

    node_to_comm = _node_to_community(communities)
    pages_generated = 0

    # --- INDEX.md ---
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Knowledge Wiki",
        f"Generated: {now}",
        f"Nodes: {G.number_of_nodes()} | Edges: {G.number_of_edges()} | Communities: {len(communities)}",
        "",
        "## Communities",
    ]
    for cid in sorted(communities.keys()):
        members = communities[cid]
        lbl = labels.get(cid, f"Community {cid}")
        slug = _slugify(lbl)
        score = cohesion.get(cid, 0.0)
        lines.append(f"- [[{slug}]] ({len(members)} nodes, cohesion: {score:.2f})")

    # God nodes (top 5 by degree)
    god_nodes = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:5]
    lines.append("")
    lines.append("## God Nodes")
    for nid in god_nodes:
        data = G.nodes[nid]
        lbl = data.get("label", nid)
        deg = G.degree(nid)
        slug = _slugify(lbl)
        lines.append(f"- [[{slug}]] -- {deg} connections")

    (wiki_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    pages_generated += 1

    # --- Per-community pages ---
    for cid in sorted(communities.keys()):
        members = communities[cid]
        if not members:
            continue

        lbl = labels.get(cid, f"Community {cid}")
        slug = _slugify(lbl)
        score = cohesion.get(cid, 0.0)

        page_lines = [
            f"# {lbl}",
            f"Cohesion: {score:.2f} | Nodes: {len(members)}",
            "",
            "## Key Nodes",
        ]

        member_set = set(members)
        by_degree = sorted(members, key=lambda n: G.degree(n), reverse=True)

        for nid in by_degree:
            data = G.nodes[nid]
            nlabel = data.get("label", nid)
            src_file = data.get("source_file", "")
            deg = G.degree(nid)
            nslug = _slugify(nlabel)
            page_lines.append(f"- **{nlabel}** ({src_file}) -- {deg} connections")

            # Outgoing edges
            for _, target, edata in G.out_edges(nid, data=True):
                tlabel = G.nodes[target].get("label", target) if target in G else target
                tslug = _slugify(tlabel)
                rel = edata.get("relation", "related")
                page_lines.append(f"  - -> {rel} -> [[{tslug}]]")

            # Incoming edges
            for source, _, edata in G.in_edges(nid, data=True):
                slabel = G.nodes[source].get("label", source) if source in G else source
                sslug = _slugify(slabel)
                rel = edata.get("relation", "related")
                page_lines.append(f"  - <- {rel} <- [[{sslug}]]")

        # Internal relationships
        page_lines.append("")
        page_lines.append("## Internal Relationships")
        for u in members:
            for _, v, edata in G.out_edges(u, data=True):
                if v in member_set:
                    ulabel = G.nodes[u].get("label", u)
                    vlabel = G.nodes[v].get("label", v)
                    rel = edata.get("relation", "related")
                    conf = edata.get("confidence", "EXTRACTED")
                    page_lines.append(f"- {ulabel} -> {rel} -> {vlabel} [{conf}]")

        # Cross-community connections
        page_lines.append("")
        page_lines.append("## Cross-Community Connections")
        for u in members:
            for _, v, edata in G.out_edges(u, data=True):
                if v not in member_set and v in G:
                    other_cid = node_to_comm.get(v)
                    other_lbl = labels.get(other_cid, f"Community {other_cid}") if other_cid is not None else "Unknown"
                    other_slug = _slugify(other_lbl)
                    ulabel = G.nodes[u].get("label", u)
                    vlabel = G.nodes[v].get("label", v)
                    rel = edata.get("relation", "related")
                    page_lines.append(f"- {ulabel} -> {rel} -> {vlabel} (-> [[{other_slug}]])")

        # Context section (template-based, no LLM)
        page_lines.append("")
        page_lines.append("## Context")

        top_labels = [G.nodes[n].get("label", n) for n in by_degree[:3]]
        top_str = ", ".join(top_labels)

        # Dominant relation
        rel_counter: Counter[str] = Counter()
        for u in members:
            for _, v, edata in G.out_edges(u, data=True):
                if v in member_set:
                    rel_counter[edata.get("relation", "related")] += 1
        dominant_rel = rel_counter.most_common(1)[0][0] if rel_counter else "related"

        # Source files
        src_files = set()
        for n in members:
            sf = G.nodes[n].get("source_file", "")
            if sf:
                src_files.add(Path(sf).name)
        src_str = ", ".join(sorted(src_files)[:5]) if src_files else "N/A"

        page_lines.append(
            f"이 커뮤니티는 {top_str}를 중심으로 {dominant_rel} 관계로 연결되어 있다. "
            f"주요 소스 파일은 {src_str}이다."
        )

        (wiki_dir / f"{slug}.md").write_text("\n".join(page_lines) + "\n", encoding="utf-8")
        pages_generated += 1

    return pages_generated


def update_wiki(G: nx.DiGraph, changed_nodes: list[str], wiki_dir: Path) -> int:
    """Incrementally update only affected wiki pages.

    Args:
        G: NetworkX graph.
        changed_nodes: List of node_ids that changed.
        wiki_dir: Directory containing existing wiki pages.

    Returns:
        Number of pages updated.
    """
    # This is a simplified incremental update.
    # In practice, we'd track which communities the changed nodes belong to
    # and only regenerate those pages. For now, return 0 if no changes.
    if not changed_nodes:
        return 0

    # Would need communities + labels to regenerate. For now, signal that
    # a full regeneration is needed.
    return 0
