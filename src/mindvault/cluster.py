"""Community detection for the knowledge graph."""

from __future__ import annotations

import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities


def cluster(G: nx.DiGraph) -> dict[int, list[str]]:
    """Greedy modularity community detection.

    Converts DiGraph to undirected for clustering.

    Args:
        G: NetworkX DiGraph to partition.

    Returns:
        Dict mapping community_id to list of node_ids.
    """
    if G.number_of_nodes() == 0:
        return {0: []}

    undirected = G.to_undirected()
    try:
        communities = greedy_modularity_communities(undirected)
    except Exception:
        # Fallback: all nodes in one community
        return {0: list(G.nodes())}

    result: dict[int, list[str]] = {}
    for i, comm in enumerate(communities):
        result[i] = sorted(comm)
    return result


def score_cohesion(G: nx.DiGraph, communities: dict[int, list[str]]) -> dict[int, float]:
    """Score each community's internal cohesion.

    Cohesion = internal_edges / possible_edges (0.0 to 1.0).
    Single-node communities get score 1.0.

    Args:
        G: NetworkX DiGraph.
        communities: Dict mapping community_id to list of node_ids.

    Returns:
        Dict mapping community_id to cohesion score.
    """
    scores: dict[int, float] = {}
    undirected = G.to_undirected()

    for cid, members in communities.items():
        n = len(members)
        if n <= 1:
            scores[cid] = 1.0
            continue

        possible = n * (n - 1) / 2
        member_set = set(members)
        internal = 0
        for u in members:
            for v in undirected.neighbors(u):
                if v in member_set and v > u:
                    internal += 1

        scores[cid] = internal / possible if possible > 0 else 0.0

    return scores
