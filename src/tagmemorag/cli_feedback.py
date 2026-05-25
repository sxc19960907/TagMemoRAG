from __future__ import annotations

import json

from .cli_helpers import read_text_file
from .config import load_config
from .logging_setup import configure_logging
from .retrieval_feedback import (
    create_feedback,
    export_eval_promotion,
    list_feedback,
    preview_eval_promotion,
    review_feedback,
)


def run_feedback_command(args) -> int:
    cfg = load_config(args.config)
    configure_logging(cfg.logging.level, cfg.logging.format)

    if args.feedback_command == "submit":
        payload = json.loads(read_text_file(args.json))
        feedback = create_feedback(args.kb, payload, cfg)
        print(json.dumps({"feedback": feedback.to_dict()}, ensure_ascii=False, indent=2))
        return 0
    if args.feedback_command == "list":
        rows = list_feedback(args.kb, cfg, status=args.status, outcome=args.outcome, query=args.query, limit=args.limit)
        print(json.dumps({"kb_name": args.kb, "feedback": [row.to_dict() for row in rows]}, ensure_ascii=False, indent=2))
        return 0
    if args.feedback_command == "review":
        feedback = review_feedback(
            args.kb,
            args.feedback_id,
            cfg,
            status=args.status,
            operator_note=args.operator_note,
        )
        print(json.dumps({"feedback": feedback.to_dict()}, ensure_ascii=False, indent=2))
        return 0
    if args.feedback_command == "promote-preview":
        preview = preview_eval_promotion(args.kb, args.feedback_id, cfg, output_path=args.output)
        print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.feedback_command == "promote":
        preview = export_eval_promotion(
            args.kb,
            args.feedback_id,
            cfg,
            output_path=args.output,
            append=args.append,
            overwrite=args.overwrite,
        )
        print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2))
        return 0
    return 1
