"""SHA256 file cache — only reprocess changed files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

CACHE_FILENAME = ".mindvault_hashes.json"


def _load_cache(cache_dir: Path) -> dict[str, str]:
    cache_file = cache_dir / CACHE_FILENAME
    if cache_file.exists():
        with open(cache_file, "r") as f:
            return json.load(f)
    return {}


def _save_cache(cache_dir: Path, data: dict[str, str]) -> None:
    cache_file = cache_dir / CACHE_FILENAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)


def compute_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file (binary mode).

    Args:
        file_path: Path to the file.

    Returns:
        Hex digest string.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def is_dirty(file_path: Path, cache_dir: Path) -> bool:
    """Check if a file has changed since last processing.

    Args:
        file_path: Path to check.
        cache_dir: Directory containing hash cache.

    Returns:
        True if file is new or changed.
    """
    cache = _load_cache(cache_dir)
    key = str(file_path)
    current_hash = compute_hash(file_path)
    return cache.get(key) != current_hash


def update_cache(file_path: Path, cache_dir: Path) -> None:
    """Update the cache entry for a file after processing.

    Args:
        file_path: Path to the processed file.
        cache_dir: Directory containing hash cache.
    """
    cache = _load_cache(cache_dir)
    key = str(file_path)
    cache[key] = compute_hash(file_path)
    _save_cache(cache_dir, cache)


def get_dirty_files(files: list[Path], cache_dir: Path) -> list[Path]:
    """Return only the files that have changed since last cache update.

    Args:
        files: List of file paths to check.
        cache_dir: Directory containing hash cache.

    Returns:
        List of dirty (new or changed) file paths.
    """
    return [f for f in files if is_dirty(f, cache_dir)]
