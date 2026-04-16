"""
services/ingestion/chunker.py
==============================
S-22: Added configurable chunk overlap.

``CHUNK_OVERLAP`` tokens (approx chars/4) of trailing context are prepended
to each new chunk so cross-boundary references survive retrieval.

Override via environment variable ``NB_CHUNK_OVERLAP`` (integer chars).
"""
from __future__ import annotations

import os
from typing import List

from .parser import DocumentChunk

# Default overlap: 64 "tokens" ≈ ~256 characters (4 chars/token heuristic)
CHUNK_OVERLAP: int = int(os.environ.get("NB_CHUNK_OVERLAP", "256"))


class SemanticChunker:
    """
    Simplified chunker that merges small text blocks from the same page
    to create coherent context windows, while preserving geometric metadata.

    S-22: Supports configurable overlap between consecutive chunks to improve
    retrieval recall across chunk boundaries.
    """

    def __init__(self, max_chars: int = 1000, overlap: int = CHUNK_OVERLAP) -> None:
        self.max_chars = max_chars
        self.overlap = overlap  # characters to carry forward into next chunk

    def chunk(self, blocks: List[DocumentChunk]) -> List[DocumentChunk]:
        """
        Groups blocks into windows of approximately max_chars with *overlap*
        characters of trailing context prepended to the next chunk.
        """
        combined_chunks: List[DocumentChunk] = []
        current_chunk_text = ""
        current_metadata: dict = {}

        for block in blocks:
            if not current_chunk_text:
                current_chunk_text = block.text
                current_metadata = block.metadata
            elif len(current_chunk_text) + len(block.text) < self.max_chars:
                current_chunk_text += "\n" + block.text
            else:
                combined_chunks.append(
                    DocumentChunk(text=current_chunk_text, metadata=current_metadata)
                )
                # Carry overlap from the tail of the just-finished chunk
                overlap_text = current_chunk_text[-self.overlap:] if self.overlap > 0 else ""
                if overlap_text:
                    current_chunk_text = overlap_text + "\n" + block.text
                else:
                    current_chunk_text = block.text
                current_metadata = block.metadata

        if current_chunk_text:
            combined_chunks.append(
                DocumentChunk(text=current_chunk_text, metadata=current_metadata)
            )

        return combined_chunks
