# Leaf Gate Rubric

## Decision Object

Leaf Gate judges a validated node `N = PRD + testcase + effective architecture + traceability + risks`.

```text
ContinueLayering(N)
iff another layer materially improves
behavior isolation
or boundary clarity
or implementation-context control
or verification independence
or risk isolation.
```

The only final decisions are `CONTINUE_LAYERING` and `STOP_LAYERING`.

Artifact incompleteness is not a layering result. Missing or weak upstream evidence produces `INPUT_ERROR` without a `decision` field.

## Preconditions

Before judging decomposition gain, require:

- current-node PRD and testcase;
- an effective architecture package that has completed the upstream testcase-driven mock/validation loop;
- complete caller-visible contract fields;
- current-layer requirement-to-testcase-to-primary-architecture traceability;
- no unresolved TODO/TBD or implementation-controlling open question;
- no unresolved high risk left by the upstream validation loop;
- a valid semantic judgement format when producing a final decision.

A separate architecture validation report is optional. The validation process may already be reflected in a flattened final architecture package.

## C1 Behavior Complexity

Return `CONTINUE_LAYERING` when behavior can be separated into meaningful child nodes:

- multiple independent behavior families or business loops;
- one scenario hiding several subsystems;
- composite scenarios spanning many unrelated requirements;
- a large Scenario Outline masking distinct behavior;
- root-level acceptance stories that are not implementation-unit tests.

Return `STOP_LAYERING` on C1 when behavior is one tight implementation family and another split would be arbitrary.

Static evidence includes scenario points, expanded cases, step counts, tags, composite scenarios, and normalized scenarios. Semantic evidence identifies hidden domains and business loops.

## C2 Boundary Width

Contract completeness is a prerequisite, not the decision itself.

Return `CONTINUE_LAYERING` when the complete architecture still contains multiple independently implementable contracts, owners, state machines, consistency boundaries, or unrelated side-effect groups.

Return `STOP_LAYERING` on C2 when the node exposes one cohesive semantic boundary. Multiple files do not imply multiple boundaries, and one file does not imply one boundary.

Only the primary architecture package can establish boundary evidence. Optional validation, remediation, and supporting files cannot replace it.

## C3 Implementation Context

Return `CONTINUE_LAYERING` when separable responsibilities make a single implementation session exceed the configured context budget or require too many simultaneous architectural views.

Return `STOP_LAYERING` on C3 when the implementation pack is bounded and no child split would meaningfully reduce cognitive load.

TODOs and open questions are precondition errors, not evidence for layering.

## C4 Independent Verifiability

Trace completeness and assertable outcomes are prerequisites.

Return `CONTINUE_LAYERING` when correct verification still requires several independently executable behavior groups, environments, dependency harnesses, or failure domains to be tested together.

Return `STOP_LAYERING` on C4 when the node can be implemented and automatically checked as one independent unit.

Weak or missing architecture evidence is an upstream validation error, not a reason to create child nodes.

## C5 Decomposition Gain

Return `CONTINUE_LAYERING` only when proposed children materially improve at least one of:

- responsibility ownership;
- contract isolation;
- consistency or state isolation;
- implementation-context size;
- automatic-test isolation;
- safety, privacy, concurrency, recovery, or external-dependency isolation;
- parallel implementation without shared hidden decisions.

Return `STOP_LAYERING` when further children would be pass-through wrappers, mechanical layers, arbitrary document sections, or fragments that cannot be implemented and tested independently.

## Final Rule

Return `CONTINUE_LAYERING` when deterministic complexity is conclusive or any evidence-backed semantic criterion shows material decomposition gain.

Return `STOP_LAYERING` only when:

- all preconditions pass;
- deterministic checks do not require another layer;
- every semantic criterion is `pass` with evidence and sufficient confidence;
- further decomposition has no material benefit.

Warnings, missing evidence, low confidence, malformed judgement, or upstream completeness gaps are evaluation errors. They do not create a third decision.

## Architecture Evidence Roles

- `architecture_files`: effective primary package; authoritative for C2 and C4.
- `architecture_validation_files`: optional provenance/risk evidence; never required as a file and never substitutes for primary evidence.
- `architecture_remediation_files`: planned corrections only.
- `architecture_supporting_files`: non-authoritative source material unless promoted by the manifest.
- `architecture_manifest` and `architecture_selection`: explain how the primary set was chosen.

The package may be flat or nested. Do not infer authority from numbering, language, filename, file size, or directory name alone.
