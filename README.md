# MindVault

Turn any folder into a searchable knowledge base.

Three-layer architecture: **Search** (BM25, zero tokens) + **Graph** (tree-sitter AST + NetworkX) + **Wiki** (auto-generated community pages).

## Install

```bash
pip install mindvault
mindvault install
```

`mindvault install` registers the `/mindvault` skill in Claude Code and installs a git post-commit hook for automatic updates.

## Quick Start

```bash
# Build the knowledge base from your project
mindvault ingest .

# Ask a question (3-layer: search -> graph -> wiki)
mindvault query "How does authentication work?"

# Check the current state
mindvault status
```

Or use as a Claude Code skill:

```
/mindvault .
/mindvault query "How does the pipeline work?"
```

## How It Works

```
Source Files
    |
    v
[1. Detect] -- find code/doc files, count words
    |
    v
[2. Extract] -- tree-sitter AST -> nodes (functions, classes, modules) + edges (calls, imports)
    |
    v
[3. Build Graph] -- NetworkX DiGraph, filter dangling edges
    |
    v
[4. Cluster] -- greedy modularity communities
    |
    v
[5. Wiki] -- one markdown page per community, INDEX.md entry point
    |
    v
[6. Index] -- BM25 inverted index over wiki pages
    |
    v
  mindvault-out/
    graph.json          raw graph data
    graph.html          interactive vis.js visualization
    GRAPH_REPORT.md     audit report
    wiki/INDEX.md       wiki entry point
    wiki/*.md           community pages
    search_index.json   BM25 index
```

**Query flow** (3 layers):

| Layer | What | Tokens |
|-------|------|--------|
| Search | BM25 over wiki pages | 0 (local computation) |
| Graph | BFS/DFS traversal from matched nodes | ~100 (edge descriptions) |
| Wiki | Read matched community pages up to budget | ~800 (configurable) |
| **Total** | | **~900** vs 60,000+ raw |

## Commands

| Command | Description |
|---------|-------------|
| `mindvault ingest <path>` | Build or incrementally update the knowledge base |
| `mindvault query "<question>"` | 3-layer query (BM25 + graph + wiki) |
| `mindvault query "<q>" --mode dfs` | DFS traversal (trace specific chains) |
| `mindvault status` | Show node/edge/community/wiki counts |
| `mindvault lint` | Check wiki + graph consistency |
| `mindvault install` | Register skill + git hook |
| `mindvault watch` | Auto-update on file changes |
| `mindvault update` | Incremental update (used by git hook) |
| `mindvault mark-dirty <file>` | Flag a file for re-extraction |
| `mindvault flush` | Process all dirty files |

## Token Savings

| Scenario | Raw file reading | MindVault query | Savings |
|----------|-----------------|-----------------|---------|
| Small project (20 files) | ~15,000 tokens | ~900 tokens | 17x |
| Medium project (100 files) | ~60,000 tokens | ~900 tokens | 67x |
| Large project (500 files) | ~300,000 tokens | ~900 tokens | 333x |

Query budget is configurable via `--budget` (default: 2000 tokens).

## Requirements

- Python 3.10+
- No external API calls (all processing is local)

## Dependencies

- `networkx` -- graph operations and community detection
- `tree-sitter` + language grammars -- AST extraction for Python, TypeScript, JavaScript, Go, Rust, Java, Swift, Kotlin, C, C++, Ruby, C#

## License

MIT
