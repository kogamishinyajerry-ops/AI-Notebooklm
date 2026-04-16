from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


def emit_json_log(logger: logging.Logger, event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload.update({key: value for key, value in fields.items() if value is not None})
    logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
