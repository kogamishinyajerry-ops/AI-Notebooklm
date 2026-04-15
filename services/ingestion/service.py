from __future__ import annotations

from pathlib import Path

from core.ingestion.transaction import IngestTransaction
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

    def process_file(
        self,
        file_path: str,
        space_id: str = "default",
        source_id: str | None = None,
        transaction: IngestTransaction | None = None,
    ) -> tuple[int, int]:
        tx = transaction or IngestTransaction(space_id=space_id)

        try:
            if Path(file_path).exists():
                tx.record_file(file_path)

            # 1. Parse
            parser = PDFParser(file_path)
            try:
                page_count = parser.page_count
                blocks = parser.extract_chunks()
            finally:
                parser.close()

            # 2. Chunk
            chunks = self.chunker.chunk(blocks)

            # 3. Embed & Store
            texts = [c.text for c in chunks]
            metadatas = [c.metadata for c in chunks]
            if source_id is not None:
                for metadata in metadatas:
                    metadata["source_id"] = source_id
                    metadata["space_id"] = space_id

            # In a real environment, we'd batch this to avoid memory issues
            embeddings = self.embedding_manager.encode(texts)

            # Record ids before the Chroma write so crash recovery can delete
            # any rows that were added before an interrupted process exited.
            vector_ids = self.vector_store.new_document_ids(len(chunks))
            tx.record_vector_ids(vector_ids)
            self.vector_store.add_documents(
                chunks=texts,
                metadatas=metadatas,
                embeddings=embeddings.tolist(),
                ids=vector_ids,
            )

            tx.commit()
            return len(chunks), page_count
        except Exception:
            if tx.status == "in_progress":
                tx.rollback(
                    vector_store=self.vector_store,
                    registry=getattr(self, "parameter_registry", None),
                )
            raise
