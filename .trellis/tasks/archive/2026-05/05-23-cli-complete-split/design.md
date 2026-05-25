# CLI Complete Split Design

## Target Shape

`src/tagmemorag/cli.py` becomes a stable entry-point wrapper:

- construct the parser via `cli_parser.build_parser()`
- parse argv
- dispatch the parsed namespace via `cli_dispatch.run_command(args)`
- keep `main(argv)` and `if __name__ == "__main__"` unchanged

## New/Updated Modules

- `cli_parser.py`: owns argparse parser construction and command flag
  registration. It may import CLI-only helper functions and default constants.
- `cli_dispatch.py`: owns the top-level `args.command` dispatch table and routes
  to command modules.
- `cli_basic.py`: build/search/serve/config/langchain/retrain-residuals/auth and
  small operational commands.
- `cli_eval.py`: eval run, answer-quality, pilot, readiness, and epa execution.
- `cli_manual.py`: manual-bulk, manual-library, tag, and qdrant execution.
- Existing modules stay in place:
  - `cli_feedback.py`
  - `cli_provider.py`
  - `cli_source_import.py`
  - `cli_helpers.py`

## Compatibility

- `tagmemorag.cli.main(argv)` remains the public test and package entry point.
- `python -m tagmemorag` still forwards to `cli.main`.
- Parser semantics remain identical because the parser code is moved, not
  redesigned.
- Tests that patch command internals should patch the new owner module.

## Risk Controls

- Use focused modules but avoid changing lower-level service APIs.
- Prefer compatibility wrapper functions only when tests or existing imports
  depend on them.
- Run full CLI tests after implementation.
