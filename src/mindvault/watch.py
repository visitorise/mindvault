"""File change detection and auto-pipeline trigger."""

from __future__ import annotations

import os
import time
from pathlib import Path

from mindvault.detect import EXT_MAP, SKIP_DIRS

# Code extensions that trigger immediate incremental
_CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".swift", ".kt", ".kts",
              ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".rb", ".cs"}


def _scan_mtimes(source_dir: Path) -> dict[str, float]:
    """Scan all tracked files and return {path: mtime} dict."""
    mtimes: dict[str, float] = {}
    for dirpath, dirnames, filenames in os.walk(source_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in EXT_MAP:
                continue
            full_path = os.path.join(dirpath, fname)
            try:
                mtimes[full_path] = os.path.getmtime(full_path)
            except OSError:
                continue
    return mtimes


def watch(source_dir: Path, output_dir: Path = None, debounce: int = 5) -> None:
    """Watch for file changes and auto-trigger incremental pipeline.

    Uses mtime polling (no watchdog dependency).

    Args:
        source_dir: Directory to monitor.
        output_dir: MindVault output directory.
        debounce: Polling interval in seconds.
    """
    from mindvault.pipeline import run_incremental
    from mindvault.hooks import mark_dirty

    source_dir = Path(source_dir)
    if output_dir is None:
        output_dir = source_dir / "mindvault-out"
    output_dir = Path(output_dir)

    print(f"[MindVault] Watching {source_dir} (poll every {debounce}s)")
    print("[MindVault] Press Ctrl+C to stop")

    # Initial scan
    prev_mtimes = _scan_mtimes(source_dir)

    try:
        while True:
            time.sleep(debounce)
            current_mtimes = _scan_mtimes(source_dir)

            # Find changed files
            changed_code = []
            changed_docs = []

            for path, mtime in current_mtimes.items():
                prev_mtime = prev_mtimes.get(path)
                if prev_mtime is None or mtime > prev_mtime:
                    ext = os.path.splitext(path)[1].lower()
                    if ext in _CODE_EXTS:
                        changed_code.append(path)
                    else:
                        changed_docs.append(path)

            # New files (in current but not in prev)
            # Already handled above via prev_mtime is None check

            if changed_code:
                print(f"[MindVault] Code changed: {', '.join(os.path.basename(p) for p in changed_code)}")
                try:
                    result = run_incremental(source_dir, output_dir)
                    print(f"[MindVault] Incremental update: {result}")
                except Exception as e:
                    print(f"[MindVault] Error during incremental update: {e}")

            if changed_docs:
                print(f"[MindVault] Docs changed: {', '.join(os.path.basename(p) for p in changed_docs)}")
                for doc_path in changed_docs:
                    mark_dirty(Path(doc_path), output_dir)
                print(f"[MindVault] Marked {len(changed_docs)} docs as dirty")

            prev_mtimes = current_mtimes

    except KeyboardInterrupt:
        print("\n[MindVault] Watch stopped.")
