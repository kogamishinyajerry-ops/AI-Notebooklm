from .parser import PDFParser
from .chunker import SemanticChunker
from core.retrieval.vector_store import VectorStoreAdapter
from core.retrieval.embeddings import EmbeddingManager
from core.storage.space_resolver import normalize_space_id
from services.knowledge.parameter_registry import ParameterRegistry

class IngestionService:
    """
    Orchestrator for the Document Ingestion Pipeline.
    Coordinates Parsing -> Chunking -> Embedding -> Storage.
    """
    def __init__(self, space_id: str = "default"):
        self.space_id = normalize_space_id(space_id)
        self.vector_store = VectorStoreAdapter(space_id=self.space_id)
        self.embedding_manager = EmbeddingManager()
        self.chunker = SemanticChunker()
        self.parameter_registry = ParameterRegistry(space_id=self.space_id)

    def process_file(self, file_path: str):
        # 1. Parse
        parser = PDFParser(file_path)
        blocks = parser.extract_chunks()
        parser.close()

        # 2. Chunk
        chunks = self.chunker.chunk(blocks)
        self._register_parameters(chunks)

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

    def _register_parameters(self, chunks):
        for index, chunk in enumerate(chunks):
            metadata = chunk.metadata or {}
            source = metadata.get("source", "")
            page_raw = metadata.get("page", 0)
            try:
                page = int(page_raw)
            except (TypeError, ValueError):
                page = 0
            chunk_id = f"{source}:p{page}:chunk:{index}"
            self.parameter_registry.register_parameters(
                chunk_id=chunk_id,
                text=chunk.text,
                page=page,
                source=source,
            )
