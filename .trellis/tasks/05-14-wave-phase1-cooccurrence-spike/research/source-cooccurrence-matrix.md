# Source: Directed Co-occurrence Matrix (V7)

> Verbatim study of `TagMemoEngine.buildDirectedCooccurrenceMatrix` so the
> Python port does not paraphrase formulas.

## File / lines
- `VCPToolBox/TagMemoEngine.js:643-735` — main builder
- `VCPToolBox/TagMemoEngine.js:758-793` — `scheduleMatrixRebuild` (debounce)
- `VCPToolBox/TagMemoEngine.js:795-820` — `doMatrixRebuild` (single-flight wrapper)
- `VCPToolBox/TagMemoEngine.js:822-833` — `_scheduleMatrixRebuildTimer`

## Inputs (read from SQLite)

```sql
-- Step 2 query (normal path)
SELECT file_id, tag_id, position
FROM file_tags
WHERE position > 0
ORDER BY file_id, position ASC

-- Step 3 query (legacy / position=0 fallback)
SELECT ft1.tag_id AS tag1, ft2.tag_id AS tag2, COUNT(ft1.file_id) AS cnt
FROM file_tags ft1
JOIN file_tags ft2
    ON ft1.file_id = ft2.file_id
   AND ft1.tag_id < ft2.tag_id
WHERE ft1.position = 0 OR ft2.position = 0
GROUP BY ft1.tag_id, ft2.tag_id
```

`file_tags` is the direct analogue of TagMemoRAG's Phase 0 `manual_tags(kb_name, manual_id, tag_id, position)`. The source has no `kb_name` column because there is one knowledge base per process; the Python port must filter by `kb_name` everywhere or maintain a per-KB matrix.

## Constants

```js
const PHI_MAX = 0.9;         // line 647
const PHI_MIN = 0.5;         // line 648
const LEGACY_PHI = 0.7;      // line 716 (used only in fallback path)
```

The Phase 0 PRD wrote the formula as `0.9 - 0.4 * (pos-1)/(n-1)`. Source code uses `(PHI_MAX - PHI_MIN)` which is `0.9 - 0.5 = 0.4`. **Same formula** — the constants stay PHI_MAX, PHI_MIN to keep the door open if a future tweak changes them. Python port should copy this naming.

## phi(pos, n) formula (lines 681-682)

```js
const phi1 = n > 1 ? PHI_MAX - (PHI_MAX - PHI_MIN) * (t1.pos - 1) / (n - 1) : PHI_MAX;
const phi2 = n > 1 ? PHI_MAX - (PHI_MAX - PHI_MIN) * (t2.pos - 1) / (n - 1) : PHI_MAX;
```

Per file with `n` tags ordered by position, position-1 (i.e. the first tag in the array) gets `phi = PHI_MAX = 0.9`, position-n gets `phi = PHI_MIN = 0.5`, linearly interpolated in between.

## Edge weight (line 683)

```js
const weight = phi1 * phi2;
```

So the contribution of one (file, tag-pair) is **phi1 × phi2**, not just phi1 alone. A pair of two leading tags gets `0.9 × 0.9 ≈ 0.81`; a leading + trailing pair gets `0.9 × 0.5 = 0.45`; trailing pair gets `0.5 × 0.5 = 0.25`. Per-file pair contributions accumulate **across files**.

## Direction convention (lines 685-688)

```js
for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
        const t1 = tags[i];   // earlier-position tag = source
        const t2 = tags[j];   // later-position tag  = target
        ...
        if (!matrix.has(t1.id)) matrix.set(t1.id, new Map());
        const targetMap = matrix.get(t1.id);
        targetMap.set(t2.id, (targetMap.get(t2.id) || 0) + weight);
    }
}
```

**Source = earlier position. Target = later position.** Only the source→target edge is written — the reverse direction is not. The matrix is asymmetric:
`matrix[A][B]` and `matrix[B][A]` differ unless A and B never share file order.

## Container shape

`Map<source_tag_id, Map<target_tag_id, weight>>` — a sparse adjacency list where each row is a `Map`. **No CSR / dense matrix.** Memory is `O(E)` where E is the number of unique directed pairs that ever co-occur, not `O(N²)`.

For TagMemoRAG fixture scale (12 canonical tags total across 4 KBs, ~3 tags/manual), E ≤ ~30. Practical shape choice for Python port:
- `dict[int, dict[int, float]]` is the most direct port and fine up to ~10⁵ tags.
- `scipy.sparse.csr_matrix` becomes worth it only beyond ~10⁵ tags or when matrix-vector products dominate. Spike propagation does many small lookups, so the dict-of-dicts may actually be faster.

## Performance guards (lines 673-676)

```js
const n = tags.length;
if (n < 2 || n > 100) return; // 🛡️ 性能保护：跳过孤立点或超大脏文件
```

- `n < 2` — single-tag manuals contribute zero pairs (mathematically vacuous, but guarded anyway).
- `n > 100` — caps the per-file pair-emission cost at `100*99/2 = 4950` pair updates. The source treats `>100` tags on one file as "dirty data" rather than legitimate.

The Python port should keep both guards. n>100 is unlikely on TagMemoRAG manuals (usually ≤10 tags) but the guard is cheap insurance.

## Legacy fallback (lines 707-728)

```js
WHERE ft1.position = 0 OR ft2.position = 0
...
const weight = row.cnt * LEGACY_PHI * LEGACY_PHI;  // 0.7 * 0.7 = 0.49
// Both directions written:
matrix.get(row.tag1).set(row.tag2, e1 + weight);
matrix.get(row.tag2).set(row.tag1, e2 + weight);
```

When position is missing (= 0), the source falls back to:
1. Compute symmetric counts (joining the same file twice with `tag1 < tag2`).
2. Multiply count by `LEGACY_PHI² = 0.49`.
3. Write **both** directions — the matrix becomes undirected for legacy data.

TagMemoRAG Phase 0 always writes a real position (1-indexed array order), so the legacy branch is **dead code on a fresh build**. But:
- Bulk-imported old manuals may have `position=0` in their sidecars.
- Python port should still implement the fallback so an upgrade from a Phase-0-pre-write database doesn't lose edges.

## Lifecycle

```
buildDirectedCooccurrenceMatrix() → in-memory only (this.tagCooccurrenceMatrix)
                                  → never persisted to disk
```

The matrix is held on the engine instance; rebuild is the only way to refresh. On process restart, the matrix is rebuilt eagerly during init (not in the snippets above; see `init()` in TagMemoEngine.js). The Python port has the same constraint OR can choose to persist to a npz/parquet for faster cold start — TagMemoRAG already prefers atomic-file persistence for global assets like `epa_basis.npz`.

## Rebuild trigger (lines 758-793)

```js
scheduleMatrixRebuild(changeCount = 1) {
    this._accumulatedTagChanges += changeCount;

    let threshold = 50;
    const totalTags = this.db.prepare('SELECT COUNT(*) as count FROM tags').get()?.count || 0;
    threshold = Math.max(10, Math.min(200, Math.floor(totalTags * 0.01)));

    if (this._accumulatedTagChanges >= threshold) {
        if (this._matrixRebuildTimer) clearTimeout(this._matrixRebuildTimer);
        const COOLING_DELAY = 300000;  // 5 minutes
        this._matrixRebuildTimer = setTimeout(() => this.doMatrixRebuild(), COOLING_DELAY);
    }
}
```

Two-stage debounce:
1. **Threshold gate**: don't even start the cooldown timer until accumulated tag changes ≥ `max(10, min(200, totalTags*0.01))`.
2. **Sliding-window cooldown**: once gated through, restart a 5-minute timer on every additional change. Rebuild fires when the timer survives 5 quiet minutes.

`doMatrixRebuild` is single-flight via `_isMatrixRebuilding`. Late changes during rebuild get a follow-up timer (lines 798-806).

For TagMemoRAG, this maps cleanly to a per-rebuild-task hook: `incremental_rebuild` already finishes by calling `tag_rebuild.sync_rebuild_tags`, which is the natural place to schedule a co-occurrence rebuild. Phase 1 should:
- Trigger an in-process rebuild at the end of every `incremental_rebuild` task (no debounce — TagMemoRAG rebuilds are already user-initiated and rate-limited by the rebuild queue).
- Skip per-mutation debouncing for now — the source's debounce is for a chat app where tags change continuously; TagMemoRAG only mutates tags during rebuild.

## Output (line 727)

```js
this.tagCooccurrenceMatrix = matrix;
```

Single writable instance field, no version/timestamp. The Python port should add at least a `built_at` timestamp and a `kb_name → matrix` map (the source has no kb dimension at all).

## Failure mode (lines 729-734)

```js
} catch (e) {
    console.error('[TagMemoEngine] ❌ Failed to build directed matrix:', e);
    this.tagCooccurrenceMatrix = new Map();
}
```

Empty matrix on failure. `applyTagBoost` then short-circuits (it checks `this.tagCooccurrenceMatrix` truthiness, but an empty Map is truthy — see source-tag-boost-and-spike.md for what happens then). Python port must mirror "fail open, leave matrix empty" — never let a corrupt matrix persist.
