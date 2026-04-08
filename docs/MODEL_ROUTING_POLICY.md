# Model Routing Policy — AeroProp Logic Harness

**Document ID:** APLH-GOV-008  
**Version:** 0.1.0  
**Status:** DRAFT  

---

## 1. Purpose

This document defines which AI model should be used for which task category in the APLH workflow. It is an engineering routing policy, not a general model comparison.

## 2. Available Models

| Model | Key Strengths | Key Limitations |
|---|---|---|
| **GPT-5.4** | Strong structured output, reliable JSON/YAML generation, good at following schemas | May hallucinate domain details; less reliable for very long context |
| **Gemini 3.1 Pro** | Very long context window, strong document ingestion, good at synthesis | May be verbose; structured output sometimes needs tighter prompting |
| **Opus 4.6** | Deep reasoning, excellent code generation, strong architectural analysis | Higher latency; higher cost per token; overkill for simple tasks |
| **Minimax 2.7** | Fast inference, good for batch processing, cost-effective | Lower ceiling on complex reasoning; less reliable for safety-critical logic analysis |

## 3. Task Routing Matrix

### 3.1 Primary Execution (Schema Development, Code, Architecture)

| Task | Recommended Model | Rationale |
|---|---|---|
| Schema design & data model engineering | **Opus 4.6** | Requires deep structural reasoning and consistency |
| Python code generation (validators, CLI) | **Opus 4.6** or **GPT-5.4** | Both strong; Opus for complex logic, GPT-5.4 for routine code |
| Architecture decisions | **Opus 4.6** | Best at multi-factor reasoning and trade-off analysis |
| Bug investigation and debugging | **Opus 4.6** | Strong root-cause analysis capability |

### 3.2 Long Document Ingestion

| Task | Recommended Model | Rationale |
|---|---|---|
| Regulation document parsing (CCAR-33, FAR-33, CS-E) | **Gemini 3.1 Pro** | Long context window handles full regulation documents |
| OEM document requirement extraction | **Gemini 3.1 Pro** | Can ingest large documents in single pass |
| Cross-document comparison | **Gemini 3.1 Pro** | Can hold multiple documents in context simultaneously |
| Technical report summarization | **Gemini 3.1 Pro** | Good at synthesis across long content |

### 3.3 Logic Review & Consistency Checking

| Task | Recommended Model | Rationale |
|---|---|---|
| Trace consistency review | **Opus 4.6** | Best at spotting logical gaps and inconsistencies |
| Abnormal scenario completeness review | **Opus 4.6** | Strong at reasoning about failure modes |
| Requirement conflict detection | **GPT-5.4** or **Opus 4.6** | Both capable; GPT-5.4 sufficient for pairwise, Opus for systemic |
| Schema validation rule review | **GPT-5.4** | Good at structured rule verification |

### 3.4 Batch Processing & Routine Tasks

| Task | Recommended Model | Rationale |
|---|---|---|
| Bulk YAML generation from templates | **GPT-5.4** or **Minimax 2.7** | Routine structured output; cost-optimize with Minimax |
| Glossary entry generation from source text | **Minimax 2.7** | Simple extraction task; high volume |
| Tag/metadata normalization | **Minimax 2.7** | Straightforward transformation |
| Format conversion (JSON ↔ YAML) | **Minimax 2.7** | Mechanical task; lowest cost model sufficient |

### 3.5 Documentation & Handoff

| Task | Recommended Model | Rationale |
|---|---|---|
| Governance document drafting | **Opus 4.6** | Requires nuanced engineering judgment |
| Architecture documentation | **Opus 4.6** | Complex structural explanation |
| Template annotation and field descriptions | **GPT-5.4** | Good at clear, structured explanations |
| README / user guide writing | **GPT-5.4** | Clean, well-structured output |

## 4. Anti-Patterns (Do NOT Assign)

| Model | Do NOT Use For | Reason |
|---|---|---|
| **Minimax 2.7** | Safety-critical abnormal analysis | Insufficient reasoning depth |
| **Minimax 2.7** | Architecture decisions | Lacks multi-factor trade-off capability |
| **Minimax 2.7** | Schema design | May produce inconsistent structures |
| **GPT-5.4** | Full regulation document ingestion (>100k tokens) | Context window limitations |
| **Gemini 3.1 Pro** | Tight-format JSON schema generation | May add verbose explanations instead of clean output |
| Any model | Original requirement authoring | **Policy: AI cannot be requirement source** |
| Any model | Review gate pass/fail decisions | **Policy: Human-only gate** |
| Any model | Freeze approval | **Policy: Human-only decision** |

## 5. Routing Implementation Notes

### 5.1 Current Phase (Phase 0–1)
- Model selection is manual (engineer chooses per task)
- No automated routing infrastructure needed
- This document serves as the engineer's reference

### 5.2 Future Phase (Phase 2+)
- Consider a lightweight dispatcher that suggests model based on task type tag
- Dispatcher should be advisory, not mandatory
- Log which model was used for each AI-assisted task (for provenance tracking)

### 5.3 Provenance Integration
When any AI model produces content that enters an artifact:
```yaml
provenance:
  source_type: "ai_extracted"  # or ai_inferred
  method: "extracted by Gemini 3.1 Pro from CCAR-33 §33.28"
  confidence: 0.6
  reviewed_by: ""
  review_date: ""
```

The model identity becomes part of the provenance chain. This is mandatory, not optional.

## 6. Cost & Latency Guidance

| Priority | Use | Model |
|---|---|---|
| Speed + lowest cost | Batch, routine | Minimax 2.7 |
| Balance of quality + cost | General tasks | GPT-5.4 |
| Maximum quality (complex reasoning) | Architecture, review, safety | Opus 4.6 |
| Maximum context (long docs) | Document ingestion | Gemini 3.1 Pro |

---

*This policy should be reviewed when new models become available or when task patterns change significantly.*
