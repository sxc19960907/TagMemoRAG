# Auth Role Boundary Trial Review

## Goal

Review and harden trial-facing auth and role boundary clarity across browser admin and Q&A surfaces.

## Requirements

- Keep existing auth scopes and enforcement unchanged.
- Make People & Access explain the trial-facing scope boundary:
  - `search` for normal Q&A/search/retrieve use;
  - `rebuild` for manual indexing and rebuild operations;
  - `admin` for People & Access, key generation, and cross-admin operations.
- Make missing/insufficient token failures on People & Access easier for operators to understand.
- Preserve safe key handling: generated plaintext is one-time only, hashes remain hidden.
- Keep local auth-disabled demos usable without requiring a token.

## Acceptance Criteria

- [ ] People & Access shows a browser-visible access boundary guide.
- [ ] Auth-enabled admin endpoints still require an admin token.
- [ ] Search-scope tokens still receive a 403 on People & Access admin APIs.
- [ ] People & Access UI maps 401/403 responses to actionable admin-token guidance.
- [ ] Focused unit/static tests pass before commit and archive.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
