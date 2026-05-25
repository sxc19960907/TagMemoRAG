# Implementation Plan

- [x] Create child task.
- [x] Define inventory requirements.
- [x] Collect committed eval suite metadata.
- [x] Collect local materialized corpus paths and slice names.
- [x] Collect retained report/gate output status and aggregate metrics.
- [x] Write `retained-corpus-inventory.md`.
- [x] Privacy-scan the inventory artifact.
- [x] Update parent program log with result and next recommendation.
- [ ] Commit the child artifacts and parent link/log updates.
- [ ] Archive this child task.

## Verification

- Inventory privacy scan:
  `rg -n "actual_top_k|raw snippet|provider_response|embedding|vector|Authorization|api_key|retrieved snippet|raw query|raw diagnostic|BEGIN|SECRET|sk-" .trellis/tasks/05-25-05-25-retained-corpus-inventory/retained-corpus-inventory.md .trellis/tasks/05-25-05-25-general-rag-retained-corpus-monitoring/program-log.md || true`
  returned no matches.
