---
name: leaf-gate
description: Use when deciding whether a layered PRD node with a PRD, testcase.feature, architecture, traceability, or risk artifacts should be decomposed further, refined, reviewed by a human, or sent to vibecoding.
---

# Leaf Gate

## Overview

Leaf Gate is the stopping decision for an explainable layered development flow. Use it after a current-layer PRD, testcase, architecture, and architecture-validation pass exist, before choosing between deeper decomposition and vibecoding.

The gate is not a prompt-only review. Prepare traceability and risk evidence first, run deterministic checks second, then perform semantic judgement with evidence.

## Required Inputs

Use a node folder when available:

```text
node-id/
  prd.md
  testcase.feature
  architecture.yaml|json|md
  traceability.yaml|json|md
  risks.yaml|json|md
```

Multi-file architecture packages are also supported:

```text
node-id/
  prd.md
  testcase.feature
  architecture/
    output/
      01-system-overview.md
      02-module-partitioning.md
      03-runtime-architecture.md
      04-adr-summary.md
      05-data-model.md
      06-interface-contracts.md
      07-technology-choices.md
      08-deployment.md
    validation-report.md
```

When `traceability.md` or `risks.md` is absent or stale, `scripts/run_leaf_gate.py` refreshes them from the current PRD, testcase, architecture package, and validation report before static checks. Use `--skip-prepare` only when intentionally reviewing existing evidence files without regenerating them.

Generated traceability uses deterministic evidence strength:

| Strength | Meaning | Gate effect |
| --- | --- | --- |
| `strong` | Direct REQ/NFR ID match, or architecture contract evidence plus boundary/value terms and product terms. | Counts as covered. |
| `medium` | Architecture contract evidence plus multiple product/action terms, or boundary/value terms plus product terms. | Counts as covered. |
| `weak` | Only broad or partial terms match. | Fails C4 as `weak_evidence`; do not send to human review. |
| `none` | No usable architecture evidence. | Fails C4 as `missing_architecture`. |

Weak or missing architecture evidence is a spec refinement issue, not a human-review shortcut. The static decision should be `NEEDS_SPEC_REFINEMENT` unless behavior complexity also fails, in which case `NEEDS_DECOMPOSITION` takes priority.

If files are named differently, map them explicitly in the report. Do not judge leaf readiness from a root PRD's high-level Acceptance Gherkin when a detailed `testcase.feature` exists. Judge the current node's testcase.

For derive-layer PRDs, treat derived IDs as the current-layer requirements:

- Current requirements include IDs such as `REQ-D001`, `NFR-D001`, and `REQ-IF001`.
- Parent IDs in metadata such as `parent_req: REQ-004` are traceability metadata, not current-layer requirements that need direct testcase tags.
- Traceability should map `REQ-Dxxx -> parent_req REQ-xxx -> testcase @REQ-Dxxx -> architecture evidence`.
- Do not fail C4 merely because testcase tags use the derived ID rather than the parent ID.

## Workflow

1. Run Leaf Gate. The script first prepares evidence, then runs static checks:

```bash
python scripts/run_leaf_gate.py <node-dir> --output <node-dir>/leaf-gate.static.json
```

2. Confirm the generated `traceability.md` and `risks.md` reflect the current node scope. If they show missing testcase coverage, missing architecture evidence, or open high risk, do not override that gap in the LLM judgement.
3. Read `references/leaf_gate_rubric.md`.
4. Read `references/llm_judge_prompt.md` and judge the five criteria against the PRD, feature file, architecture, traceability, risks, and static report.
5. Produce a final `leaf-gate.report.json` using `references/report_template.json`.
6. Decide with these statuses only:

| Decision | Meaning |
| --- | --- |
| `LEAF_READY` | The node may enter vibecoding. |
| `NEEDS_DECOMPOSITION` | Generate lower-layer PRDs. |
| `NEEDS_SPEC_REFINEMENT` | Required artifacts, contracts, tests, or mappings are missing or ambiguous. |
| `HUMAN_REVIEW` | High risk, low confidence, or policy-sensitive scope needs human judgement. |

## Hard Rules

- Do not return `LEAF_READY` from static checks alone.
- Do not return `LEAF_READY` unless all five criteria pass.
- Every LLM PASS or FAIL must cite evidence from an artifact or the static report.
- If evidence is missing, choose `NEEDS_SPEC_REFINEMENT`, not PASS.
- If unresolved high risk remains, choose `HUMAN_REVIEW` or `NEEDS_DECOMPOSITION`.
- If a scenario is a system-level story hiding multiple subsystems, fail behavior complexity even if the scenario count is low.
- Do not treat generated `traceability.md` or `risks.md` as proof by themselves. They are evidence indexes; judge the underlying PRD, testcase, architecture, and validation report.
- Do not upgrade `weak_evidence` during semantic judgement. Weak evidence remains a static C4 failure and should lead to spec refinement or decomposition, not `HUMAN_REVIEW`.

## Five Criteria

Use the rubric file for full details. In brief:

| ID | Criterion | Static checker role | LLM judge role |
| --- | --- | --- | --- |
| C1 | Behavior complexity is controlled | Count scenarios, examples, steps, tags, coverage | Detect hidden multi-subsystem stories |
| C2 | Contract boundary is clear | Check contract fields | Judge semantic completeness and boundary width |
| C3 | AI implementation context is controlled | Estimate size, TODOs, open questions, references | Detect hidden assumptions and new architecture decisions |
| C4 | Automatic verification is decidable | Check traceability and executable assertions | Judge observability and assertion quality |
| C5 | Residual risk is low and decomposition gain is low | Check risk register and unresolved items | Judge whether deeper decomposition still reduces risk |

## Common Mistakes

| Mistake | Correct response |
| --- | --- |
| Counting only root PRD Acceptance scenarios | Use the current node's detailed `testcase.feature`. |
| Treating low scenario count as leaf readiness | Check hidden domains and scenario breadth. |
| Letting the LLM decide without static checks | Run the checker first and cite its output. |
| Treating missing risk files as no risk | Mark the node as `NEEDS_SPEC_REFINEMENT`. |
| Feeding an entire architecture working directory | Prefer `architecture/output` plus `architecture/validation-report.md`; avoid intermediate drafts unless cited by the final package. |
| Treating generated evidence as self-certifying | Use traceability and risks as indexes back to source artifacts. |
| Treating weak keyword overlap as coverage | Require `strong` or `medium`; weak evidence fails C4. |
| Passing a node with vague Then clauses | Fail C4 unless outcomes are observable and assertable. |

## Resources

- `scripts/run_leaf_gate.py`: deterministic static checker and optional final decision combiner.
- `references/leaf_gate_rubric.md`: full criteria, proof intent, and pass/fail guidance.
- `references/llm_judge_prompt.md`: structured LLM judgement prompt.
- `references/report_template.json`: final report shape.
- `references/pressure_scenarios.md`: test scenarios for future skill validation.
