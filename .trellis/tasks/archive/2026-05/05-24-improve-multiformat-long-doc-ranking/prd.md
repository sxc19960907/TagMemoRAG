# Improve Multiformat Long Document Ranking

## Goal

Use the newly added multi-format real-knowledge benchmark to improve or correct the first real weakness it exposes, focusing on long PDF and DOCX-derived documents.

## Findings

- The multi-format benchmark materializes real HTML, PDF, and DOCX sources and builds successfully.
- Retrieval eval currently reports weak aggregate metrics (`hit@k=0.666667`, `mrr=0.444444`) even though the answer diagnostic passes.
- Inspecting `actual_top_k` shows the DOCX case returns the right EPA waiver-certification chunks in ranks 2, 3, and 6.
- The DOCX eval case fails because each expected entry requires phrases that are split across adjacent chunks, so no single result can match the expectation. This is an eval modeling issue, not a retrieval failure.

## Requirements

- Adjust the DOCX multi-format eval case so each relevant expectation maps to evidence that can appear in a single real chunk.
- Preserve the user's requirement that source documents remain real online documents; do not add synthetic source text.
- Rerun the real multi-format retrieval and answer diagnostics.
- Only change retrieval/ranking code if the corrected eval still exposes an actual ranking failure.

## Acceptance Criteria

- [ ] `multiformat-docx-epa-waiver-certifications` has meaningful non-zero hit/recall after fixture correction.
- [ ] Multi-format retrieval eval improves from the previous weak aggregate metrics without loosening to fake data.
- [ ] Multi-format answer eval remains green.
- [ ] Focused tests and `git diff --check` pass.

## Out of Scope

- Do not broaden the benchmark with more sources in this task.
- Do not tune ranking against a malformed expectation.
