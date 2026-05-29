# Real Document Boundary Notes

## Scope

Checked local real-product PDF coverage for the delivery hardening task.

## Confirmed Assets

- `product_manuals/washer/ASKO W6564.pdf`
- `product_manuals/oven/HISENSE BSA5221.pdf`
- `product_manuals/refrigerator/HISENSE HR6FDFF701SW.pdf`
- `product_manuals/dryer/HISENSE DHGA901NL.pdf`
- `product_manuals/dryer/HISENSE DHQE800BW2.pdf`

## Browser Coverage Decision

The browser real-product source-preview test now uploads three product categories:

- washer
- oven
- refrigerator

The stable Q&A assertions remain focused on washer and oven because the offline hashing profile reliably routes those category-specific questions to the expected source cards. The refrigerator PDF is still included as a third real business document category for upload, indexing, searchable state, and source-preview readiness.

## Boundary Found

The local hashing profile is not a reliable semantic router for the refrigerator Super Freeze / display-control questions when washer and oven PDFs are present in the same KB. Candidate searches often rank oven or washer chunks above the refrigerator chunks even when the refrigerator manual contains the requested section.

This is a retrieval-quality boundary, not a browser UX failure. It should be handled by later retrieval evaluation or production-provider testing rather than weakening the black-box browser assertions.

## Safe User-Facing Contract

The delivery browser test should prove:

- real PDFs from at least three product categories can be uploaded and indexed;
- source-preview assets are generated for real PDFs;
- stable washer/oven Q&A paths produce cited source cards;
- source cards and preview links do not expose storage keys, blob keys, checksums, node IDs, or anchor keys.
