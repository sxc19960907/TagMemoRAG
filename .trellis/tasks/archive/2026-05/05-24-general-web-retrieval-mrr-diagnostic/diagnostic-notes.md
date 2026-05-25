# Diagnostic Notes

## Baseline

Source reports:

- `.tmp/eval/release-readiness-after-fit-compaction-defaults.json`
- `.tmp/eval/general-web-after-evidence-prior.json`

Current release-readiness status is `warning` only because
`general_web_retrieval` is below the MRR target:

- `hit@k=1.0`
- `recall_at_k=0.928571`
- `MRR=0.651361`
- warning target: `MRR >= 0.75`

All other release-readiness stages are currently green after the archived
fit-aware context merge compaction task.

## Weak Cases

### `github-hello-world-repository`

- Case metrics: `MRR=0.166667`, `recall_at_k=1.0`.
- Expected evidence appears at ranks 6 and 8.
- Higher-ranked chunks are related to the same tutorial and share many query
  terms, but they are mostly tutorial overview, page-source/title text, or
  workflow/action instructions.
- `lexical_evidence_score` is not a useful separator here:
  - rank 1 overview/action chunk: `0.605`
  - rank 6 README/Markdown expected chunk: `0.4213`
  - rank 8 repository/folder expected chunk: `0.3088`
- Body query-term coverage also does not isolate expected evidence:
  - rank 3 non-expected chunk covers `6/8` terms
  - rank 6 expected chunk covers `5/8` terms
  - rank 8 expected chunk covers `3/8` terms

Interpretation: this case exposes a real ranking issue for multi-intent queries.
The expected evidence is more definition-style, but broad action/overview chunks
still have stronger lexical overlap. A broad evidence prior would likely keep
helping the wrong chunks.

### `github-hello-world-pull-request`

- Case metrics: `MRR=0.25`, `recall_at_k=1.0`.
- Expected evidence appears at rank 4.
- Rank 1 is a broad tutorial overview with strong overlap across branches,
  commits, pull requests, workflow, create, and review terms.
- Rank 2 is also closely related review/merge workflow text.
- `lexical_evidence_score` again does not safely identify the expected chunk:
  - rank 1 overview chunk: `0.7378`
  - rank 2 related workflow chunk: `0.6378`
  - rank 4 expected pull-request definition chunk: `0.6078`

Interpretation: this is a mild ranking issue, but the competing chunks are
answer-relevant enough that a generic action/overview penalty is risky. The
expected chunk is definition-style, yet action/workflow terms are part of the
query and part of good answer evidence.

### `mdn-http-cache-no-cache-private`

- Case metrics: `MRR=0.142857`, `recall_at_k=0.5`.
- One expected evidence item appears at rank 7; the other expected item is
  outside top-k.
- Ranks 1 and 2 are semantically relevant private-cache evidence:
  - rank 1 explains that a private cache is tied to one client and can store a
    personalized response because it is not shared with other clients.
  - rank 2 says personalized content should be stored only in a private cache
    with the `private` directive.
- Rank 8 includes both `no-cache` and `private` directive guidance, but it does
  not match the exact expected strings.
- `lexical_evidence_score` prefers non-expected chunks:
  - rank 2 non-expected private-directive evidence: `0.6733`
  - rank 3 non-expected no-cache implementation note: `0.6733`
  - rank 7 expected private leak-prevention evidence: `0.5433`
  - rank 8 non-expected combined no-cache/private directive evidence: `0.5433`

Interpretation: this case may be partly an eval expectation gap rather than a
pure retrieval failure. Several higher-ranked chunks are useful evidence for the
query but are not counted because the fixture matches only two exact support
strings.

## Signal Review

Checked deterministic local features:

- matched expected indexes
- retrieval score
- `lexical_evidence_score`
- body and heading query-term coverage
- compact-window term overlap
- definition cue words
- overview cue words
- action/workflow cue words
- page/source chrome indicators

No safe general ranking signal emerged:

- Strong lexical overlap often belongs to broad overview/action chunks.
- Definition cues help some expected chunks but also appear in useful
  non-expected chunks.
- Action/workflow cues cannot be broadly penalized because pull-request queries
  legitimately ask for workflow, review, and merge evidence.
- MDN higher-ranked non-expected chunks appear substantively relevant, so pushing
  them down for exact-string fixture compliance would risk answer quality.

## Decision

Do not make a retrieval scoring change in this batch.

A broad boost, penalty, or source/title weighting adjustment is unsafe based on
the current evidence. The next safe path is to either:

- refine the general-web fixture so it accepts multiple independently useful
  evidence chunks for the MDN private/no-cache case, and then re-evaluate whether
  the remaining MRR gap is real; or
- add a dedicated diagnostic tool/report that compares expected-string matching
  with answer-useful evidence labels before changing ranking.

This preserves current behavior and avoids introducing function differences to
force the benchmark over the MRR threshold.
