# PRD-to-Gherkin Handoff Contract

This reference is normative for PRD generation. It describes source evidence that the downstream test-generation Skill may transform into Requirement Model, test cases, and Gherkin. It does not authorize this Skill to generate those artifacts.

## 1. Requirement Record

```yaml
id: REQ-001                 # or NFR-001
text: <one normative obligation>
priority: Must Have         # functional only; Should/Could are equally oracle-bound
release_scope: current      # current | out_of_version | not_applicable
scope_reason: <required when non-current>
requirement_kind: atomic    # current normative clauses must be atomic
parent_req: <optional parent ID>
source_kind: explicit       # explicit | valid_derivation
evidence_refs: [<source locator>]
```

`current` means the downstream test Skill must consider the clause authoritative. `out_of_version` and `not_applicable` are exclusions, not test inputs.

Release scope must be an explicit product decision for every candidate clause, including `Should` and `Could`. MoSCoW priority never implies `current` or authorizes an exclusion.

## 2. Functional Acceptance Contract

```yaml
id: AC-REQ-001-01
type: functional
verifies: [REQ-001]
release_scope: current
actor: <who or what initiates the behavior>
preconditions: [<observable state>]
trigger: <single business action/event>
response: [<required system behavior>]
observable_oracles: [<pass/fail observation>]
boundaries:
  - condition: <limit or partition>
    response: <required behavior at that limit>
exceptions:
  - condition: <failure/invalid state>
    response: <required behavior>
evidence_refs: [<user decision, parent clause, or architecture contract>]
```

Completeness rule: all fields are present and non-empty for current scope. Each boundary and exception must pair condition with response. One contract may verify multiple atomic IDs only when one behavior produces an independently observable oracle for every linked ID.

## 3. NFR Verification Contract

```yaml
id: AC-NFR-001-01
type: nfr
verifies: [NFR-001]
release_scope: current
population: <requests/users/items/runs and selection rule>
measurement_start: <start event>
measurement_end: <end event>
unit: <ms, %, count, etc.>
threshold: <numeric comparison>
exclusions: [<excluded samples or none>]
pass_rule: <aggregation and pass/fail comparison>
evidence_refs: [<source locator>]
```

All seven measurement fields are mandatory. The Agent may normalize syntax but may not choose a missing percentile, sample, window, aggregation, or threshold.

Before applying this schema, classify the obligation:

- A deterministic invariant that must hold for every applicable event belongs in an atomic functional/governance requirement and functional contract, including the required failure response.
- A statistical quality target evaluated over a population or time window belongs in an NFR contract and requires all seven fields.

## 4. Oracle Coverage Ledger

```markdown
| Requirement | Type | Release scope | Acceptance Contract | Status | Reason |
|---|---|---|---|---|---|
| REQ-001 | functional | current | AC-REQ-001-01 | ready | - |
| NFR-002 | nfr | current | - | blocked | missing pass_rule |
| REQ-010 | functional | out_of_version | - | excluded | planned for v2 |
```

Allowed statuses are `ready`, `blocked`, and `excluded`. `ready_for_test_generation` requires zero blocked current-scope rows.

## 5. Evidence and Derivation

Acceptable evidence:

- a direct user/product-owner decision;
- an explicit parent PRD clause or Acceptance Contract;
- an explicit architecture interface/event/data/metric contract;
- a valid deterministic derivation that records its source and transformation.

Unacceptable evidence:

- common sense, industry convention, or model memory;
- a test technique chosen by the downstream Skill;
- a generated placeholder such as “returns expected result”;
- priority, `gherkin_count`, or the existence of a scenario name;
- an unconfirmed assumption.

## 6. Mechanical Gates

Before `ready_for_test_generation: true`, verify:

1. IDs are unique and references resolve.
2. Every current normative clause is atomic.
3. Every current functional clause has a complete functional contract.
4. Every current NFR has a complete NFR contract.
5. Contract type matches requirement type.
6. Every contract has at least one evidence reference.
7. Non-current clauses have an exclusion reason and no mixed current linkage.
8. No conflicting required responses exist for the same condition.
9. Coverage ledger contains zero blocked rows.
10. Independent Agent review reports pass.

If any gate fails, keep the artifact as a draft and list exact blocking fields. Do not fill the field with invented content.

## 7. Operational Closure and Handoff

After running the mechanical gates, the PRD generator must repeatedly:

1. recompute blocked rows;
2. ask one product decision at a time, ordered by scope, functional oracle, then NFR measurement;
3. record the answer as evidence and update the affected contract;
4. rerun all gates.

With any blocker or pending/failed independent review, save `*.draft.md` with `status: draft` and `ready_for_test_generation: false`; downstream handoff is prohibited. Only a zero-blocker, independently passed artifact may use the normal `.md` filename with `status: approved` and `ready_for_test_generation: true`.

## 8. Quality-report Recovery

When a downstream quality report identifies missing requirements, parse and map each finding back to the exact requirement or contract field. Preserve valid content, resume the closure loop at the first unresolved decision, and ask only for missing facts. Do not restart discovery and do not clear a finding by editing readiness metadata alone.
