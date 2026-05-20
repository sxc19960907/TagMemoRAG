# Architecture v2 — Implementation Checklist

## What "implementation" means here

This task does not write code. "Implementation" = drafting `.trellis/spec/backend/architecture.md` and updating `.trellis/spec/backend/index.md`, validated against the design.md spec.

## Pre-flight

- [ ] Confirm git tree is clean on `feat/wave-phase1-cooccurrence-spike`.
- [ ] Confirm active task: `python3 ./.trellis/scripts/task.py current --source` returns this task.
- [ ] Re-read design.md section "Document Structure (target)".
- [ ] Re-read PRD decisions D1–D6 once more before drafting.

## Drafting Order

The doc is large; draft top-down with one commit per logical block to keep diffs reviewable.

- [ ] **Block 1 — Frame**: Document Status, Reading Guide, Executive Position, System Overview.
  - Validation: status markers legend present; no "production-grade" self-label; three named gaps (QueryPlan / Reranker / IndexGeneration).
- [ ] **Block 2 — Domain Model + ID system**: Domain Model section + A1.
  - Validation: chunk_id vs vector_point_id formulas present; reranker_id explicitly excluded from persistent ids.
- [ ] **Block 3 — A2 QueryPlan + Budget**: schemas + early-exit protocol + persistence pointer to D6.
  - Validation: dataclass schemas literal in design.md appear; query raw text NOT stored statement present.
- [ ] **Block 4 — A3 Reranker**: Protocol + cache key + tier table + calibration + ACL gate + truncation rule.
  - Validation: no vendor-specific identifiers in this section; tier table uses abstract names only.
- [ ] **Block 5 — A4 IndexGeneration**: state machine + storage layout + admin API + trigger fields + rollback.
  - Validation: state machine ASCII present; collection name `{prefix}_{kb}_g{N}` present; "no traffic split" noted.
- [ ] **Block 6 — A5 WAVE**: experimental status + KEEP_OFF link + promotion criteria.
  - Validation: section lives outside "Strengths"; memory `wave-readiness-flags-empirical-keep-off` linked.
- [ ] **Block 7 — B6/B7/B8 blueprints**: each section follows the D2 template; minimum question counts met.
  - Validation: B6 ≥6 questions, B7A ≥4, B7B ≥4, B8 ≥5; "Out of Scope for this blueprint" present in each.
- [ ] **Block 8 — C9/C10 cross-cutting**: eval-as-driver mechanism (not slogan); honesty rules.
  - Validation: replay tool contract paragraph present; honesty rules are imperatives.
- [ ] **Block 9 — Storage Backends + Roadmap + Appendices**: storage table; roadmap T1–T9; Appendix A vendor block; Appendix B changelog.
  - Validation: roadmap rows T1–T9 with Depends-on + Priority; Appendix A dated header; Appendix B table with at least 8 rows.
- [ ] **Block 10 — index.md update**: living doc link at top; archive demoted to "Historical references".

## Validation Commands

```bash
# 1. Files exist
test -f .trellis/spec/backend/architecture.md
test -f .trellis/spec/backend/index.md

# 2. No "production-grade" self-label in living doc
! grep -nE '\bproduction-grade\b' .trellis/spec/backend/architecture.md

# 3. Vendor specifics only in Appendix A
# Extract Appendix A boundaries first, then ensure 'Qwen3-Reranker' / 'siliconflow' appear only inside.
python3 -c "
import re, pathlib, sys
text = pathlib.Path('.trellis/spec/backend/architecture.md').read_text()
m = re.search(r'## Appendix A.*?(?=^## |\Z)', text, flags=re.DOTALL|re.MULTILINE)
appendix = m.group(0) if m else ''
body = text.replace(appendix, '')
violations = [t for t in ('Qwen3-Reranker', 'siliconflow', '¥0.07') if t in body]
sys.exit(0 if not violations else (print(violations) or 1))
"

# 4. WAVE memory link present
grep -F 'wave-readiness-flags-empirical-keep-off' .trellis/spec/backend/architecture.md

# 5. Roadmap rows
for id in T1 T2 T3 T4 T5 T6 T7 T8 T9; do
  grep -F "| $id |" .trellis/spec/backend/architecture.md >/dev/null || { echo "missing $id"; exit 1; }
done

# 6. index.md points at living doc
grep -F 'architecture.md' .trellis/spec/backend/index.md

# 7. Status markers legend
grep -E '✅|🚧|📋' .trellis/spec/backend/architecture.md | head

# 8. Markdown trailing-whitespace / merge-marker hygiene
git diff --check .trellis/spec/backend/architecture.md .trellis/spec/backend/index.md
```

All must pass before reporting completion.

## Review Gates

- [ ] **Self-review**: walk every "required substance" bullet from design.md against the draft.
- [ ] **User review**: present the new architecture.md and index.md for approval before commit.
- [ ] **Acceptance Criteria sweep**: tick every box in PRD § Acceptance Criteria.

## Commit Strategy

One commit per draft block (10 commits feasible) OR one squashed commit at the end. Decide at draft time based on diff size; default = squashed single commit because the doc is internally cross-referenced and partial commits read badly.

Commit message shape:

```
docs(spec): add backend/architecture.md v2 living doc

- Replaces archive production-rag-architecture/design.md as source of truth
- Encodes brainstorm decisions D1–D6
- Adds follow-up execution roadmap (T1–T9, not pre-created as tasks)
```

## Rollback

`git checkout HEAD -- .trellis/spec/backend/architecture.md .trellis/spec/backend/index.md` if the draft needs to be discarded.
