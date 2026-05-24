# Design

## Scope

This task is a long-horizon quality program for the existing deterministic/local RAG stack. It is not a rewrite and not a new product surface.

## Work Streams

1. Baseline matrix
   - Run the existing real-data retrieval and answer diagnostics.
   - Save summaries under `.tmp/eval/` and retain a task-level summary in `quality-program-notes.md`.

2. Coverage expansion
   - Inspect current fixture gaps.
   - Add stable real-source fixtures or diagnostics only when they expose a meaningful missing capability.
   - Keep fetched third-party content in runtime directories such as `.tmp/`.

3. Quality improvement batch
   - Use per-case reports to identify a concrete weakness.
   - Prefer local deterministic improvements first: parser/source cleanup, lexical/fusion tuning, context packing, answer filtering, or eval authoring corrections.
   - Reject changes that improve one slice while regressing the full baseline matrix unless the trade-off is explicitly accepted in a follow-up task.

4. Full regression
   - Rerun all matrix slices after each meaningful batch.
   - Record both wins and rejected attempts.

## Boundaries

- WAVE/geodesic remains default-off and out of promotion scope.
- External rerankers are out of scope for this task.
- Downloaded third-party document bodies stay out of git.
- API/CLI restructuring is out of scope.

## Compatibility

Changes should preserve existing CLI/API contracts and eval fixture schemas unless a specific diagnostic proves a schema change is needed. New scripts should be opt-in and deterministic when possible.
