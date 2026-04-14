from typing import List
from .parser import DocumentChunk

class SemanticChunker:
    """
    Simplified chunker that merges small text blocks from the same page 
    to create coherent context windows, while preserving geometric metadata.
    """
    def __init__(self, max_chars: int = 1000):
        self.max_chars = max_chars

    def chunk(self, blocks: List[DocumentChunk]) -> List[DocumentChunk]:
        """
        Groups blocks into windows of approximately max_chars.
        """
        combined_chunks = []
        current_chunk_text = ""
        current_metadata = {}

        for block in blocks:
            if not current_chunk_text:
                current_chunk_text = block.text
                current_metadata = block.metadata
            elif len(current_chunk_text) + len(block.text) < self.max_chars:
                current_chunk_text += "\n" + block.text
                # In this simple version, we take the bbox of the first block 
                # or we could calculate a bounding box for the combined area.
                # Here we stick to page-level or first-block metadata for simplicity.
            else:
                combined_chunks.append(DocumentChunk(text=current_chunk_text, metadata=current_metadata))
                current_chunk_text = block.text
                current_metadata = block.metadata
        
        if current_chunk_text:
            combined_chunks.append(DocumentChunk(text=current_chunk_text, metadata=current_metadata))
            
        return combined_chunks
