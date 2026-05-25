from __future__ import annotations

from .cli_basic import run_basic_command
from .cli_eval import run_eval_command
from .cli_feedback import run_feedback_command
from .cli_manual import run_manual_command
from .cli_provider import run_production_provider_command, run_provider_command
from .cli_source_import import run_knowledge_command, run_manualslib_command

_BASIC_COMMANDS = {"auth", "build", "config", "demo", "langchain", "retrain-residuals", "search", "serve"}
_EVAL_COMMANDS = {"epa", "eval", "pilot", "readiness"}
_MANUAL_COMMANDS = {"manual-bulk", "manual-library", "qdrant", "tag"}


def run_command(args) -> int:
    if args.command in _BASIC_COMMANDS:
        return run_basic_command(args)
    if args.command in _EVAL_COMMANDS:
        return run_eval_command(args)
    if args.command in _MANUAL_COMMANDS:
        return run_manual_command(args)
    if args.command == "manualslib":
        return run_manualslib_command(args)
    if args.command == "knowledge":
        return run_knowledge_command(args)
    if args.command == "provider":
        return run_provider_command(args)
    if args.command == "production-provider":
        return run_production_provider_command(args)
    if args.command == "feedback":
        return run_feedback_command(args)
    return 1
