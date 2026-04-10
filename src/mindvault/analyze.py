"""Graph analysis — hub detection and surprising connections."""

from __future__ import annotations

import networkx as nx


def god_nodes(G: nx.DiGraph, top_n: int = 5) -> list[dict]:
    """Find highest-degree hub nodes.

    Args:
        G: NetworkX DiGraph.
        top_n: Number of top hub nodes to return.

    Returns:
        List of dicts: [{id, label, edges}, ...].
    """
    if G.number_of_nodes() == 0:
        return []

    degrees = [(node, G.degree(node)) for node in G.nodes()]
    degrees.sort(key=lambda x: x[1], reverse=True)

    result = []
    for node, deg in degrees[:top_n]:
        data = G.nodes[node]
        result.append({
            "id": node,
            "label": data.get("label", node),
            "edges": deg,
        })
    return result


def surprising_connections(G: nx.DiGraph, communities: dict[int, list[str]]) -> list[dict]:
    """Find unexpected cross-community edges.

    Cross-community edges where both endpoints have low degree are
    more surprising (non-hub nodes bridging different clusters).

    Args:
        G: NetworkX DiGraph.
        communities: Dict mapping community_id to list of node_ids.

    Returns:
        List of top 5 surprising cross-community edges.
    """
    # Build reverse lookup: node -> community_id
    node_to_comm: dict[str, int] = {}
    for cid, members in communities.items():
        for m in members:
            node_to_comm[m] = cid

    candidates = []
    for u, v, data in G.edges(data=True):
        cu = node_to_comm.get(u)
        cv = node_to_comm.get(v)
        if cu is None or cv is None or cu == cv:
            continue
        # Score: lower combined degree = more surprising
        combined_degree = G.degree(u) + G.degree(v)
        candidates.append({
            "source": u,
            "target": v,
            "source_community": cu,
            "target_community": cv,
            "relation": data.get("relation", "unknown"),
            "confidence": data.get("confidence", "EXTRACTED"),
            "source_files": [data.get("source_file", "")],
            "_score": combined_degree,
        })

    # Sort by combined degree ascending (lower = more surprising)
    candidates.sort(key=lambda x: x["_score"])

    result = []
    for c in candidates[:5]:
        c.pop("_score")
        result.append(c)
    return result


def suggest_questions(G: nx.DiGraph, communities: dict[int, list[str]], labels: dict) -> list[str]:
    """Generate questions from community labels and cross-community relationships.

    Args:
        G: NetworkX DiGraph.
        communities: Dict mapping community_id to list of node_ids.
        labels: Dict mapping community_id to human-readable label.

    Returns:
        List of 5 question strings.
    """
    questions = []
    comm_ids = sorted(communities.keys())

    # Generate cross-community questions
    for i, c1 in enumerate(comm_ids):
        for c2 in comm_ids[i + 1:]:
            l1 = labels.get(c1, f"Community {c1}")
            l2 = labels.get(c2, f"Community {c2}")
            questions.append(
                f"How does {l1} relate to {l2}?"
            )
            if len(questions) >= 5:
                break
        if len(questions) >= 5:
            break

    # Pad with generic questions if we don't have enough cross-community pairs
    while len(questions) < 5:
        idx = len(questions)
        if idx < len(comm_ids):
            cid = comm_ids[idx]
            lbl = labels.get(cid, f"Community {cid}")
            questions.append(f"What is the primary responsibility of {lbl}?")
        else:
            questions.append(f"What hidden dependencies exist in this codebase?")
            break

    return questions[:5]
