# Leaf Gate Pressure Scenarios

## Hidden Product Story

A low-count testcase hides several subsystems and business loops in one scenario.

Expected: `CONTINUE_LAYERING`. Scenario count alone must not stop layering.

## Incomplete Contract

The architecture has no caller-visible error, state, side-effect, or dependency semantics.

Expected: `INPUT_ERROR` without `decision`. Leaf Gate must not invent a contract or call incompleteness a layering result.

## Weak Traceability

Requirements and scenarios exist, but the primary architecture only has broad keyword overlap.

Expected: `INPUT_ERROR` without `decision`. The upstream testcase-driven architecture validation loop owns correction.

## Validated Wide Boundary

All artifacts are complete, but the node contains several independently implementable contracts, state machines, or risk boundaries.

Expected: `CONTINUE_LAYERING` with meaningful child-boundary evidence.

## Mechanical Child Split

The proposed children merely mirror document sections or forward calls without independent behavior or tests.

Expected: `STOP_LAYERING`.

## Flattened Architecture Package

The effective architecture is a flat directory containing README and a variable set of final documents, with no separate validation report.

Expected: discover the package from manifest links/semantics. The missing validation-report file is not an error.
