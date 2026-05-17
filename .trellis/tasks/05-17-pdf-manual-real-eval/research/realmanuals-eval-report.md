# Real Manuals Eval — Empirical Findings

> 2026-05-17 — Step B of "回归初心" reflection.
> KB built from 5 production PDF manuals (236 pages, 182k chars total)
> with siliconflow Qwen3-VL-Embedding-8B (4096 dim).

## TL;DR

**The wave-rag pipeline (current branch state) does NOT meet production
quality expectations on real PDF manuals**. Top-K retrieval is heavily
contaminated by cross-product chunks even with a 4096-dim semantic
embedder. Root cause is a structural problem inside our pipeline that
**no algorithm flag flip can fix**:

1. PDF parser produces one chunk per page with `header="Page N"`. The
   wave-search graph loses real header/section hierarchy → sibling /
   parent-child structure edges degenerate to consecutive-only.
2. Page-level chunks mix multiple unrelated topics (e.g. ASKO washer
   page 21 contains "EN 60456 testing standard" + "drum capacity" + "drain
   motor pipe diameter" all interleaved). 4096-dim embeddings averaged
   over a noisy page lose discriminative signal.
3. Cross-product semantic similarity is high (washer / dryer / dishwasher
   share lots of vocabulary: drain, water, detergent, program). Without
   `metadata.product_category` filter, top-K is dominated by whichever
   manual happens to have a chunk with high lexical overlap to the query.

## Evidence — top-K source distribution per query

12 queries over the realmanuals KB (siliconflow + spike-on default).
"sf_top1" is the source_file of the first result; "match" = whether
that source matches the query's intended product.

| Query | sf_top1 | Intended | Match? |
|---|---|---|---|
| 洗衣機排水馬達在哪裡 | refrigerator | washer | ❌ |
| 洗衣機洗劑粉盒怎麼用 | washer | washer | ✅ |
| 洗衣機怎麼選擇洗程 | washer | washer | ✅ |
| 洗衣機兒童安全保護 | refrigerator | washer | ❌ |
| How to choose drying program step by step | refrigerator | dryer | ❌ |
| laundry not dried takes too long | refrigerator | dryer | ❌ |
| dryer ionizer system | refrigerator | dryer | ❌ |
| oven cooking system hot air bottom heater | oven | oven | ✅ |
| oven steam clean function | oven | oven | ✅ |
| refrigerator ice maker cubed crushed | refrigerator | refrigerator | ✅ |
| refrigerator display controls temperature | refrigerator | refrigerator | ✅ |
| refrigerator troubleshooting noise | refrigerator | refrigerator | ✅ |

**Top-1 product correctness: 7/12 (58%)** — and 4 out of 5 wrong cases
incorrectly route to the **refrigerator** PDF (the largest in the set
at 53k chars and most pages with English text — which Qwen-VL evidently
favors).

## What this means for "wave vs plain KNN" (the original reflection)

The original PRD命题 was: "在客服 RAG 场景，浪潮算法（图传播）vs plain
KNN，哪个更好？"

**This eval doesn't actually answer the question yet** because both
configurations would inherit the same input quality problems above:

- `vec-only` (KNN) on these chunks would be **at least as bad** —
  losing the wave_search step doesn't help when the chunks themselves
  mix topics.
- `wave-baseline` (current default) on these chunks doesn't get to
  use its strength either, because the structure-graph is mostly flat
  (`Page N` → `Page N+1` consecutive edges only).

The empirical conclusion is: **the wave algorithm (and any algorithm)
needs structural input it doesn't currently get**. The work to do next
is **NOT** more algorithm phases or constant tuning. It's **PDF →
Markdown with section headers**, so the KB graph captures real
parent/child/sibling relationships, and chunk size matches a section
not a page.

## Findings against the "已有移植" scope

Re-checking what we built in Phases 1-4 against this signal:

| Component | Verdict on real PDF data | Note |
|---|---|---|
| Phase 1 cooccurrence + spike | Inert | spike processes tags but PDF chunks have only `[washer]` etc. — no real tag co-occurrence |
| Phase 2a EPA real-PCA | Inert | EPA needs ≥4 distinct tag clusters; our metadata gives 5 (one per category), but with 1 manual per category basis estimation is unreliable |
| Phase 2b ResidualPyramid | Inert | Pyramid needs many tags per chunk; PDF chunks get only `[<category>]` |
| Phase 3 cross-domain resonance | Zero | EPA dominant axes don't form |
| Phase 3.5 intrinsic_residuals | Zero | Single-tag chunks → residual energy degenerate |
| Phase 4 V8 geodesicRerank | Disabled (KEEP_OFF) | Same query-level concerns from earlier readiness eval |

In short: every Phase 1-4 mechanism is **idle on this input** because
the input doesn't carry the structure / tags / co-occurrences these
mechanisms operate on.

## What to do next (recommendation, not auto-execution)

Three concrete options, ranked by likely impact:

### Option A — PDF parser upgrade (highest value, biggest scope)

Replace `_parse_pdf` (one chunk per page) with a real Markdown
extractor that:
- Detects section headers (font size / boldness / capitalization
  heuristics, or a library like `unstructured` / `marker-pdf`).
- Produces chunks scoped to sections, with proper `header` /
  parent-child path.
- Optional: write the parsed Markdown to `product_manuals/<category>/
  <file>.md` next to the PDF, so future rebuilds use the cleaner
  representation.

This is a separate Trellis task (medium-large). Once landed, re-run
this same diag and the algorithm phases finally get input they can
work on.

### Option B — Tag / metadata enrichment (medium value)

Even with one-chunk-per-page, if each chunk gets richer
`metadata.tags` (e.g. extracted from page text via keyword
extraction), the cooccurrence + spike pipeline starts to have
something to chew on. ASKO W6564 page 7 mentions "排水馬達 / 洗劑粉盒 /
電源開關" — that page should carry tags `["drain-motor",
"detergent-drawer", "power-switch"]`, not just `["washer"]`.

This unblocks Phase 1-4 algorithms partially, without solving the
section-structure problem.

### Option C — Just accept and move on (lowest investment)

If the wave-rag project's deployment scenario is short, structured
documents (like the original `coffee_machine.md` with H1/H2/H3
headers), then the algorithm is fine on its intended input — PDFs
are just out of scope until a parser upgrade. Document this clearly,
flag PDF support as alpha.

## My recommendation

**Option A** for the long term, **Option C** for now. The wave-RAG
pipeline does what it claimed to do on **structured input**; PDF
deserves a separate task with its own scope. Don't keep tuning
algorithm flags hoping they'll fix what is fundamentally a parser
problem.

The 12-query realmanuals fixture stays in the repo as-is (with
placeholder ground truth) — it's evidence for "why we're not on
PDFs yet", not a fixture for CI gating.

## Concrete deliverables of this task

- `scripts/ingest_real_manuals.py` (corrected after BSA→oven /
  DH→dryer reclassification)
- `tests/fixtures/eval/realmanuals.jsonl` (12 query placeholder
  fixture; not in CI)
- `data/realmanuals/` KB (gitignored, but reproducible via build cmd)
- This report.

Three weeks of algorithm work, four readiness flags pinned KEEP_OFF,
and one PDF-parser fix is what stands between the current branch and
"works on production manuals". The flags aren't useless; they're just
waiting for input they can act on.
