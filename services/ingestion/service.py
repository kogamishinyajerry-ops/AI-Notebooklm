import os
from typing import List, Dict, Any
from services.ingestion.parser import PDFParser
from core.retrieval.vector_store import VectorStoreAdapter
from core.retrieval.embeddings import EmbeddingManager
from services.knowledge.graph_builder import KnowledgeGraphBuilder
from services.knowledge.parameter_registry import ParameterRegistry
import threading

class IngestionService:
    """
    Industrial-grade Ingestion Pipeline (Task 5 | V3.0 Updated Task 41)
    Coordinates parsing, embedding, vector storage, and now Cognitive Graph building.
    """
    def __init__(self):
        self.vector_store = VectorStoreAdapter()
        self.embedding_manager = EmbeddingManager()
        self.graph_builder = KnowledgeGraphBuilder()
        self.parameter_registry = ParameterRegistry()

    def process_file(self, file_path: str) -> int:
        """
        Main pipeline for processing an uploaded PDF.
        """
        parser = PDFParser(file_path)
        chunks = parser.extract_chunks()
        
        # 1. Prepare vectors
        texts = [c.text for c in chunks]
        metadatas = [c.metadata for c in chunks]
        embeddings = self.embedding_manager.encode(texts)
        
        # 2. Add to Vector DB (Sync)
        self.vector_store.add_documents(
            chunks=texts,
            metadatas=metadatas,
            embeddings=embeddings.tolist()
        )
        
        # 3. Cognitive Indexing (Async - Task 41)
        # We spawn a background thread for high-precision extraction
        thread = threading.Thread(target=self._run_cognitive_indexing, args=(chunks,))
        thread.start()
        
        return len(chunks)

    def _run_cognitive_indexing(self, chunks: List[Any]):
        """
        Performs GraphRAG and Parameter tagging.
        This is the source-grounded reasoning preparation.
        """
        for i, chunk in enumerate(chunks):
            chunk_id = f"{chunk.metadata.get('source')}_{i}"
            
            # Extract Graph triples
            self.graph_builder.process_chunk(
                chunk_id=chunk_id,
                text=chunk.text,
                source=chunk.metadata.get('source')
            )
            
            # Register Parameters
            self.parameter_registry.register_parameters(
                chunk_id=chunk_id,
                text=chunk.text,
                page=chunk.metadata.get('page', 1),
                source=chunk.metadata.get('source')
            )
        
        # Flush any unsaved graph changes (batch write strategy from A-1)
        self.graph_builder.flush()
        print(f"Cognitive Indexing Complete for {len(chunks)} chunks.")
