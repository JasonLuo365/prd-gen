---
name: leaf-gate
description: Use when deciding whether a layered PRD node with a PRD, testcase.feature, architecture, traceability, or risk artifacts should be decomposed further, refined, reviewed by a human, or sent to vibecoding.
---

# Leaf Gate

## Overview

Leaf Gate is the stopping decision for an explainable layered development flow. Use it after a current-layer PRD, testcase, architecture, and architecture-validation pass exist, before choosing between deeper decomposition and vibecoding.

The gate is not a prompt-only review. Run deterministic checks first, then perform semantic judgement with evidence.

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

If files are named differently, map them explicitly in the report. Do not judge leaf readiness from a root PRD's high-level Acceptance Gherkin when a detailed `testcase.feature` exists. Judge the current node's testcase.

## Workflow

1. Run the static checker:

```bash
python scripts/run_leaf_gate.py <node-dir> --output <node-dir>/leaf-gate.static.json
```

2. Read `references/leaf_gate_rubric.md`.
3. Read `references/llm_judge_prompt.md` and judge the five criteria against the PRD, feature file, architecture, traceability, risks, and static report.
4. Produce a final `leaf-gate.report.json` using `references/report_template.json`.
5. Decide with these statuses only:

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
| Passing a node with vague Then clauses | Fail C4 unless outcomes are observable and assertable. |

## Resources

- `scripts/run_leaf_gate.py`: deterministic static checker and optional final decision combiner.
- `references/leaf_gate_rubric.md`: full criteria, proof intent, and pass/fail guidance.
- `references/llm_judge_prompt.md`: structured LLM judgement prompt.
- `references/report_template.json`: final report shape.
- `references/pressure_scenarios.md`: test scenarios for future skill validation.
