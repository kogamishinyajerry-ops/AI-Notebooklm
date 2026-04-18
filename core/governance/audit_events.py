from __future__ import annotations

from enum import Enum


class AuditEvent(str, Enum):
    SPACE_CREATE = "space.create"
    NOTEBOOK_CREATE = "notebook.create"
    NOTEBOOK_DELETE = "notebook.delete"
    SOURCE_UPLOAD = "source.upload"
    SOURCE_DELETE = "source.delete"
    CHAT_REQUEST = "chat.request"
    CHAT_HISTORY_CLEAR = "chat.history.clear"
    NOTE_CREATE = "note.create"
    NOTE_UPDATE = "note.update"
    NOTE_DELETE = "note.delete"
    STUDIO_CREATE = "studio.create"
    STUDIO_DELETE = "studio.delete"
    GRAPH_GENERATE = "graph.generate"
    QUOTA_DENIED = "quota.denied"
    AUTH_DENIED = "auth.denied"
    INTEGRITY_REPAIR = "integrity.repair"
    ADMIN_ACCESS = "admin.access"
