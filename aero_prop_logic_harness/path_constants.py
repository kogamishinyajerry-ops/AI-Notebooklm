"""
Shared path constants and directory traversal rules for APLH.

All CLI commands MUST use these helpers to ensure a consistent view
of which files are artifacts and which are internal control metadata.
"""

from pathlib import Path
from typing import Iterator

# ── Internal control directories ──────────────────────────────────────
# These are NEVER artifact directories.  They contain control metadata
# (signoff records, gate status, etc.) and must be excluded from every
# artifact-scanning code path.
CONTROL_DIR_NAMES: frozenset[str] = frozenset({".aplh"})

# ── Formal baseline root ─────────────────────────────────────────────
# The formal baseline root is the ONLY directory against which a
# `freeze-complete` signoff is valid.  It is resolved relative to the
# repository root (the directory that contains `pyproject.toml`).
FORMAL_BASELINE_RELATIVE = Path("artifacts")


def _find_project_root() -> Path:
    """Walk upward from this file to locate the project root (contains pyproject.toml)."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").is_file():
            return current
        current = current.parent
    # Fallback: return cwd (e.g. for tests that run from the repo root)
    return Path.cwd()


def get_formal_baseline_root() -> Path:
    """Return the resolved absolute path of the formal baseline root."""
    return (_find_project_root() / FORMAL_BASELINE_RELATIVE).resolve()


def is_formal_baseline_root(target_dir: Path) -> bool:
    """Return True if *target_dir* resolves to the formal baseline root."""
    return target_dir.resolve() == get_formal_baseline_root()


def is_control_dir(rel_parts: tuple[str, ...]) -> bool:
    """Return True if any component of *rel_parts* is a control directory."""
    return bool(CONTROL_DIR_NAMES.intersection(rel_parts))


def iter_artifact_yamls(root: Path) -> Iterator[Path]:
    """
    Yield every artifact YAML file under *root*, applying the shared
    exclusion rules that ALL CLI commands must respect:

    1. Skip control-metadata directories (.aplh/).
    2. Skip template files (*.template.yaml).
    3. When *root* is NOT inside an examples subtree, also skip any
       ``examples/`` subtree underneath it (baseline isolation).
    """
    root = Path(root)
    if not root.is_dir():
        return

    for yaml_file in root.glob("**/*.yaml"):
        # Template files are never artifacts
        if yaml_file.name.endswith(".template.yaml"):
            continue

        try:
            rel_parts = yaml_file.relative_to(root).parts
        except ValueError:
            continue

        # Control directories are never artifacts
        if is_control_dir(rel_parts):
            continue

        # Baseline isolation: if the scan root is NOT inside an examples
        # path itself, skip any examples/ subtree found underneath.
        if "examples" in rel_parts:
            continue

        yield yaml_file
