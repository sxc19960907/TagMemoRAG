# MVP Delivery Guide

## Goal

Create a single delivery guide that lets a pilot operator understand what TagMemoRAG currently is, configure the local/live provider profile, run verification, and use the core RAG flows without stitching together multiple runbooks.

## Requirements

- Document current product status honestly as pilot-ready / technical pre-production, not a full production platform.
- Cover prerequisites, secrets, Docker provider services, config validation, managed PDF import/rebuild, retrieve/search/answer, smoke/pilot verification, and report retention.
- Link to deeper runbooks rather than duplicating every operational detail.
- Include a concise capability matrix: shipped, default-off/experimental, deferred.
- Include troubleshooting for common setup/provider failures.
- Keep all examples sanitized; no credential values or runtime payload content.

## Acceptance Criteria

- [x] `docs/mvp-delivery-guide.md` exists and is readable as the primary handoff document.
- [x] The guide includes a copy-pasteable happy path for local live-provider verification.
- [x] The guide points to existing detailed docs for deployment, smoke, pilot, and live evidence.
- [x] The guide states remaining deferred production gaps.
- [x] Sanitization check finds no secret values or raw runtime payloads.
