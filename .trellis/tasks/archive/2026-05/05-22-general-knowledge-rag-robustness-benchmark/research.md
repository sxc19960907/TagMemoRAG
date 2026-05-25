# General Knowledge Robustness Benchmark Research

## Purpose

Use product manuals as the first stress-test domain, then expand TagMemoRAG
quality checks toward public knowledge sources that represent different RAG
failure modes.

## Candidate Source Families

| Family | Example public sources | What it tests |
|---|---|---|
| Software documentation | Python docs, GitHub Docs | Code terms, exact API names, versioned concepts, procedural answers |
| Government / policy documents | IRS publications and instructions | Long PDFs/HTML, legalistic language, eligibility rules, caveats |
| Health / public information | MedlinePlus / NIH topic pages | High-stakes answer caution, symptom/treatment distinctions, source fidelity |
| Help-center / FAQ content | Public support centers and FAQ pages | Short pages, repeated templates, conversational user intents |
| Product manuals | Existing `product_manuals/`, ManualsLib samples | PDF extraction noise, tables, model numbers, troubleshooting, mixed language |

## First Slice

The first implementation slice should not download and commit third-party
content. It should harden the eval matcher against extraction artifacts found
during real manual validation:

- PDF/OCR line breaks inside expected phrases.
- Repeated whitespace or tabs from layout extraction.
- Non-printing control characters inside words or phrases.

This keeps future benchmark metrics from undercounting valid hits simply because
the public source extractor introduced formatting noise.

## Later Benchmark Shape

For each source family, create a small `.tmp` or ignored materialized corpus and
a checked-in eval suite that references only stable, attributable source
identities and short expected evidence strings. Long third-party content should
remain uncommitted unless license review explicitly permits checked-in fixtures.
