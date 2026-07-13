# PRD Fillable Template — Oracle-Ready Handoff

This template captures source business behavior for the downstream test-generation Skill. Do not write test cases or Gherkin here.

## 1. Scope

- Product/release:
- Target users:
- Problem/outcome:
- Current release boundary:
- Non-goals:
- Dependencies/data constraints:

## 2. Atomic Requirements

For each clause:

```yaml
id: REQ-001
text: <one independently verifiable obligation>
priority: Must Have
release_scope: current
requirement_kind: atomic
source_kind: explicit
evidence_refs: []
```

Use `NFR-###` for non-functional clauses. Use `out_of_version` or `not_applicable` plus `scope_reason` only for documented exclusions.

## 3. Success Metrics

| ID | Metric | Target | Measurement | Verifies |
|---|---|---|---|---|
| METRIC-001 | | | | |

## 4. Functional Acceptance Contract

```yaml
id: AC-REQ-001-01
type: functional
verifies: [REQ-001]
release_scope: current
actor:
preconditions: []
trigger:
response: []
observable_oracles: []
boundaries:
  - condition:
    response:
exceptions:
  - condition:
    response:
evidence_refs: []
```

## 5. NFR Verification Contract

```yaml
id: AC-NFR-001-01
type: nfr
verifies: [NFR-001]
release_scope: current
population:
measurement_start:
measurement_end:
unit:
threshold:
exclusions: []
pass_rule:
evidence_refs: []
```

## 6. Oracle Coverage Ledger

| Requirement | Type | Release scope | Acceptance Contract | Status | Reason |
|---|---|---|---|---|---|
| | | | | | |

## 7. Blocking Questions

| ID | Missing field | Why it blocks | Owner/source needed |
|---|---|---|---|
| | | | |

## 8. Independent Agent Review

- Scope frozen:
- Atomicity passed:
- Functional oracle coverage passed:
- NFR measurement completeness passed:
- References resolved:
- Conflicts absent:
- Blocked count:
- Ready for test generation:
