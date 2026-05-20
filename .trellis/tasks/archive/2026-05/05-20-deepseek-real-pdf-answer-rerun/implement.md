# Implementation Plan

1. Ensure provider verification KB exists; rebuild ASKO/HISENSE PDFs if needed.
2. Run `/answer` through FastAPI `TestClient` with DeepSeek key only in the command environment.
3. Compare a small token budget with a larger token budget if useful.
4. Write a sanitized report under `docs/deepseek-real-pdf-answer-rerun.md`.
5. Run focused and full tests, then archive and commit.
