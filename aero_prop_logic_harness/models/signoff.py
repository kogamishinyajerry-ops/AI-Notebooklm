"""
Signoff entry data model (Phase 3).

Provides a structured Pydantic schema for T2 signoff entries
stored in `.aplh/review_signoffs.yaml`.

Phase 3 additions:
  - Parameterised reviewer (no longer hardcoded)
  - scenario_id and run_id for audit correlation
  - baseline_scope constrained to Literal['demo-scale']
  - timestamp validated as ISO 8601 format

Phase 3-1 hardening (review fix):
  - baseline_scope: str → Literal['demo-scale']
  - timestamp: str → str with ISO 8601 format validation
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SignoffEntry(BaseModel):
    """Structured signoff record for T2 manual review resolutions.

    Signoff entries are persisted in baseline-local
    ``.aplh/review_signoffs.yaml`` and are excluded from artifact
    schema validation by the shared traversal rules.

    Constraints (Phase 3-1 hardened):
      - ``baseline_scope`` must be exactly ``"demo-scale"``
      - ``timestamp`` must be a valid ISO 8601 datetime string
      - ``extra="forbid"`` prevents uncontrolled schema drift
    """
    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(
        description="ISO 8601 timestamp of the signoff (e.g., 2026-04-04T12:00:00Z)",
    )
    reviewer: str = Field(
        description="Identity of the human reviewer who approved this signoff",
    )
    resolution: str = Field(
        description="Free-text resolution describing the manual review decision",
    )
    scenario_id: Optional[str] = Field(
        default=None,
        description="ID of the scenario that triggered the T2 block (e.g., SCENARIO-DEMO)",
    )
    run_id: Optional[str] = Field(
        default=None,
        description="Unique run identifier for trace correlation (e.g., RUN-3A7F1BC9D2E4)",
    )
    baseline_scope: Literal["demo-scale"] = Field(
        default="demo-scale",
        description="Scope of the baseline this signoff applies to. "
                    "Phase 3-1 only permits 'demo-scale'.",
    )

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_iso8601(cls, v: str) -> str:
        """Ensure timestamp is a parseable ISO 8601 datetime string.

        Requires both date AND time components (must contain 'T').
        Date-only strings like '2026-04-04' are rejected because
        a signoff without a time component is not auditable.
        """
        if "T" not in v:
            raise ValueError(
                f"timestamp must be a full ISO 8601 datetime (with 'T' separator), "
                f"got date-only: {v!r}"
            )
        try:
            # Strip trailing 'Z' and parse; Python's fromisoformat
            # handles the standard ISO 8601 formats.
            normalised = v.replace("Z", "+00:00") if v.endswith("Z") else v
            datetime.fromisoformat(normalised)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"timestamp must be a valid ISO 8601 datetime string, got: {v!r}"
            ) from exc
        return v

