import chromadb
from chromadb.config import Settings
import uuid
import json
import os

os.environ.setdefault("ANONYMIZED_TELEMETRY", "FALSE")


def build_chroma_settings(persist_directory: str) -> Settings:
    return Settings(
        is_persistent=True,
        persist_directory=persist_directory,
        anonymized_telemetry=False,
        allow_reset=False,
    )

class VectorStoreAdapter:
    """
    Adapter for local vector storage using ChromaDB.
    Ensures data privacy (C1) by running as a local persistent library.
    Handle list-type metadata (like BBox) by serializing to JSON strings for ChromaDB compatibility.
    """
    def __init__(self, persist_directory: str = "data/vector_db"):
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=build_chroma_settings(persist_directory),
        )
        self.collection_name = "doc_knowledge_base"
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def add_documents(self, chunks: list[str], metadatas: list[dict], embeddings: list[list[float]]):
        """
        Adds text chunks with metadata and embeddings to the store.
        ChromaDB metadata values must be str, int, float or bool.
        We stringify lists (e.g. bbox) to JSON.
        """
        processed_metadatas = []
        for meta in metadatas:
            new_meta = {}
            for k, v in meta.items():
                if isinstance(v, (list, dict)):
                    new_meta[k] = json.dumps(v)
                else:
                    new_meta[k] = v
            processed_metadatas.append(new_meta)

        ids = [str(uuid.uuid4()) for _ in chunks]
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=processed_metadatas,
            documents=chunks
        )

    def query(self, query_embeddings: list[float], top_k: int = 5):
        """
        Queries the store for the most relevant chunks.
        Deserializes JSON strings back to lists/dicts where applicable.
        """
        results = self.collection.query(
            query_embeddings=[query_embeddings],
            n_results=top_k
        )
        
        # Post-process results to deserialize metadata
        if results.get("metadatas"):
            for i in range(len(results["metadatas"])):
                for j in range(len(results["metadatas"][i])):
                    meta = results["metadatas"][i][j]
                    for k, v in meta.items():
                        if isinstance(v, str) and (v.startswith("[") or v.startswith("{")):
                            try:
                                meta[k] = json.loads(v)
                            except:
                                pass # Keep as string if parsing fails
        
        return results
