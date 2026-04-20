from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict


METRICS_ENABLED_ENV = "NOTEBOOKLM_METRICS_ENABLED"
METRICS_ALLOW_REMOTE_ENV = "NOTEBOOKLM_METRICS_ALLOW_REMOTE"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def metrics_enabled() -> bool:
    """Return True only when the operator explicitly enables scraping."""
    return _env_enabled(METRICS_ENABLED_ENV)


def metrics_allow_remote() -> bool:
    """Return True when non-loopback scraping was explicitly allowed."""
    return _env_enabled(METRICS_ALLOW_REMOTE_ENV)


def is_loopback_client(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.strip().lower()
    if normalized in _LOOPBACK_HOSTS:
        return True
    if normalized.startswith("127."):
        return True
    return normalized == "0:0:0:0:0:0:0:1"


def _label_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(**labels: str) -> str:
    if not labels:
        return ""
    rendered = ",".join(
        f'{key}="{_label_escape(str(value))}"'
        for key, value in sorted(labels.items())
    )
    return "{" + rendered + "}"


@dataclass
class MetricsRegistry:
    """Small in-process Prometheus registry with no external dependency."""

    service_name: str = "comac_notebooklm"
    started_at: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _request_total: DefaultDict[tuple[str, str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    _duration_ms_sum: DefaultDict[tuple[str, str, str], float] = field(
        default_factory=lambda: defaultdict(float)
    )

    def observe_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        key = (method.upper(), path, str(status_code))
        with self._lock:
            self._request_total[key] += 1
            self._duration_ms_sum[key] += max(duration_ms, 0.0)

    def render_prometheus(self, *, now: float | None = None) -> str:
        now = time.time() if now is None else now
        with self._lock:
            request_total = dict(self._request_total)
            duration_ms_sum = dict(self._duration_ms_sum)

        uptime_seconds = max(now - self.started_at, 0.0)
        lines = [
            "# HELP notebooklm_process_start_time_seconds Unix start time for this API process.",
            "# TYPE notebooklm_process_start_time_seconds gauge",
            f"notebooklm_process_start_time_seconds {self.started_at:.3f}",
            "# HELP notebooklm_uptime_seconds Process uptime for this API worker.",
            "# TYPE notebooklm_uptime_seconds gauge",
            f"notebooklm_uptime_seconds {uptime_seconds:.3f}",
            "# HELP notebooklm_http_requests_total Total HTTP requests observed by this worker.",
            "# TYPE notebooklm_http_requests_total counter",
        ]

        for (method, path, status), count in sorted(request_total.items()):
            lines.append(
                "notebooklm_http_requests_total"
                f"{_labels(method=method, path=path, status=status)} {count}"
            )

        lines.extend([
            "# HELP notebooklm_http_request_duration_ms_sum Sum of request durations in milliseconds.",
            "# TYPE notebooklm_http_request_duration_ms_sum counter",
        ])
        for (method, path, status), value in sorted(duration_ms_sum.items()):
            lines.append(
                "notebooklm_http_request_duration_ms_sum"
                f"{_labels(method=method, path=path, status=status)} {value:.3f}"
            )

        lines.extend([
            "# HELP notebooklm_http_request_duration_ms_count Count of request duration observations.",
            "# TYPE notebooklm_http_request_duration_ms_count counter",
        ])
        for (method, path, status), count in sorted(request_total.items()):
            lines.append(
                "notebooklm_http_request_duration_ms_count"
                f"{_labels(method=method, path=path, status=status)} {count}"
            )

        return "\n".join(lines) + "\n"
