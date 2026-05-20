# Implementation Plan

1. Run local deterministic readiness smoke with `.tmp/clean-env-delivery/readiness`.
2. Run command help checks for the delivery guide commands.
3. Run unified live-provider smoke with clean output paths and `--skip-docker` if provider services are already running.
4. Add a sanitized clean-environment verification report.
5. Run sanitization checks, commit, archive, and record journal.
