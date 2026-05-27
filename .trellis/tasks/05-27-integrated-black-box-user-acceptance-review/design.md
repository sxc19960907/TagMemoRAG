# Integrated Black Box User Acceptance Review Design

## Scope

This task performs final acceptance review and records findings. It does not add new product scope unless browser review exposes a blocking defect.

## Review Flow

1. Seed the local demo KB with `demo library-qa`.
2. Start the local server with the demo config on a free local port.
3. Open the app in the in-app browser.
4. Review the visible QA experience:
   - first-screen guidance and active KB
   - language switch
   - three realistic questions
   - answer readability
   - citations and source cards
   - feedback handoff to Retrieval Quality
5. Run automated final gates:
   - `pilot run --include-browser-qa`
   - `readiness browser-qa`
6. Write an acceptance report in task artifacts.

## Compatibility

If no blocking defect is found, the only committed changes should be Trellis task artifacts and the acceptance report.

## Rollback

If this task changes product code, rollback follows the specific files changed. If it only records review evidence, no product rollback is needed.
