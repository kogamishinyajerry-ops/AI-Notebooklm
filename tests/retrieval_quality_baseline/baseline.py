"""
V4.1-T1: Baseline Configuration
================================
Exposes the baseline metrics as a typed dataclass for clean imports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


BASELINE_JSON = Path(__file__).parent / "baseline.json"


@dataclass(frozen=True)
class BaselineConfig:
    """Frozen snapshot of the baseline metrics for regression comparison."""

    mrr_at_5: float
    ndcg_at_5: float
    recall_at_5: float
    hit_rate: float
    regression_threshold_pct: float
    baseline_commit: str
    recorded_at: str
    config_top_k: int

    @classmethod
    def load(cls, path: Path = BASELINE_JSON) -> "BaselineConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            mrr_at_5=data["metrics"]["mrr_at_5"],
            ndcg_at_5=data["metrics"]["ndcg_at_5"],
            recall_at_5=data["metrics"]["recall_at_5"],
            hit_rate=data["metrics"]["hit_rate"],
            regression_threshold_pct=data["regression_threshold_pct"],
            baseline_commit=data["baseline_commit"],
            recorded_at=data["recorded_at"],
            config_top_k=data["config"]["top_k"],
        )

    def mrr_threshold(self) -> float:
        return self.mrr_at_5 * (1.0 - self.regression_threshold_pct / 100.0)

    def ndcg_threshold(self) -> float:
        return self.ndcg_at_5 * (1.0 - self.regression_threshold_pct / 100.0)

    def recall_threshold(self) -> float:
        return self.recall_at_5 * (1.0 - self.regression_threshold_pct / 100.0)


# Pre-loaded singleton used by test_retrieval_quality_regression.py
_baseline: BaselineConfig | None = None


def get_baseline() -> BaselineConfig:
    """Lazily load and cache the baseline config."""
    global _baseline
    if _baseline is None:
        _baseline = BaselineConfig.load()
    return _baseline
