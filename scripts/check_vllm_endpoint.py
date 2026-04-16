from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.llm.vllm_client import LLMConfigurationError, probe_local_llm


def main() -> int:
    timeout = float(os.getenv("VLLM_HEALTH_TIMEOUT", "2"))
    try:
        result = probe_local_llm(timeout=timeout)
    except LLMConfigurationError as exc:
        print(
            json.dumps(
                {
                    "status": "misconfigured",
                    "reachable": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("reachable") else 1


if __name__ == "__main__":
    raise SystemExit(main())
