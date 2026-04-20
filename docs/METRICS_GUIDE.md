# V4.3 Metrics Guide

V4.3 adds a stdlib-only Prometheus text endpoint at `/metrics`.

## Default Posture

Metrics are disabled by default:

```bash
curl -i http://127.0.0.1:8000/metrics
# HTTP/1.1 404 Not Found
```

This keeps the production runtime quiet unless an operator deliberately enables
scraping.

## Enable Local Scraping

Enable the endpoint with:

```bash
export NOTEBOOKLM_METRICS_ENABLED=1
```

By default, only loopback clients can scrape it. This accepts `127.0.0.1`,
`127.*`, `::1`, and `localhost`.

```bash
curl http://127.0.0.1:8000/metrics
```

The endpoint ignores forwarded headers for access control so a remote caller
cannot spoof loopback through `X-Forwarded-For`.

## Explicit Remote Override

Only set this inside a trusted intranet deployment where network policy already
restricts the scraper path:

```bash
export NOTEBOOKLM_METRICS_ALLOW_REMOTE=1
```

`NOTEBOOKLM_METRICS_ALLOW_REMOTE=1` has no effect unless
`NOTEBOOKLM_METRICS_ENABLED=1` is also set.

## Emitted Metrics

- `notebooklm_process_start_time_seconds`
- `notebooklm_uptime_seconds`
- `notebooklm_http_requests_total{method,path,status}`
- `notebooklm_http_request_duration_ms_sum{method,path,status}`
- `notebooklm_http_request_duration_ms_count{method,path,status}`

Metrics are per-process and in-memory. Multi-worker deployments should scrape
each worker or treat the values as worker-local observability, not global
business counters.

## Compliance Notes

- No new dependency is introduced.
- The endpoint does not call external services.
- Metrics expose route templates and status codes, not request bodies, document
  content, API keys, filenames, or citation payloads.
