# Validation Notes

## Change

Release readiness now treats `general_web_ranking_pressure` as an optional
report input.

When present and non-empty, it adds bounded detail to the
`general_web_retrieval` stage:

- `ranking_pressure_count`
- `highest_pressure_rank_count`

It also adds a passed-status next-step hint. This is intentionally non-blocking:
the overall release readiness status remains `passed` when all required gates
are green.

Missing, unreadable, or malformed optional ranking-pressure reports are ignored.

## Commands

```text
.venv/bin/pytest tests/unit/test_release_readiness.py -q
```

Result:

- `7 passed`

```text
.venv/bin/python scripts/release_readiness.py \
  --report general_web_ranking_pressure=.tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/release-readiness-with-ranking-pressure.json
```

Observed retained report:

- status: `passed`
- `general_web_retrieval.ranking_pressure_count=2`
- `general_web_retrieval.highest_pressure_rank_count=5`
- next steps include:
  `Track non-blocking general-web ranking pressure before the next retrieval-quality batch`

## Privacy

Unit coverage verifies the readiness output does not include ranking-pressure
case ids or `top_results`. Only bounded counts are surfaced.
