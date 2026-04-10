"""Wiki and graph consistency checks."""

from __future__ import annotations

import json
import re
from pathlib import Path


def _check_contradiction_with_llm(concept: str, snippets: list[dict]) -> bool | None:
    """Use local LLM to judge if two snippets about the same concept contradict.

    Args:
        concept: The concept being checked.
        snippets: List of dicts with 'text' keys containing snippet text.

    Returns:
        True if contradictory, False if not, None if no local LLM available
        or LLM call failed.
    """
    try:
        from mindvault.llm import detect_llm, call_llm
    except ImportError:
        return None

    provider = detect_llm()
    if provider["provider"] is None or not provider["is_local"]:
        return None  # Local LLM only — never use API for lint

    prompt = (
        f'다음 두 설명이 같은 개념 "{concept}"에 대해 모순되는지 판단하세요.\n'
        f'설명 1: {snippets[0]["text"]}\n'
        f'설명 2: {snippets[1]["text"]}\n\n'
        'JSON으로만 답하세요: {"contradiction": true/false, "reason": "..."}'
    )

    try:
        result = call_llm(prompt, "", provider)
        if not result:
            return None
        # Parse JSON from response
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        data = json.loads(cleaned)
        return bool(data.get("contradiction", False))
    except (json.JSONDecodeError, KeyError, TypeError, Exception):
        return None  # Graceful fallback


def lint_wiki(wiki_dir: Path, graph_path: Path) -> dict:
    """Check wiki for consistency issues.

    Args:
        wiki_dir: Directory containing wiki pages.
        graph_path: Path to graph.json.

    Returns:
        Dict with keys: broken_links, orphan_pages, contradictions,
        orphan_concepts, stale_pages, total_pages.
    """
    wiki_dir = Path(wiki_dir)
    if not wiki_dir.exists():
        return {
            "broken_links": [], "orphan_pages": [],
            "contradictions": [], "orphan_concepts": [], "stale_pages": [],
            "total_pages": 0,
        }

    # Collect all .md files recursively (includes ingested/, queries/)
    md_files = list(wiki_dir.rglob("*.md"))
    total_pages = len(md_files)

    # Build set of existing slugs (filenames without .md, including subdir paths)
    existing_slugs: set[str] = set()
    for f in md_files:
        existing_slugs.add(f.stem.lower())
        # Also add relative path forms
        try:
            rel = str(f.relative_to(wiki_dir))
            existing_slugs.add(rel.lower())
        except ValueError:
            pass

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

    # --- Contradiction detection ---
    contradictions: list[dict] = []
    concepts_path = wiki_dir / "_concepts.json"
    concepts: dict[str, list[str]] = {}
    if concepts_path.exists():
        try:
            concepts = json.loads(concepts_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            concepts = {}

    for concept, pages in concepts.items():
        if len(pages) < 2:
            continue
        # Extract snippets about this concept from each page
        snippets: list[dict] = []
        for page_name in pages:
            page_path = wiki_dir / page_name
            if not page_path.exists():
                continue
            content = page_path.read_text(encoding="utf-8", errors="ignore")
            # Find lines mentioning this concept
            concept_lower = concept.lower()
            for line in content.splitlines():
                if concept_lower in line.lower() and line.strip():
                    snippets.append({"page": page_name, "text": line.strip()})
                    break  # one snippet per page

        if len(snippets) >= 2:
            # Simple string comparison check: if snippets differ significantly
            unique_snippets = set(s["text"] for s in snippets)
            if len(unique_snippets) > 1:
                # Try LLM contradiction verification (local only)
                llm_result = _check_contradiction_with_llm(concept, snippets)
                if llm_result is not None:
                    # LLM gave a verdict
                    if llm_result:
                        contradictions.append({
                            "concept": concept,
                            "pages": pages,
                            "snippets": [s["text"] for s in snippets],
                            "llm_verified": True,
                        })
                else:
                    # No local LLM or LLM call failed — fallback to string comparison
                    contradictions.append({
                        "concept": concept,
                        "pages": pages,
                        "snippets": [s["text"] for s in snippets],
                        "llm_verified": False,
                    })

    # --- Orphan concepts ---
    orphan_concepts: list[str] = []
    all_wiki_content = ""
    for md_file in md_files:
        try:
            all_wiki_content += md_file.read_text(encoding="utf-8", errors="ignore") + "\n"
        except (OSError, IOError):
            continue

    all_wiki_lower = all_wiki_content.lower()
    for concept in concepts:
        if concept.lower() not in all_wiki_lower:
            orphan_concepts.append(concept)

    # --- Stale pages ---
    stale_pages: list[str] = []
    graph_path = Path(graph_path)
    if graph_path.exists():
        try:
            graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
            # Collect all source files referenced in the graph
            graph_sources: set[str] = set()
            for node in graph_data.get("nodes", []):
                sf = node.get("source_file", "")
                if sf:
                    graph_sources.add(Path(sf).name)

            # Check each wiki page (community pages) for references to deleted sources
            for md_file in wiki_dir.glob("*.md"):
                if md_file.name == "INDEX.md" or md_file.name == "_concepts.json":
                    continue
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                # Extract source file references from the page
                page_sources = re.findall(r"\(([^)]+\.\w{1,5})\)", content)
                if page_sources:
                    code_sources = [
                        s for s in page_sources
                        if s.endswith(('.py', '.js', '.ts', '.md', '.txt'))
                    ]
                    if code_sources:
                        all_deleted = all(
                            not Path(s).exists() and Path(s).name not in graph_sources
                            for s in code_sources
                        )
                        if all_deleted:
                            stale_pages.append(md_file.name)
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "broken_links": broken_links,
        "orphan_pages": orphan_pages,
        "contradictions": contradictions,
        "orphan_concepts": orphan_concepts,
        "stale_pages": stale_pages,
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
