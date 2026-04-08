"""
Audit Logger for Phase 5 Promotion.
Records ledger entries for successful physical file promotions to formal.
"""
from __future__ import annotations

import logging
from pathlib import Path

import ruamel.yaml

from aero_prop_logic_harness.models.promotion import PromotionAuditRecord

logger = logging.getLogger(__name__)

class PromotionAuditLogger:
    """Records immutable audit ledger of physical migrations inside formal dir."""
    
    def __init__(self, formal_dir: Path):
        self.formal_dir = formal_dir.resolve()
        self.aplh_dir = self.formal_dir / ".aplh"
        self.log_file = self.aplh_dir / "formal_promotions_log.yaml"
        self.yaml = ruamel.yaml.YAML()
        self.yaml.preserve_quotes = True

    def initialize_log(self) -> None:
        if not self.aplh_dir.exists():
            self.aplh_dir.mkdir(parents=True, exist_ok=True)
            
        if not self.log_file.exists():
            with open(self.log_file, "w", encoding="utf-8") as f:
                self.yaml.dump([], f)

    def append_record(self, record: PromotionAuditRecord) -> None:
        """Append an audit record to the log."""
        self.initialize_log()
        
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                records = self.yaml.load(f) or []
        except Exception:
            records = []
            
        records.append(record.model_dump(exclude_none=True))
        
        with open(self.log_file, "w", encoding="utf-8") as f:
            self.yaml.dump(records, f)
