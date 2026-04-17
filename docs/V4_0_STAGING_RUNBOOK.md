# V4.0 Staging Runbook

## Goal

Deploy the reviewed V4.0 image into an intranet staging environment, validate API health, auth isolation, and local-LLM connectivity, then hand the environment to real-corpus and UAT work.

## Files

- `/Users/Zhuanz/AI-Notebooklm/deploy/docker-compose.staging.yml`
- `/Users/Zhuanz/AI-Notebooklm/deploy/staging.env.example`
- `/Users/Zhuanz/AI-Notebooklm/scripts/check_vllm_endpoint.py`

## Pre-flight

1. Copy `deploy/staging.env.example` to `deploy/staging.env`.
2. Replace `NOTEBOOKLM_API_KEYS` with a real staging owner/API-key mapping.
3. Point `VLLM_URL` at the actual OpenAI-compatible local vLLM endpoint.
4. Confirm the target host has access to the baked embedding cache or can build the image once with network access.

## Launch

```bash
cd /Users/Zhuanz/AI-Notebooklm/deploy
cp staging.env.example staging.env
docker compose -f docker-compose.staging.yml build
docker compose -f docker-compose.staging.yml up -d
docker compose -f docker-compose.staging.yml ps
```

## Required Checks

### API health

```bash
curl -fsS http://localhost:8000/api/v1/health | jq
```

Expected:

- `status=ok`
- `transactions` object present

### LLM endpoint alignment

```bash
cd /Users/Zhuanz/AI-Notebooklm
python3 scripts/check_vllm_endpoint.py
curl -fsS http://localhost:8000/api/v1/llm/health | jq
```

Expected:

- `status=reachable`
- `configured_url` matches the staging `VLLM_URL`
- no `mismatched_service`

### Auth isolation

1. Create notebook with a valid `X-API-Key`.
2. Repeat the same request without API key and expect `401`.
3. Repeat with another principal’s key and expect `403` on notebook-scoped subresources.

Example:

```bash
curl -sS -X POST http://localhost:8000/api/v1/notebooks \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: replace-with-real-api-key' \
  -d '{"name":"staging notebook"}' | jq
```

## Deployment Notes

- The staging compose file pins Uvicorn to `--workers 1` to avoid JSON-store write races before a future SQLite migration.
- `VLLM_URL` must not reuse the API port `8000`; default staging examples assume `8001`.
- If `/api/v1/llm/health` reports `mismatched_service`, stop and fix the endpoint before UAT.

## Exit Criteria

- Container stays healthy for 10+ minutes.
- `/api/v1/health` and `/api/v1/llm/health` both pass.
- Auth checks return the expected `401/403` boundaries.
- A notebook can ingest at least one PDF and answer one grounded query with citations.
