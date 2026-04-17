# V4.0 UAT Pack

## Goal

Run structured user acceptance validation on the staging environment after D1 and D3 are green.

## Test Roles

- Reviewer A: citation accuracy
- Reviewer B: retrieval relevance
- Reviewer C: workflow usability

One person can cover multiple roles if the staging pilot is small.

## Core Scenarios

### 1. Notebook isolation

1. Create two notebooks with different API keys.
2. Upload different PDFs to each notebook.
3. Verify notebook list and chat responses never leak the other notebook’s content.

Pass when:

- notebook list only shows the current owner’s notebooks
- cross-owner notebook access returns `403`
- chat never cites the foreign notebook

### 2. Grounded Q&A with citations

1. Ask 5 real airworthiness questions against the staged corpus.
2. Inspect returned citations and open the cited page in the PDF viewer.
3. Score each answer:
   - `2` = citation is correct and answer is grounded
   - `1` = answer is partially correct but citation is weak
   - `0` = answer is unsupported or wrong

Pass when:

- average score is at least `1.5`
- no answer scores `0` because of fabricated citations

### 3. Notes and history persistence

1. Save at least one response to notes.
2. Refresh the page.
3. Confirm notes and chat history remain visible and correctly scoped.

### 4. Studio outputs

1. Generate all available studio output types for one notebook.
2. Confirm each artifact is persisted and reloadable.
3. Verify citations or source grounding remain visible where applicable.

### 5. Graph / mind-map usability

1. Open the graph tab for a notebook with ingested aerospace content.
2. Confirm graph renders without crashing.
3. Ask one entity-centric question and confirm retrieval still returns grounded chunks.

## Capture Template

For each scenario record:

- reviewer
- notebook id
- query or action
- expected result
- actual result
- screenshots or copied response
- blocker or severity

## Final Decision

- `Pass`: no blocker, grounded answers acceptable, workflows usable
- `Conditional Pass`: only minor UX friction
- `Fail`: citation error, data leak, or broken primary workflow

## Recommended Command Support

Before handing to users, rerun:

```bash
cd /Users/Zhuanz/AI-Notebooklm
python3 -m pytest -q
python3 scripts/check_vllm_endpoint.py
```
