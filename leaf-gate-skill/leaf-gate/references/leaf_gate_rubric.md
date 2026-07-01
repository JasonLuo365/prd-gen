# Leaf Gate Rubric

## Decision Object

Given a node `N = PRD + testcase.feature + architecture + traceability + risks`, `LeafReady(N)` means:

The node is small and explicit enough for an AI implementation session, and the result can be automatically checked without further decomposition reducing major risk.

Operational definition:

```text
LeafReady(N)
iff
C1 behavior complexity is controlled
and C2 contract boundary is clear
and C3 AI implementation context is controlled
and C4 automatic verification is decidable
and C5 residual risk is low and decomposition gain is low
```

This is an operational sufficiency and necessity claim for the process, not a guarantee that the implementation will be correct on the first attempt.

## C1 Behavior Complexity Is Controlled

Pass when the current node's `testcase.feature` describes a small behavior surface:

- Scenario points are within the configured threshold.
- A scenario does not hide multiple subsystems or multiple business loops.
- Each scenario verifies one clear behavior or one tight behavior family.
- Scenario Outline examples are bounded and not disguising broad product scope.

Static evidence:

- scenario count
- expanded case count
- max steps per scenario
- max REQ tags per scenario
- untagged scenarios

LLM evidence:

- whether scenario language indicates a product-level end-to-end story
- hidden domains or subsystems inside a single scenario
- whether scenarios are leaf-level tests or root-level acceptance stories

Fail examples:

- "User completes remote office task" contains Telegram input, planning, authorization, execution, status, recovery, and result reporting.
- A single scenario maps to many unrelated requirements.

## C2 Contract Boundary Is Clear

Pass when the node has a small semantic contract:

- inputs
- outputs
- errors
- states or state transitions
- side effects
- dependencies

Static evidence:

- architecture artifact exists
- required contract fields or terms appear

LLM evidence:

- whether the contract is semantically complete
- whether the boundary is too wide
- whether the contract leaks internals instead of hiding implementation details

Fail examples:

- The architecture names several services but no caller-visible contract.
- The node requires multiple unrelated contracts to describe its behavior.

## C3 AI Implementation Context Is Controlled

Pass when vibecoding can happen in a bounded implementation session:

- Required artifacts fit a reasonable context budget.
- No unresolved TODO/TBD/Open Question controls implementation behavior.
- The AI does not need to invent business rules.
- The AI does not need to make new architecture decisions.

Static evidence:

- estimated token count
- artifact count
- TODO/TBD/open question count
- external reference count

LLM evidence:

- hidden assumptions
- missing business rules
- unclear ownership or dependencies
- decisions the AI would have to guess

Fail examples:

- "Handle safely" appears without a concrete safe/unsafe rule.
- "Simple task" is referenced but not defined.

## C4 Automatic Verification Is Decidable

Pass when implementation correctness can be checked automatically:

- Requirements map to scenarios.
- Scenarios map to architecture components or contracts.
- Then clauses describe observable outcomes.
- Tests can fail for wrong behavior.

Static evidence:

- REQ -> Scenario coverage
- traceability file exists
- unmapped requirements
- untagged scenarios

LLM evidence:

- whether Then clauses are assertable
- whether checks observe behavior rather than implementation vibes
- whether nonfunctional requirements have measurable probes

Fail examples:

- Then "system handles it reasonably".
- Performance requirement exists without measurement point.

## C5 Residual Risk Is Low And Decomposition Gain Is Low

Pass when no unresolved high risk remains and further decomposition is unlikely to improve clarity:

- No unresolved high risk in the risk register.
- Open questions are not implementation-blocking.
- External dependencies have known contracts or stubs.
- Further decomposition would only create pass-through wrappers or mechanical layers.

Static evidence:

- risk register exists
- unresolved high-risk count
- open question count

LLM evidence:

- whether deeper decomposition would reduce risk
- whether the current node crosses safety, permission, data consistency, concurrency, or recovery boundaries
- whether proposed children would be deep modules or shallow forwarding

Fail examples:

- Authorization, high-risk actions, and recovery policy are still bundled in one node.
- Safety-sensitive behavior depends on an undefined policy.

## Decision Rule

Return `LEAF_READY` only when:

- static checks have no hard failure,
- LLM judgement marks all criteria `pass`,
- every pass includes evidence,
- no unresolved high risk remains,
- confidence is at or above the configured minimum.

Otherwise:

- `NEEDS_DECOMPOSITION` when behavior or boundaries are too large,
- `NEEDS_REFINEMENT` when required artifacts, definitions, contracts, testcase mapping, architecture evidence, owner decisions, or risk dispositions are missing.

For `NEEDS_REFINEMENT`, include `refinement_routes` with one or more targets:

- `architecture`: contract fields, dependencies, side effects, architecture evidence, risk mitigations that belong in architecture.
- `testcase`: missing scenario coverage, missing tags, unobservable Then clauses, metric/test probes.
- `owner_decision`: product, business, compliance, risk-acceptance, or low-confidence semantic decisions that generation must not invent.
