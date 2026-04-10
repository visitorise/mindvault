"""CLI entry point for MindVault."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from mindvault import __version__


def cmd_install(args) -> None:
    """mindvault install — skill registration + git hook installation."""
    from mindvault.hooks import install_git_hook

    project_root = Path(args.path).resolve()
    results = []

    # 1. Copy SKILL.md to ~/.claude/skills/mindvault/
    skill_src = Path(__file__).parent.parent.parent / "skill" / "SKILL.md"
    skill_dst_dir = Path.home() / ".claude" / "skills" / "mindvault"
    if skill_src.exists():
        skill_dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_src, skill_dst_dir / "SKILL.md")
        results.append(f"  Skill: copied to {skill_dst_dir}/SKILL.md")
    else:
        results.append("  Skill: SKILL.md not found (skip)")

    # 2. Register in ~/.claude/CLAUDE.md (if not already there)
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    marker = "mindvault"
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        if marker not in content.lower():
            content += "\n\n## MindVault Skill\n\nUse `/mindvault` skill for knowledge graph queries.\n"
            claude_md.write_text(content, encoding="utf-8")
            results.append("  CLAUDE.md: mindvault skill registered")
        else:
            results.append("  CLAUDE.md: already registered (skip)")
    else:
        results.append("  CLAUDE.md: file not found (skip)")

    # 3. Install git hook if in a git repo
    if (project_root / ".git").exists():
        ok = install_git_hook(project_root)
        if ok:
            results.append("  Git hook: post-commit hook installed")
        else:
            results.append("  Git hook: installation failed")
    else:
        results.append("  Git hook: not a git repo (skip)")

    print("MindVault installed:")
    for r in results:
        print(r)


def cmd_query(args) -> None:
    """mindvault query "question" — 3-layer query."""
    from mindvault.query import query

    output_dir = Path(args.output_dir) if hasattr(args, "output_dir") and args.output_dir else Path("mindvault-out")

    if not output_dir.exists():
        print(f"No MindVault data found at {output_dir}. Run `mindvault` or `/mindvault .` first.")
        sys.exit(1)

    result = query(args.question, output_dir, mode=args.mode, budget=args.budget)

    # Format output
    print(f"\n=== Search Results (0 tokens) ===")
    if result["search_results"]:
        for i, sr in enumerate(result["search_results"], 1):
            print(f"  {i}. [{sr['title']}] (score: {sr['score']:.2f})")
            print(f"     {sr['snippet'][:80]}")
    else:
        print("  (no results)")

    print(f"\n=== Graph Context ===")
    gc = result["graph_context"]
    if gc["matched_nodes"]:
        print(f"  Matched: {', '.join(gc['matched_nodes'][:10])}")
        if len(gc["matched_nodes"]) > 10:
            print(f"  ... and {len(gc['matched_nodes']) - 10} more")
    else:
        print("  (no matching nodes)")

    if gc["neighbors"]:
        # Show a few neighbor relationships
        for edge in gc["edges"][:5]:
            src = edge.get("source", "?")
            tgt = edge.get("target", "?")
            rel = edge.get("relation", "->")
            print(f"  {src} --{rel}--> {tgt}")
        if len(gc["edges"]) > 5:
            print(f"  ... and {len(gc['edges']) - 5} more edges")

    tokens = result["tokens_used"]
    wiki_len = len(result["wiki_context"])
    print(f"\n=== Wiki Context (est. ~{tokens} tokens) ===")
    if wiki_len > 0:
        # Show first 500 chars
        preview = result["wiki_context"][:500]
        if wiki_len > 500:
            preview += f"\n... ({wiki_len - 500} more chars)"
        print(preview)
    else:
        print("  (no wiki context)")

    print(f"\nTotal tokens used: {tokens}")


def cmd_ingest(args) -> None:
    """mindvault ingest <path> — add new source and run incremental update."""
    from mindvault.pipeline import run_incremental

    source_path = Path(args.path).resolve()
    output_dir = Path("mindvault-out")

    if not source_path.exists():
        print(f"Error: {source_path} does not exist.")
        sys.exit(1)

    print(f"Ingesting: {source_path}")
    result = run_incremental(source_path, output_dir)
    print(f"Result: {result}")


def cmd_lint(args) -> None:
    """mindvault lint — wiki + graph consistency check."""
    from mindvault.lint import lint_wiki, lint_graph

    output_dir = Path(args.path) if args.path != ".mindvault" else Path("mindvault-out")
    wiki_dir = output_dir / "wiki"
    graph_path = output_dir / "graph.json"

    if not output_dir.exists():
        print(f"No MindVault data found at {output_dir}. Run `mindvault` or `/mindvault .` first.")
        sys.exit(1)

    print("=== Wiki Lint ===")
    wiki_result = lint_wiki(wiki_dir, graph_path)
    print(f"  Total pages: {wiki_result['total_pages']}")
    print(f"  Broken links: {len(wiki_result['broken_links'])}")
    if wiki_result["broken_links"][:5]:
        for bl in wiki_result["broken_links"][:5]:
            print(f"    - {bl['file']}: [[{bl['link']}]]")
        if len(wiki_result["broken_links"]) > 5:
            print(f"    ... and {len(wiki_result['broken_links']) - 5} more")
    print(f"  Orphan pages: {len(wiki_result['orphan_pages'])}")
    if wiki_result["orphan_pages"][:5]:
        for op in wiki_result["orphan_pages"][:5]:
            print(f"    - {op}")

    print("\n=== Graph Lint ===")
    graph_result = lint_graph(graph_path)
    print(f"  Total nodes: {graph_result['total_nodes']}")
    print(f"  Total edges: {graph_result['total_edges']}")
    print(f"  Isolated nodes: {len(graph_result['isolated_nodes'])}")
    print(f"  Ambiguous edges: {graph_result['ambiguous_edges']}")


def cmd_status(args) -> None:
    """mindvault status — show current MindVault status."""
    import os

    output_dir = Path("mindvault-out")
    if not output_dir.exists():
        print("No MindVault data found. Run `mindvault` or `/mindvault .` first.")
        return

    graph_path = output_dir / "graph.json"
    wiki_dir = output_dir / "wiki"
    index_path = output_dir / "search_index.json"

    print("=== MindVault Status ===")

    if graph_path.exists():
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = len(data.get("nodes", []))
        edges = len(data.get("links", []))
        communities = len(data.get("communities", {}))
        mtime = os.path.getmtime(graph_path)
        from datetime import datetime
        last_updated = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  Graph: {nodes} nodes, {edges} edges, {communities} communities")
        print(f"  Last updated: {last_updated}")
    else:
        print("  Graph: not built")

    if wiki_dir.exists():
        wiki_pages = len(list(wiki_dir.glob("*.md")))
        print(f"  Wiki: {wiki_pages} pages")
    else:
        print("  Wiki: not built")

    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        doc_count = idx.get("doc_count", 0)
        print(f"  Search index: {doc_count} documents")
    else:
        print("  Search index: not built")


def cmd_watch(args) -> None:
    """mindvault watch — start file watcher."""
    from mindvault.watch import watch

    source_dir = Path(args.path).resolve()
    output_dir = source_dir / "mindvault-out"

    watch(source_dir, output_dir, debounce=5)


def cmd_update(args) -> None:
    """mindvault update — run incremental pipeline (for git hook)."""
    from mindvault.pipeline import run_incremental

    source_dir = Path(".").resolve()
    output_dir = Path("mindvault-out")

    if not output_dir.exists():
        if not getattr(args, "quiet", False):
            print("No MindVault data found. Skipping update.")
        return

    result = run_incremental(source_dir, output_dir)
    if not getattr(args, "quiet", False):
        print(f"MindVault update: {result}")


def cmd_mark_dirty(args) -> None:
    """mindvault mark-dirty <path> — mark file as needing re-extraction."""
    from mindvault.hooks import mark_dirty

    file_path = Path(args.file_path).resolve()
    output_dir = Path("mindvault-out")
    mark_dirty(file_path, output_dir)


def cmd_flush(args) -> None:
    """mindvault flush — process all dirty files."""
    from mindvault.hooks import flush

    output_dir = Path("mindvault-out")
    result = flush(output_dir)
    print(f"Flush result: {result}")


def main() -> None:
    """CLI entry point. Subcommands: install, query, ingest, lint, status, watch."""
    parser = argparse.ArgumentParser(
        prog="mindvault",
        description="MindVault — unified knowledge management: Search + Graph + Wiki",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mindvault {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # install
    sub_install = subparsers.add_parser("install", help="Install hooks and initialize MindVault in a project")
    sub_install.add_argument("path", nargs="?", default=".", help="Project root path")

    # query
    sub_query = subparsers.add_parser("query", help="Query the knowledge graph")
    sub_query.add_argument("question", help="Question to answer")
    sub_query.add_argument("--mode", default="bfs", choices=["bfs", "dfs", "hybrid"], help="Traversal mode")
    sub_query.add_argument("--budget", type=int, default=2000, help="Token budget")
    sub_query.add_argument("--output-dir", default=None, help="MindVault output directory")

    # ingest
    sub_ingest = subparsers.add_parser("ingest", help="Ingest files into the knowledge graph")
    sub_ingest.add_argument("path", nargs="?", default=".", help="Directory to ingest")
    sub_ingest.add_argument("--incremental", action="store_true", help="Only process changed files")

    # lint
    sub_lint = subparsers.add_parser("lint", help="Check wiki consistency")
    sub_lint.add_argument("path", nargs="?", default=".mindvault", help="Wiki output directory")

    # status
    sub_status = subparsers.add_parser("status", help="Show MindVault status for current project")

    # watch
    sub_watch = subparsers.add_parser("watch", help="Watch for file changes and auto-update")
    sub_watch.add_argument("path", nargs="?", default=".", help="Directory to watch")

    # update (for git hook)
    sub_update = subparsers.add_parser("update", help="Run incremental update (git hook)")
    sub_update.add_argument("--quiet", action="store_true", help="Suppress output")

    # mark-dirty (for Claude Code hook)
    sub_mark_dirty = subparsers.add_parser("mark-dirty", help="Mark a file as dirty")
    sub_mark_dirty.add_argument("file_path", help="File path to mark as dirty")

    # flush (for Claude Code hook)
    sub_flush = subparsers.add_parser("flush", help="Process all dirty files")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "install": cmd_install,
        "query": cmd_query,
        "ingest": cmd_ingest,
        "lint": cmd_lint,
        "status": cmd_status,
        "watch": cmd_watch,
        "update": cmd_update,
        "mark-dirty": cmd_mark_dirty,
        "flush": cmd_flush,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"mindvault {args.command}: not yet implemented")
        sys.exit(1)


if __name__ == "__main__":
    main()
