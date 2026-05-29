# CI actions runtime maintenance

## Goal

Remove the GitHub Actions Node.js 20 deprecation warning from project workflows while preserving the current Quality CI and public site publishing behavior.

## Requirements

- Update workflow actions that currently run on deprecated Node.js 20 runtimes when newer compatible major versions are available.
- Preserve Quality CI triggers for pull requests and pushes to `master` / `main`.
- Preserve public site publishing triggers and the `gh-pages` publishing behavior.
- Keep the workflows simple; do not introduce unrelated CI restructuring.
- Verify the relevant workflow YAML files parse locally where possible.
- Push and verify GitHub Actions after the change.

## Acceptance Criteria

- [ ] `.github/workflows/quality.yml` no longer uses actions that emit the Node.js 20 deprecation warning.
- [ ] `.github/workflows/pages.yml` no longer uses actions that emit the Node.js 20 deprecation warning.
- [ ] Local focused checks pass.
- [ ] Remote Quality CI passes after push.
- [ ] Public site publish workflow remains available and unchanged in behavior for site changes.
