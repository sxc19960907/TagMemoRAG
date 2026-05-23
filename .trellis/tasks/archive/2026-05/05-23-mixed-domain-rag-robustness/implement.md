# Implementation Plan

1. [x] Add `tests/fixtures/eval/mixed_knowledge.jsonl` with shared-KB cases:
   - ASKO washer drain motor from real PDF manuals
   - Hisense oven steam clean from real PDF manuals
   - GitHub README/repository from public web docs
   - Python tutorial/standard-library from public web docs
   - each case includes wrong-domain negatives

2. [x] Add `scripts/diag_mixed_domain_eval.py`:
   - CLI args for suite, docs, config, kb, top-k, output
   - optional `--stage-from-defaults` to build a temporary mixed docs directory
   - call `run_eval` instead of reimplementing retrieval
   - return exit `0` on pass, `1` on diagnostic failure, `2` on setup/schema errors

3. [x] Add unit tests for the diagnostic:
   - local mixed corpus passes positive and negative expectations
   - missing docs/setup errors are bounded

4. [x] Update docs:
   - document seeding public web docs
   - document mixed-domain diagnostic command
   - mention real product manuals are included through staging

5. [x] Validate:
   - run the new unit test
   - run the mixed diagnostic with local fixture docs
   - run the mixed diagnostic against real `product_manuals/` and `.tmp/general-web-eval/general_web` if present
   - run focused eval/diagnostic tests touched by this task
