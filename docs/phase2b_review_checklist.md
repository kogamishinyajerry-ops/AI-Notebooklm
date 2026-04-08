# APLH Phase 2B Human Review Checklist

## 1. Scope

This checklist covers the **T2/T3 advisory review items** that require human judgment
and cannot be fully resolved by automated gates:

- P2-C4-R: Priority conflicts with overlapping guards
- P2-D4-R: ABN severity vs mode type alignment
- P2-D2-R: Degraded mode recovery path quality

This checklist does **NOT** cover:

- T1 items handled by automated gates (initial mode, reachability, endpoint resolution, etc.)
- Execution semantics, scenario evaluation, or runtime behavior (Phase 3+)
- Formal baseline freeze decisions (separate governance process)

## 2. Review Items

### 2.1 P2-C4-R: Priority conflicts with overlapping guards

- [ ] For each source_mode with multiple outgoing transitions:
  - List transitions sharing equal priority
  - Assess whether guard predicates could overlap
  - Record: PASS / CONCERN / N/A

### 2.2 P2-D4-R: ABN severity matches mode type

- [ ] For each ABN → MODE mapping:
  - Verify severity_hint is consistent with target mode_type
  - Record: PASS / CONCERN / N/A

### 2.3 P2-D2-R: Degraded mode recovery path quality

- [ ] For each degraded mode with outgoing transitions:
  - Verify at least one path leads to a normal mode
  - Record: PASS / CONCERN / N/A

## 3. Signoff

- Reviewer:
- Date:
- Verdict: PASS / REVISE
