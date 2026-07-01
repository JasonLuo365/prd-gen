# Pressure Scenarios

Use these scenarios to test whether agents apply the skill rather than shortcutting the decision.

## Scenario 1: Low Scenario Count Trap

Input: A root PRD has fewer than 10 Gherkin scenarios, but the main scenario contains messaging, planning, authorization, execution, status, recovery, and results.

Expected: The agent must not mark `LEAF_READY` from scenario count. It should fail C1 and recommend decomposition.

## Scenario 2: Missing Architecture Contract

Input: PRD and feature are present, but architecture only lists component names.

Expected: The agent must return `NEEDS_REFINEMENT` with an `architecture` route or fail C2. It must not invent contracts.

## Scenario 3: Vague Then Clauses

Input: Feature uses Then clauses like "system handles errors safely" without observable assertions.

Expected: The agent must fail or warn C4 and request refinement.

## Scenario 4: High Risk Remaining

Input: Authorization and destructive operations remain in one node, with unresolved policy questions.

Expected: The agent must not return `LEAF_READY`; choose `NEEDS_DECOMPOSITION` or `NEEDS_REFINEMENT` with an `owner_decision` route.
