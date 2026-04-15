import os
from .parser import PDFParser
from .chunker import SemanticChunker
from core.retrieval.vector_store import VectorStoreAdapter
from core.retrieval.embeddings import EmbeddingManager

class IngestionService:
    """
    Orchestrator for the Document Ingestion Pipeline.
    Coordinates Parsing -> Chunking -> Embedding -> Storage.
    """
    def __init__(self):
        self.vector_store = VectorStoreAdapter()
        self.embedding_manager = EmbeddingManager()
        self.chunker = SemanticChunker()

    def process_file(self, file_path: str):
        # 1. Parse
        parser = PDFParser(file_path)
        blocks = parser.extract_chunks()
        parser.close()

        # 2. Chunk
        chunks = self.chunker.chunk(blocks)

        # 3. Embed & Store
        texts = [c.text for c in chunks]
        metadatas = [c.metadata for c in chunks]
        
        # In a real environment, we'd batch this to avoid memory issues
        embeddings = self.embedding_manager.encode(texts)
        
        # Store in ChromaDB
        self.vector_store.add_documents(
            chunks=texts,
            metadatas=metadatas,
            embeddings=embeddings.tolist()
        )

        return len(chunks)
