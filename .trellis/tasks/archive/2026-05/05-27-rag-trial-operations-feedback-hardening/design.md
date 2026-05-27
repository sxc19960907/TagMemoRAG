# RAG Trial Operations And Feedback Hardening Design

## Scope

This parent task organizes the post-demo trial operations phase. It should usually create child tasks for implementation and verification instead of carrying broad code changes directly.

## Operating Model

The trial loop has four surfaces:

1. User QA: users ask questions, inspect evidence, and submit helpful/not-helpful feedback.
2. Operator review: Retrieval Quality and readiness/report pages show what needs attention.
3. Regression growth: high-value feedback becomes eval cases and browser/pilot gates.
4. Release confidence: retained reports, docs, and CI/GitHub status show whether the system is safe to keep using.

## Child Task Boundaries

Child tasks should be independently shippable. Each child should define:

- the browser or CLI surface under review;
- the user/operator failure mode it reduces;
- the exact validation commands;
- whether it affects docs only, UI, backend contracts, or tests.

## Compatibility

The existing browser-first QA path is accepted as the baseline. New work should avoid destabilizing it and should run `readiness browser-qa` when touching QA, feedback, retrieval quality, or browser navigation.

## Network

GitHub push is allowed now that the previous push succeeded, but CI remains authoritative after each push. Live-provider checks remain opt-in unless a child task explicitly targets provider/deployment behavior.
