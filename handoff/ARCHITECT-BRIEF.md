# ARCHITECT-BRIEF — MindVault

## Step 1 — Progress Indicator

**Goal**: Implement step-by-step progress indicator for `mindvault ingest` command with clean, consistent output.

**Target users**: CLI users who want visual feedback during long-running ingestion.

---

## 1.1 Create `src/mindvault/progress.py`

```python
class Progress:
    """Step-by-step progress indicator.

    All output goes to stderr to keep stdout clean for actual results.
    Automatically disabled in non-TTY environments (CI/CD).
    """

    def __init__(self, total_steps: int, enabled: bool = True):
        self.current_step = 0
        self.total_steps = total_steps
        self._enabled = enabled and sys.stderr.isatty()
        self._last_line_len = 0

    def step(self, name: str) -> None:
        """Start a new step."""
        self.current_step += 1
        if self._enabled:
            print(f"[Step {self.current_step}/{self.total_steps}] {name}...", 
                  file=sys.stderr, flush=True)

    def done(self, message: str = "") -> None:
        """Mark current step as complete."""
        if self._enabled:
            if message:
                print(f"[OK] {message}", file=sys.stderr, flush=True)
            else:
                print("[OK]", file=sys.stderr, flush=True)

    def info(self, message: str) -> None:
        """Print info message (inline, no step increment)."""
        if self._enabled:
            print(f"[INFO] {message}", file=sys.stderr, flush=True)

    def warn(self, message: str) -> None:
        """Print warning message."""
        if self._enabled:
            print(f"[WARN] {message}", file=sys.stderr, flush=True)
```

---

## 1.2 Integrate into `pipeline.py`

**Full pipeline steps (5 total):**
1. Detecting files
2. Extracting AST
3. Extracting document structure
4. Building graph & generating wiki
5. Indexing search

```python
from mindvault.progress import Progress

def run(source_dir: Path, output_dir: Path = None, **kwargs) -> dict:
    source_dir = Path(source_dir)
    if output_dir is None:
        output_dir = source_dir / "mindvault-out"
    output_dir = Path(output_dir)

    progress = Progress(total_steps=5)

    # Step 1: Detect files
    progress.step("Detecting files")
    detection = detect(source_dir)
    progress.done(f"Found {len(detection['files']['code'])} code, {len(detection['files']['document'])} doc files")

    # Step 2: Compile
    progress.step("Compiling graph")
    result = compile(source_dir, output_dir, **kwargs)
    progress.done(f"{result['nodes']} nodes, {result['edges']} edges")

    # Step 3: Index wiki pages
    progress.step("Indexing wiki")
    wiki_dir = output_dir / "wiki"
    if wiki_dir.exists():
        index_markdown(wiki_dir, output_dir / "search_index.json")
    progress.done(f"{result['wiki_pages']} pages")

    # Step 4: Index source docs
    progress.step("Indexing source docs")
    # ... indexing logic ...
    progress.done(f"{index_docs} documents indexed")

    result["index_docs"] = index_docs
    return result
```

---

## 1.3 Constraints

- Output goes to stderr, not stdout
- Disabled in non-TTY (CI/CD safe)
- All steps logged with `[Step X/N]` prefix
- Completion marked with `[OK]`
- No progress bars (simple step-based)

---

## 1.4 Acceptance Criteria

1. `mindvault ingest .` shows `[Step 1/5] Detecting files...[OK] Found X code, Y doc files`
2. Each step appears sequentially with proper numbering
3. Output goes to stderr (stdout stays clean)
4. Disabled when stderr is not a TTY
5. Existing tests pass

---

## Files to Create

- `src/mindvault/progress.py`

## Files to Modify

- `src/mindvault/pipeline.py`
