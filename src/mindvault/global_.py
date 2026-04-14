"""Global pipeline: discover projects -> per-project pipeline -> merge -> unified output.

v0.8.1: Enhanced cross-project connections — shared dependencies, same stack,
improved name matching with noise filtering.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from mindvault.discover import discover_projects


def _extract_dependencies(proj_path: Path) -> set[str]:
    """Extract dependency names from project manifest files.

    Supports: package.json, pubspec.yaml, pyproject.toml.
    Returns a set of lowercased dependency names.
    """
    deps: set[str] = set()

    # package.json (Node.js / React / Next.js / Expo)
    pkg_json = proj_path / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
            for key in ("dependencies", "devDependencies"):
                for dep_name in data.get(key, {}):
                    deps.add(dep_name.lower())
        except (json.JSONDecodeError, OSError):
            pass

    # pubspec.yaml (Flutter/Dart)
    pubspec = proj_path / "pubspec.yaml"
    if pubspec.exists():
        try:
            import yaml
            data = yaml.safe_load(pubspec.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(data, dict):
                for key in ("dependencies", "dev_dependencies"):
                    section = data.get(key, {})
                    if isinstance(section, dict):
                        for dep_name in section:
                            deps.add(dep_name.lower())
        except Exception:
            pass

    # pyproject.toml (Python)
    pyproject = proj_path / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8", errors="ignore")
            # Simple regex extraction (avoid toml dependency)
            import re
            # Match lines like "networkx", "pytest>=8", etc. in dependencies array
            for m in re.finditer(r'"([a-zA-Z0-9_-]+)', text):
                dep_name = m.group(1).lower()
                if len(dep_name) > 2:
                    deps.add(dep_name)
        except (OSError, UnicodeDecodeError):
            pass

    # Filter out noise deps (too common to be meaningful)
    NOISE_DEPS = {
        "typescript", "eslint", "prettier", "jest", "mocha",
        "webpack", "babel", "postcss", "autoprefixer", "tailwindcss",
        "react", "react-dom",  # too common in JS ecosystem
        "flutter", "dart",  # implied by pubspec.yaml
        "python", "pip", "setuptools", "wheel", "build", "twine",
    }
    return deps - NOISE_DEPS


def _add_dependency_edges(
    projects: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> int:
    """Add cross-project edges for shared dependencies.

    Creates a virtual "dep::{name}" node for each shared dependency,
    then links project root nodes to it. This creates a natural cluster
    of projects sharing the same library.

    Returns count of new edges added.
    """
    # Collect deps per project
    proj_deps: dict[str, set[str]] = {}
    for proj in projects:
        deps = _extract_dependencies(proj["path"])
        if deps:
            proj_deps[proj["name"]] = deps

    if len(proj_deps) < 2:
        return 0

    # Find deps shared by 2+ projects (but not ALL projects — those are noise)
    dep_to_projects: dict[str, list[str]] = defaultdict(list)
    for proj_name, deps in proj_deps.items():
        for dep in deps:
            dep_to_projects[dep].append(proj_name)

    total_projects = len(proj_deps)
    edge_count = 0

    for dep, sharing_projects in dep_to_projects.items():
        if len(sharing_projects) < 2:
            continue
        # Skip if ALL projects share it (too generic)
        if len(sharing_projects) >= total_projects:
            continue

        # Create edges between projects that share this dependency
        for i in range(len(sharing_projects)):
            for j in range(i + 1, len(sharing_projects)):
                p1, p2 = sharing_projects[i], sharing_projects[j]
                # Find a representative node from each project (first module/file node)
                n1 = _find_project_root_node(p1, all_nodes)
                n2 = _find_project_root_node(p2, all_nodes)
                if n1 and n2:
                    all_edges.append({
                        "source": n1,
                        "target": n2,
                        "relation": "shares_dependency",
                        "confidence": "INFERRED",
                        "confidence_score": 0.7,
                        "weight": 0.6,
                        "metadata": dep,
                    })
                    edge_count += 1

    return edge_count


def _add_stack_edges(
    projects: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> int:
    """Add cross-project edges for projects on the same technology stack.

    Returns count of new edges added.
    """
    stack_to_projects: dict[str, list[str]] = defaultdict(list)
    for proj in projects:
        stack = proj.get("type", "Unknown")
        if stack != "Unknown":
            stack_to_projects[stack].append(proj["name"])

    edge_count = 0
    for stack, proj_names in stack_to_projects.items():
        if len(proj_names) < 2:
            continue
        for i in range(len(proj_names)):
            for j in range(i + 1, len(proj_names)):
                n1 = _find_project_root_node(proj_names[i], all_nodes)
                n2 = _find_project_root_node(proj_names[j], all_nodes)
                if n1 and n2:
                    all_edges.append({
                        "source": n1,
                        "target": n2,
                        "relation": "same_stack",
                        "confidence": "INFERRED",
                        "confidence_score": 0.8,
                        "weight": 0.7,
                        "metadata": stack,
                    })
                    edge_count += 1

    return edge_count


def _find_project_root_node(proj_name: str, all_nodes: list[dict]) -> str | None:
    """Find the best representative node for a project.

    Prefers: module-level nodes > file-level nodes > any node.
    """
    candidates = [n for n in all_nodes if n.get("project") == proj_name]
    if not candidates:
        return None

    # Prefer module/file-level nodes (they represent the project better)
    for n in candidates:
        ntype = n.get("type", "")
        if ntype in ("module", "file"):
            return n["id"]

    # Fallback: first node
    return candidates[0]["id"]


def run_global(
    root: Path, output_dir: Path = None, max_depth: int = 4, verbose: bool = False
) -> dict:
    """Discover projects under root, run pipeline on each, merge into unified graph/wiki/index.

    Args:
        root: Root directory to scan for projects.
        output_dir: Global output directory (default: ~/.mindvault/).
        max_depth: Max BFS depth for project discovery.
        verbose: If True, show progress messages. Default False.

    Returns:
        Dict with stats: projects, total_nodes, total_edges, cross_project_edges,
                         wiki_pages, index_docs.
    """
    from mindvault.pipeline import run as pipeline_run
    from mindvault.build import build_graph
    from mindvault.cluster import cluster, score_cohesion
    from mindvault.wiki import generate_wiki, _community_label
    from mindvault.export import export_json, export_html
    from mindvault.index import index_markdown

    root = Path(root).resolve()
    if output_dir is None:
        output_dir = Path.home() / ".mindvault"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Discover projects
    projects = discover_projects(root, max_depth)
    if not projects:
        return {
            "projects": 0,
            "total_nodes": 0,
            "total_edges": 0,
            "cross_project_edges": 0,
            "wiki_pages": 0,
            "index_docs": 0,
        }

    # 2. Run pipeline on each project
    project_results = []
    all_nodes = []
    all_edges = []

    for proj in projects:
        proj_output = output_dir / proj["name"]
        try:
            result = pipeline_run(proj["path"], proj_output, verbose=verbose)
        except Exception as e:
            result = {"nodes": 0, "edges": 0, "communities": 0, "wiki_pages": 0}

        # Load project graph
        graph_path = proj_output / "graph.json"
        proj_nodes = 0
        proj_edges = 0
        if graph_path.exists():
            try:
                gdata = json.loads(graph_path.read_text(encoding="utf-8"))
                raw_nodes = gdata.get("nodes", [])
                raw_links = gdata.get("links", [])

                # Prefix node IDs with project name
                for node in raw_nodes:
                    node["id"] = f"{proj['name']}/{node['id']}"
                    node["project"] = proj["name"]
                    all_nodes.append(node)

                # Prefix edge endpoints
                for link in raw_links:
                    link["source"] = f"{proj['name']}/{link['source']}"
                    link["target"] = f"{proj['name']}/{link['target']}"
                    link["project"] = proj["name"]
                    all_edges.append(link)

                proj_nodes = len(raw_nodes)
                proj_edges = len(raw_links)
            except (json.JSONDecodeError, OSError):
                pass

        project_results.append(
            {
                "name": proj["name"],
                "path": str(proj["path"]),
                "type": proj["type"],
                "nodes": proj_nodes,
                "edges": proj_edges,
            }
        )

    # 3. Add cross-project edges
    # 3a. Shared dependencies (from manifest files)
    dep_edges = _add_dependency_edges(projects, all_nodes, all_edges)

    # 3b. Same technology stack
    stack_edges = _add_stack_edges(projects, all_nodes, all_edges)

    # 3c. Shared names (improved from original — stricter filtering)
    name_to_nodes: dict[str, list[str]] = defaultdict(list)
    for node in all_nodes:
        # Extract base name: project/file_entity -> entity part
        full_id = node["id"]
        base = full_id.split("/", 1)[1] if "/" in full_id else full_id
        # Use the node label or the last part of the ID
        label = node.get("label", base)
        name_to_nodes[label].append(full_id)

    # Filter out generic/noisy labels that create meaningless cross-project edges
    GENERIC_LABELS = {
        "Props",
        "props",
        "default",
        "index",
        "main",
        "App",
        "app",
        "config",
        "Config",
        "utils",
        "helpers",
        "types",
        "constants",
        "styles",
        "theme",
        "Layout",
        "layout",
        "Root",
        "root",
        "Home",
        "home",
        "Header",
        "header",
        "Footer",
        "footer",
        "Button",
        "button",
        "Modal",
        "modal",
        "Error",
        "error",
        "Loading",
        "loading",
        "Container",
        "container",
        "module",
        "Module",
        "init",
        "__init__",
    }

    cross_edges = 0
    for label, node_ids in name_to_nodes.items():
        if len(node_ids) < 2:
            continue
        # Skip generic labels
        if label in GENERIC_LABELS or len(label) <= 3:
            continue
        # Get unique projects
        projects_set = set()
        for nid in node_ids:
            proj_name = nid.split("/", 1)[0]
            projects_set.add(proj_name)
        if len(projects_set) < 2:
            continue
        # Add edges between nodes from different projects
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                p1 = node_ids[i].split("/", 1)[0]
                p2 = node_ids[j].split("/", 1)[0]
                if p1 != p2:
                    all_edges.append(
                        {
                            "source": node_ids[i],
                            "target": node_ids[j],
                            "relation": "shares_name_with",
                            "confidence": "INFERRED",
                            "confidence_score": 0.6,
                            "weight": 0.5,
                        }
                    )
                    cross_edges += 1

    # 4. Build unified graph
    merged = {"nodes": all_nodes, "edges": all_edges}
    G = build_graph(merged)

    # 5. Cluster + wiki + export
    communities = cluster(G)
    cohesion = score_cohesion(G, communities)
    labels = {}
    for cid, members in communities.items():
        labels[cid] = _community_label(G, members)

    wiki_pages = generate_wiki(G, communities, labels, output_dir, cohesion=cohesion)
    export_json(G, communities, output_dir / "graph.json")
    export_html(G, communities, labels, output_dir / "graph.html")

    # 6. Build unified search index
    wiki_dir = output_dir / "wiki"
    index_path = output_dir / "search_index.json"
    index_docs = 0
    if wiki_dir.exists():
        index_docs = index_markdown(wiki_dir, index_path)

    # 6b. Also index Claude Code memory files if they exist
    from mindvault.pipeline import _index_source_docs

    memory_patterns = [
        Path.home() / ".claude" / "projects",
    ]
    for mem_root in memory_patterns:
        if mem_root.exists():
            for memory_dir in mem_root.rglob("memory"):
                if memory_dir.is_dir():
                    md_files = [
                        str(f.relative_to(memory_dir)) for f in memory_dir.glob("*.md")
                    ]
                    if md_files:
                        _index_source_docs(memory_dir, md_files, index_path)
                        index_docs += len(md_files)

    # 7. Save projects manifest
    manifest = {
        "root": str(root),
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "projects": project_results,
    }
    (output_dir / "projects.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "projects": len(projects),
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "cross_project_edges": cross_edges + dep_edges + stack_edges,
        "wiki_pages": wiki_pages,
        "index_docs": index_docs,
    }


def run_global_incremental(root: Path, output_dir: Path = None) -> dict:
    """Incremental global update: reload projects.json, run incremental on each.

    Args:
        root: Root directory.
        output_dir: Global output directory (default: ~/.mindvault/).

    Returns:
        Dict with update stats.
    """
    from mindvault.pipeline import run_incremental

    root = Path(root).resolve()
    if output_dir is None:
        output_dir = Path.home() / ".mindvault"
    output_dir = Path(output_dir)

    manifest_path = output_dir / "projects.json"
    if not manifest_path.exists():
        # No prior build — run full
        return run_global(root, output_dir)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return run_global(root, output_dir)

    # Re-discover to find new/removed projects
    current_projects = discover_projects(root)
    current_names = {p["name"] for p in current_projects}
    known_names = {p["name"] for p in manifest.get("projects", [])}

    new_projects = current_names - known_names
    removed_projects = known_names - current_names

    # Run incremental on existing projects
    updated = 0
    for proj in current_projects:
        proj_output = output_dir / proj["name"]
        if proj["name"] in new_projects:
            # New project — full pipeline
            from mindvault.pipeline import run as pipeline_run

            try:
                pipeline_run(proj["path"], proj_output)
                updated += 1
            except Exception:
                pass
        else:
            # Existing — incremental
            try:
                result = run_incremental(proj["path"], proj_output)
                if result.get("changed", 0) > 0:
                    updated += 1
            except Exception:
                pass

    # Clean up removed projects
    import shutil

    for name in removed_projects:
        removed_dir = output_dir / name
        if removed_dir.exists():
            shutil.rmtree(removed_dir)

    # Update manifest
    project_results = []
    for proj in current_projects:
        graph_path = output_dir / proj["name"] / "graph.json"
        nodes = 0
        if graph_path.exists():
            try:
                gdata = json.loads(graph_path.read_text(encoding="utf-8"))
                nodes = len(gdata.get("nodes", []))
            except (json.JSONDecodeError, OSError):
                pass
        project_results.append(
            {
                "name": proj["name"],
                "path": str(proj["path"]),
                "type": proj["type"],
                "nodes": nodes,
            }
        )

    manifest = {
        "root": str(root),
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "projects": project_results,
    }
    (output_dir / "projects.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "updated": updated,
        "new_projects": len(new_projects),
        "removed_projects": len(removed_projects),
        "total_projects": len(current_projects),
    }
