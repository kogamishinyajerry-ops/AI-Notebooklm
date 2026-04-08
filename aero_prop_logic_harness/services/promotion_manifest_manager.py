"""
Manifest Manager for Phase 5 Promotion.
Handles retrieving, validating, and mutating the lifecycle state of a PromotionManifest.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List

import ruamel.yaml

from aero_prop_logic_harness.models.promotion import PromotionManifest

logger = logging.getLogger(__name__)

class PromotionManifestManager:
    """Manages the lifecycle of PromotionManifest objects."""

    def __init__(self, demo_dir: Path):
        self.demo_dir = demo_dir.resolve()
        self.manifest_dir = self.demo_dir / ".aplh" / "promotion_manifests"
        self.yaml = ruamel.yaml.YAML()
        self.yaml.preserve_quotes = True

    def _get_manifest_path(self, manifest_id: str) -> Path:
        return self.manifest_dir / f"{manifest_id}.yaml"

    def list_manifests(self) -> List[PromotionManifest]:
        """List all available manifests."""
        manifests = []
        if not self.manifest_dir.exists():
            return manifests
            
        for file_path in self.manifest_dir.glob("*.yaml"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = self.yaml.load(f)
                manifests.append(PromotionManifest(**data))
            except Exception as e:
                logger.warning(f"Failed to load manifest {file_path}: {e}")
        return manifests

    def load_manifest(self, manifest_id: str) -> PromotionManifest:
        """Load a specific manifest by ID."""
        file_path = self._get_manifest_path(manifest_id)
        if not file_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_id}")
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = self.yaml.load(f)
        return PromotionManifest(**data)

    def save_manifest(self, manifest: PromotionManifest) -> Path:
        """Persist a manifest in the demo baseline governance area."""
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._get_manifest_path(manifest.manifest_id)
        with open(file_path, "w", encoding="utf-8") as f:
            self.yaml.dump(manifest.model_dump(exclude_none=True), f)
        return file_path

    def mark_promoted(self, manifest_id: str) -> None:
        """Mark a manifest as promoted."""
        manifest = self.load_manifest(manifest_id)
        if manifest.lifecycle_status == "promoted":
            return
            
        manifest.lifecycle_status = "promoted"
        file_path = self._get_manifest_path(manifest_id)
        with open(file_path, "w", encoding="utf-8") as f:
            self.yaml.dump(manifest.model_dump(exclude_none=True), f)

    def mark_expired(self, manifest_id: str) -> None:
        """Mark a manifest as expired."""
        manifest = self.load_manifest(manifest_id)
        if manifest.lifecycle_status == "expired":
            return
            
        manifest.lifecycle_status = "expired"
        file_path = self._get_manifest_path(manifest_id)
        with open(file_path, "w", encoding="utf-8") as f:
            self.yaml.dump(manifest.model_dump(exclude_none=True), f)
