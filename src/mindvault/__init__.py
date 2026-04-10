"""MindVault — unified knowledge management: Search + Graph + Wiki."""

__version__ = "0.1.0"

from mindvault.search import search, build_index
from mindvault.detect import detect
from mindvault.extract import extract_ast, extract_semantic
from mindvault.build import build_graph
from mindvault.cluster import cluster, score_cohesion
from mindvault.analyze import god_nodes, surprising_connections
from mindvault.wiki import generate_wiki, update_wiki
from mindvault.compile import compile
from mindvault.pipeline import run, run_incremental
from mindvault.query import query
from mindvault.hooks import install_git_hook, install_claude_hooks, mark_dirty, flush

__all__ = [
    "__version__",
    "search",
    "build_index",
    "detect",
    "extract_ast",
    "extract_semantic",
    "build_graph",
    "cluster",
    "score_cohesion",
    "god_nodes",
    "surprising_connections",
    "generate_wiki",
    "update_wiki",
    "compile",
    "run",
    "run_incremental",
    "query",
    "install_git_hook",
    "install_claude_hooks",
    "mark_dirty",
    "flush",
]
