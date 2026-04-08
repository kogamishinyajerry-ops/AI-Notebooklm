# ID and Naming Conventions — AeroProp Logic Harness

**Document ID:** APLH-GOV-005  
**Version:** 0.1.0  
**Status:** DRAFT — Pending Gate B Freeze  

---

## 1. Design Principles

The ID system is designed to be:
- **Stable**: IDs never change once assigned; deprecated items retain their ID
- **Readable**: A human can identify artifact type from the prefix
- **Sortable**: Numeric suffix enables natural ordering
- **Cross-referenceable**: IDs are unique across all artifact types
- **Future-proof**: 4-digit sequence supports up to 9999 items per type; expandable if needed

## 2. ID Format

```
{PREFIX}-{NNNN}
```

Where:
- `{PREFIX}` is the artifact type prefix (uppercase)
- `-` is a literal hyphen separator
- `{NNNN}` is a zero-padded 4-digit sequence number

### 2.1 Prefix Table

| Prefix | Artifact Type | Example |
|---|---|---|
| `REQ` | Requirement | `REQ-0001` |
| `FUNC` | Function | `FUNC-0001` |
| `IFACE` | Interface | `IFACE-0001` |
| `ABN` | Abnormal | `ABN-0001` |
| `TERM` | Glossary Entry | `TERM-0001` |
| `TRACE` | Trace Link | `TRACE-0001` |

### 2.2 Regex Pattern

```regex
^(REQ|FUNC|IFACE|ABN|TERM|TRACE)-[0-9]{4}$
```

### 2.3 Validation Rules

1. Prefix must be one of the defined values (case-sensitive, uppercase)
2. Separator must be a single hyphen
3. Sequence number must be exactly 4 digits, zero-padded
4. IDs are globally unique — no two artifacts may share the same ID regardless of type
5. Once assigned, an ID must not be reused even if the artifact is deprecated

## 3. File Naming

### 3.1 Artifact Files

```
{id_lowercase}.yaml
```

Examples:
- `req-0001.yaml`
- `func-0003.yaml`
- `iface-0002.yaml`
- `abn-0001.yaml`
- `term-0005.yaml`
- `trace-0001.yaml`

Rules:
- Filename is the artifact ID in lowercase
- Extension is `.yaml` (not `.yml`)
- One artifact per file

### 3.2 Directory Structure

```
artifacts/
├── requirements/     # REQ-xxxx files
├── functions/        # FUNC-xxxx files
├── interfaces/       # IFACE-xxxx files
├── abnormals/        # ABN-xxxx files
├── glossary/         # TERM-xxxx files
├── trace/            # TRACE-xxxx files
└── examples/         # Example/demo artifacts (any type)
```

### 3.3 Schema Files

```
schemas/{artifact_type}.schema.json
```

Examples: `requirement.schema.json`, `function.schema.json`

### 3.4 Template Files

```
templates/{artifact_type}.template.yaml
```

Examples: `requirement.template.yaml`, `function.template.yaml`

### 3.5 Documentation Files

```
docs/{DOCUMENT_NAME}.md
```

- Uppercase with underscores for governance/architecture docs
- Example: `PROJECT_CHARTER.md`, `REVIEW_GATES.md`

## 4. Sequence Number Management

### Phase 0–1 Approach (Manual)
- Engineers assign the next available number manually
- The CLI `list-artifacts` command shows existing IDs to avoid collisions
- No automated sequence server is required

### Phase 2+ Consideration
- An auto-increment service may be added if artifact volume justifies it
- The 4-digit format can be extended to 5+ digits if needed (backward-compatible since the regex can be relaxed)

## 5. Cross-Reference Notation

When referencing an artifact from within another artifact's fields:

```yaml
# Direct reference (preferred)
linked_functions:
  - "FUNC-0001"
  - "FUNC-0003"

# In prose/notes fields
notes: "See REQ-0012 for the originating thrust management requirement."
```

## 6. Version Tagging

Artifact versions follow simplified semantic versioning:

```
{MAJOR}.{MINOR}.{PATCH}
```

- **MAJOR**: Incompatible change to artifact meaning (e.g., requirement intent changed)
- **MINOR**: Compatible addition (e.g., new detail field populated)
- **PATCH**: Correction (e.g., typo fix, formatting)

Initial version for all new artifacts: `0.1.0`

---

*This document is subject to Gate B (Schema Freeze) review.*
