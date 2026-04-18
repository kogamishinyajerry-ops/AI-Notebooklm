from __future__ import annotations

from fastapi import HTTPException


class NotebookNotFound(HTTPException):
    def __init__(self, notebook_id: str):
        super().__init__(
            status_code=404,
            detail=f"Notebook not found: {notebook_id}",
        )
