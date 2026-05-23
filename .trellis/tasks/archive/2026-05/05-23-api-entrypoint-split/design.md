# Slim API Entrypoint Design

## Target Shape

`api.py` remains the canonical FastAPI app module but stops owning every API-only
contract and helper. The first split favors compatibility over maximal
extraction:

- keep `app`, middleware, exception handlers, and route decorators in `api.py`
- keep global mutable runtime state in `api.py`
- move Pydantic request model classes to `api_models.py`
- move QA routing/formatting helpers to `api_qa.py`
- move manual-library form parsing, rebuild helper, and diagnostics helpers to
  `api_manual.py`

## Compatibility Boundary

Existing callers may import request models from `tagmemorag.api`, so `api.py`
will import and re-export the moved model classes. Tests and integrations that
mutate `api.settings`, `api.embedder`, or `api.app_state` continue to work.

## Dependency Direction

The new modules are still API-layer modules. They may import FastAPI/Pydantic
types only where they own request parsing helpers, but lower service modules
must not import `api.py`.

`api_manual.py` accepts explicit dependencies for mutable state operations:

- settings/config object
- app state
- embedder
- optional rebuild queue

That keeps the helper module independent from `api.py` globals.

## Risk Controls

- Move code mechanically and preserve function signatures where practical.
- Re-export models from `api.py` before route definitions use them.
- Run API-focused tests after extraction.
- Stop after safe helper/model extraction if router splitting would require
  broad dependency injection or behavioral risk.
