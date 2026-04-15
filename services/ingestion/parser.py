import fitz  # PyMuPDF
from typing import List, Dict, Any
from pydantic import BaseModel

class DocumentChunk(BaseModel):
    text: str
    metadata: Dict[str, Any]

class PDFParser:
    """
    Hig-fidelity PDF Parser using PyMuPDF.
    Ensures Constraint C2: Each chunk maintains its source, page, and BBox.
    """
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.doc = fitz.open(file_path)

    @property
    def page_count(self) -> int:
        return len(self.doc)

    def extract_chunks(self) -> List[DocumentChunk]:
        """
        Parses the PDF and returns a list of chunks grouped by page.
        In Phase 2, we treat each block as a potential chunk.
        """
        chunks = []
        for page_num, page in enumerate(self.doc):
            # Extract blocks (text blocks with geometry)
            blocks = page.get_text("blocks")
            for block in blocks:
                # block[4] is the text, block[:4] is the bbox (x0, y0, x1, y1)
                text = block[4].strip()
                if not text:
                    continue
                
                bbox = block[:4]
                metadata = {
                    "source": self.file_path.split("/")[-1],
                    "page": page_num + 1,
                    "bbox": list(bbox),
                    "type": "text"
                }
                chunks.append(DocumentChunk(text=text, metadata=metadata))
        
        return chunks

    def close(self):
        self.doc.close()
