# RAG Capability Review and Optimization — Execution Plan

## 0. Operating Rules

- Keep parent changes limited to audit and planning artifacts; production code
  changes must happen only in scoped child tasks.
- Ask user only for product/scope decisions that cannot be answered from the
  repo.
- Use code, tests, docs, and archived tasks as evidence before recommending a
  child.
- Prefer concrete eval gates over vague quality claims.

## 1. Planning Steps

### Step 1 — Evidence Inventory

- Map current RAG modules and docs.
- Record eval fixtures and existing baselines.
- Identify project-specific invariants that should not be outsourced blindly.

Output:

- `research/capability-audit.md`

### Step 2 — Library Reuse Matrix

- Compare custom areas with LangChain, LlamaIndex, and at least one eval or
  RAG diagnostics library/tooling option.
- Decide keep/wrap/replace/defer per area.

Output:

- `research/library-reuse-matrix.md`

### Step 3 — Roadmap and Child Tasks

- Split recommendations into child tasks.
- For each child, write scope, dependencies, validation gates, and rollback.
- Create child Trellis tasks in planning status.

Output:

- `research/child-roadmap.md`
- child task directories

### Step 4 — Parent Review Gate

- Confirm with the user before starting any child implementation.
- Parent may be archived once the audit, matrix, roadmap, and approved child
  tasks are complete.

## 2. Validation Commands

```bash
rg -n "TBD|_example|TODO" .trellis/tasks/05-21-rag-capability-review-and-optimization || true
python3 - <<'PY'
import json
from pathlib import Path
for path in [
    Path('.trellis/tasks/05-21-rag-capability-review-and-optimization/implement.jsonl'),
    Path('.trellis/tasks/05-21-rag-capability-review-and-optimization/check.jsonl'),
]:
    for line in path.read_text().splitlines():
        if line.strip():
            json.loads(line)
PY
git diff --check
git diff --name-only -- src tests
```

Expected final command output: empty.

## 3. Exit Criteria

- [x] Capability audit written.
- [x] Library reuse matrix written.
- [x] Child roadmap written.
- [x] Child task directories created in planning status.
- [x] User reviewed and approved the roadmap.
- [x] Approved child tasks C1-C6 completed and archived.
- [x] Parent production-code changes were avoided; implementation happened in
      child tasks with their own validation gates.

## 4. Validation Results

- `rg -n "TBD|_example|TODO" .trellis/tasks/05-21-rag-capability-review-and-optimization || true`
  only reports the literal validation command in this file.
- JSONL manifests parse successfully.
- `git diff --check` passed.
- Production code remained untouched for the parent audit commit.
- User approved continuing with child tasks in roadmap order. Child tasks C1-C6
  are completed and archived, with full-suite validation run on the final
  child.
