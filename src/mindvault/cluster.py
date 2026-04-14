"""Community detection for the knowledge graph.

v0.8.0: Pre-clustering noise filtering + small community merging.
"""

from __future__ import annotations

from collections import Counter

import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities


def _filter_noise_nodes(G: nx.DiGraph) -> set[str]:
    """Identify noise nodes that should be excluded from wiki generation.

    Noise criteria:
    - Degree 0 (completely isolated)
    - Degree 1 with a generic/short label (e.g. single imports, __init__)

    Returns:
        Set of node IDs to exclude from clustering for wiki purposes.
        These nodes remain in the graph for search/query — only wiki skips them.
    """
    noise: set[str] = set()
    generic_labels = {"__init__", "index", "main", "utils", "helpers", "types", "config"}

    for nid in G.nodes():
        deg = G.degree(nid)
        label = G.nodes[nid].get("label", "").lower()

        if deg == 0:
            noise.add(nid)
        elif deg == 1 and (len(label) <= 3 or label in generic_labels):
            noise.add(nid)

    return noise


def cluster(G: nx.DiGraph, min_community_size: int = 3) -> dict[int, list[str]]:
    """Greedy modularity community detection with noise filtering.

    1. Filters noise nodes (isolated, generic single-edge)
    2. Runs greedy modularity on the cleaned subgraph
    3. Merges tiny communities (< min_community_size) into nearest neighbor

    Args:
        G: NetworkX DiGraph to partition.
        min_community_size: Minimum nodes per community. Smaller ones
            get merged into the community of their best-connected neighbor.

    Returns:
        Dict mapping community_id to list of node_ids.
        Noise nodes are excluded entirely (not in any community).
    """
    if G.number_of_nodes() == 0:
        return {0: []}

    # Step 1: Identify noise
    noise = _filter_noise_nodes(G)
    clean_nodes = [n for n in G.nodes() if n not in noise]

    if not clean_nodes:
        return {0: []}

    # Step 2: Cluster the clean subgraph
    subgraph = G.subgraph(clean_nodes).copy()
    undirected = subgraph.to_undirected()

    try:
        raw_communities = list(greedy_modularity_communities(undirected))
    except Exception:
        return {0: clean_nodes}

    # Step 3: Merge tiny communities into nearest neighbor
    node_to_comm: dict[str, int] = {}
    communities: dict[int, list[str]] = {}
    for i, comm in enumerate(raw_communities):
        communities[i] = sorted(comm)
        for nid in comm:
            node_to_comm[nid] = i

    # Find tiny communities and merge them
    tiny_cids = [cid for cid, members in communities.items() if len(members) < min_community_size]
    for cid in tiny_cids:
        members = communities[cid]
        # Find which other community has the most connections to these members
        neighbor_comm_counts: Counter[int] = Counter()
        for nid in members:
            for neighbor in undirected.neighbors(nid):
                ncid = node_to_comm.get(neighbor)
                if ncid is not None and ncid != cid and ncid not in tiny_cids:
                    neighbor_comm_counts[ncid] += 1

        if neighbor_comm_counts:
            target_cid = neighbor_comm_counts.most_common(1)[0][0]
            communities[target_cid].extend(members)
            for nid in members:
                node_to_comm[nid] = target_cid
        # If no non-tiny neighbor found, keep as-is (will be a small community)

        del communities[cid]

    # Re-index community IDs to be sequential
    result: dict[int, list[str]] = {}
    for new_id, (_, members) in enumerate(sorted(communities.items())):
        result[new_id] = sorted(members)

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
