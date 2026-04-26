"""W-V43-12: cold-cache fail-fast guard.

Closes the cold-cache confusion path identified in W-V43-10 §6:
- Pre-Window-2 closeout, a fresh worktree with no model cache produced 8
  errors in the C2 sentinel + 1 failure in the R-2604 sentinel, all
  cascading from `RuntimeError: Embedding model 'BAAI/bge-large-zh-v1.5'
  was not found in the local cache.`
- The C2 / R-2604 stack traces were noisy and slow to interpret. An
  executor unfamiliar with the project would investigate retrieval-quality
  drift before realizing the root cause was a missing model download.

This file is named `test_aa_*` so pytest's alphabetic test ordering picks
it up before `test_retrieval_quality_regression.py` and
`test_r2604_isolation_sentinel.py`. When the cache is missing, this
single test fails first with an explicit remediation instruction; the
downstream test failures still happen but the operator immediately knows
the root cause.

The guard does **not** modify `conftest.py` (the R-2604-01 lesson:
conftest pre-imports already shape test isolation; adding more there is
high-risk for cross-test interactions). Filesystem-only check, no
imports of `sentence_transformers` / `core.retrieval.embeddings` so the
guard runs in milliseconds and does not pollute import order.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Mirrors core/retrieval/embeddings.py default; if the project ever changes
# the default, this constant should track it. The C2 sentinel and R-2604
# sentinel both depend on this exact model.
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"


def _candidate_cache_roots() -> list[Path]:
    """Candidate roots to search for a HuggingFace-format cached model.

    Returns a list because different env-var combinations point at
    different physical caches and the model may live in any one of them.
    The check passes if ANY candidate contains the model.

    Precedence covers:
      - `HF_HUB_CACHE` / `HUGGINGFACE_HUB_CACHE`: direct hub cache dir.
      - `TRANSFORMERS_CACHE`: forwarded as `cache_dir` directly by
        transformers (NO `/hub` append, per Codex round 4 P2).
      - `HF_HOME`: root dir; hub cache is at `HF_HOME/hub`.
      - `SENTENCE_TRANSFORMERS_HOME` (Codex round 5 P2): in this repo's
        Docker images this is set to the same path as `HF_HOME`, but
        elsewhere it can be the only configured cache. SentenceTransformer
        stores HF-hosted models under the same `models--{org}--{name}/`
        layout there.
      - Default: `~/.cache/huggingface/hub`.
    """
    roots: list[Path] = []

    direct = (
        os.getenv("HF_HUB_CACHE")
        or os.getenv("HUGGINGFACE_HUB_CACHE")
        or os.getenv("TRANSFORMERS_CACHE")
    )
    if direct:
        roots.append(Path(direct))

    hf_home = os.getenv("HF_HOME")
    if hf_home:
        roots.append(Path(hf_home) / "hub")

    st_home = os.getenv("SENTENCE_TRANSFORMERS_HOME")
    if st_home:
        # Some setups put the HF-format cache directly under this dir;
        # others put it under `<st_home>/hub`. Check both.
        roots.append(Path(st_home))
        roots.append(Path(st_home) / "hub")

    roots.append(Path.home() / ".cache" / "huggingface" / "hub")

    return roots


def _hf_cache_root() -> Path:
    """Primary cache root for human-facing error messages.

    The actual cache check uses `_candidate_cache_roots()` to allow any
    of the configured caches to satisfy the requirement.
    """
    return _candidate_cache_roots()[0]


def _is_offline_mode() -> bool:
    """Mirror `core.retrieval.embeddings.should_use_local_files_only()`
    semantics WITHOUT importing that module (avoids dragging
    `sentence_transformers` into preflight import order)."""
    if os.getenv("EMBEDDING_LOCAL_FILES_ONLY"):
        return os.getenv("EMBEDDING_LOCAL_FILES_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}
    if os.getenv("TRANSFORMERS_OFFLINE", "").strip() == "1":
        return True
    if os.getenv("HF_HUB_OFFLINE", "").strip() == "1":
        return True
    if os.getenv("ENVIRONMENT", "").strip().lower() == "production":
        return True
    return False


def _model_dir_for(model_id: str, cache_root: Path) -> Path:
    """HF caches layout: `models--{org}--{name}/`."""
    safe_id = model_id.replace("/", "--")
    return cache_root / f"models--{safe_id}"


def _cache_has_model(model_id: str, cache_root: Path) -> bool:
    """A cached model has a non-empty `snapshots/` subtree."""
    model_dir = _model_dir_for(model_id, cache_root)
    if not model_dir.is_dir():
        return False
    snapshots = model_dir / "snapshots"
    if not snapshots.is_dir():
        return False
    for entry in snapshots.iterdir():
        if entry.is_dir() and any(entry.iterdir()):
            return True
    return False


def test_embedding_model_cache_present():
    """Fail fast with a clear message if the embedding model is missing.

    Cache check runs **unconditionally** because the C2 retrieval sentinel
    fixtures (`eval_corpus_setup` in `tests/conftest.py` and the
    `retriever` fixture in `tests/test_retrieval_quality_regression.py`)
    set `TRANSFORMERS_OFFLINE=1` *during their own setup*, after this
    preflight would have run. A skip-based guard (Codex W-V43-12 round 2,
    P2) misses that exact case — the very scenario W-V43-12 was added to
    explain — so we always require the cache to be present.

    The error message branches on whether the operator already opted into
    offline mode at the shell level, so they get a remediation tailored
    to their setup.
    """
    model_id = os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_EMBEDDING_MODEL)

    # Codex W-V43-12 round 6 (P2): support vendored-model deployments where
    # EMBEDDING_MODEL_NAME is a local filesystem path. Distinguish from an
    # HF org/name like `BAAI/bge-large-zh-v1.5` by requiring a path-shaped
    # prefix (absolute, `~`, or relative `./`/`..`). If the path exists as
    # a populated directory, SentenceTransformer can load it directly.
    looks_like_path = (
        model_id.startswith("/")
        or model_id.startswith("~")
        or model_id.startswith("./")
        or model_id.startswith("../")
    )
    if looks_like_path:
        candidate_path = Path(model_id).expanduser()
        if candidate_path.is_dir() and any(candidate_path.iterdir()):
            return

    candidates = _candidate_cache_roots()
    if any(_cache_has_model(model_id, root) for root in candidates):
        return

    # Codex W-V43-12 round 7 (P3): if the model name is a local path, the
    # `pre_download_models.py` script (which fills the HF cache) is not the
    # right remediation. Tell the operator to populate the path directly.
    if looks_like_path:
        candidate_path = Path(model_id).expanduser()
        pytest.fail(
            f"\n\n"
            f"  W-V43-12 preflight: EMBEDDING_MODEL_NAME is a local path\n"
            f"  ({model_id}) but the directory is missing or empty:\n"
            f"      {candidate_path}\n\n"
            f"  Vendored-model deployments must place the SentenceTransformer\n"
            f"  files (config.json, pytorch_model.bin or model.safetensors,\n"
            f"  modules.json, etc.) at that path BEFORE pytest runs.\n"
            f"  `scripts/pre_download_models.py` fills the HuggingFace hub\n"
            f"  cache, not your vendored directory; copy or rsync the model\n"
            f"  files into the configured path manually.\n"
        )

    cache_root = candidates[0]
    searched = "\n".join(f"      - {root}" for root in candidates)

    common_remediation = (
        "  To unblock, run:\n\n"
        "      python3 scripts/pre_download_models.py\n\n"
        "  The model is ~1.8 GB and is downloaded once. The C2 retrieval\n"
        "  sentinel and the R-2604 isolation sentinel both depend on it.\n"
    )

    if _is_offline_mode():
        pytest.fail(
            f"\n\n"
            f"  W-V43-12 preflight: offline mode is enabled "
            f"(TRANSFORMERS_OFFLINE/HF_HUB_OFFLINE/EMBEDDING_LOCAL_FILES_ONLY/ENVIRONMENT=production),\n"
            f"  but the embedding model '{model_id}' is NOT in any of the\n"
            f"  candidate HuggingFace cache locations:\n"
            f"{searched}\n\n"
            f"  In strict CI the cache must be populated during the image build,\n"
            f"  not at test time.\n\n"
            f"  Codex W-V43-12 round 3 (P2): the pre-download script honors the\n"
            f"  same offline flags, so in this shell you must unset them for the\n"
            f"  download to be allowed to fetch from HuggingFace:\n\n"
            f"      env -u TRANSFORMERS_OFFLINE -u HF_HUB_OFFLINE \\\n"
            f"          -u EMBEDDING_LOCAL_FILES_ONLY -u RERANKER_LOCAL_FILES_ONLY \\\n"
            f"          python3 scripts/pre_download_models.py\n\n"
            f"  Once the cache is populated, re-enable offline mode and rerun pytest.\n"
            f"  Alternative: rebuild the image so its build step pre-populates the cache\n"
            f"  before TRANSFORMERS_OFFLINE=1 is baked in.\n"
        )

    pytest.fail(
        f"\n\n"
        f"  W-V43-12 preflight: the embedding model '{model_id}' is NOT in any\n"
        f"  of the candidate HuggingFace cache locations:\n"
        f"{searched}\n\n"
        f"  The retrieval-quality and R-2604 isolation tests run their fixtures\n"
        f"  with TRANSFORMERS_OFFLINE=1 (set via setdefault), so even in a\n"
        f"  network-online shell those tests will fail with cascade errors\n"
        f"  unless the cache is pre-populated.\n\n"
        f"{common_remediation}"
    )
