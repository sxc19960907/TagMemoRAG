# Research: Source Data Model (VCPToolBox TagMemoEngine)

**Goal**: Document the exact SQLite schema and data conventions in VCPToolBox so that TagMemoRAG Phase 0 can mirror them accurately, with documented deviations.

## Source schema verbatim

From `KnowledgeBaseManager.js:185-249` (`_initSchema`):

```sql
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    diary_name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    mtime INTEGER NOT NULL,
    size INTEGER NOT NULL,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    vector BLOB,
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    vector BLOB
);

CREATE TABLE IF NOT EXISTS file_tags (
    file_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (file_id, tag_id),
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tag_intrinsic_residuals (
    tag_id INTEGER PRIMARY KEY,
    residual_energy REAL NOT NULL,
    neighbor_count INTEGER NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_files_diary ON files(diary_name);
CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id);
CREATE INDEX IF NOT EXISTS idx_file_tags_tag ON file_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_file_tags_composite ON file_tags(tag_id, file_id);
```

**Note on migration**: Source has a runtime `ALTER TABLE file_tags ADD COLUMN position` patch (KnowledgeBaseManager.js:243-247) for legacy DBs without the column.

## Field-by-field mapping to TagMemoRAG schema

| Source (VCPToolBox) | TagMemoRAG (Phase 0 proposed) | Notes |
|---|---|---|
| `files` table | (none — uses `manual_records` already) | `manual_records.manual_id` plays `files.id` role; we already have it |
| `chunks` table | (none — graph node IDs from networkx) | TagMemoRAG keeps chunks in graph + npz vectors, not SQLite |
| `tags(id, name, vector)` | `tags(id, kb_name, name, vector, embedding_dim, embedded_at)` | Add `kb_name` discriminator; add `embedding_dim` for safety; track `embedded_at` for staleness |
| `file_tags(file_id, tag_id, position)` | `chunk_tags(chunk_id TEXT, tag_id, position)` | We map at chunk granularity (manual.metadata.tags inherited by all chunks of that manual) — see deviation below |
| `tag_intrinsic_residuals(tag_id, residual_energy, neighbor_count, computed_at)` | Same — adopt verbatim | Source has `neighbor_count` field we missed in PRD; add it for V7 fidelity |

## Position encoding rules

From `buildDirectedCooccurrenceMatrix` (TagMemoEngine.js:643-735):

**Source's processFileGroup logic (line 672-693)**:
```js
processFileGroup = (tags, fid) => {
    const n = tags.length;
    if (n < 2 || n > 100) return;  // skip isolated or super-dirty files
    for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
            const t1 = tags[i], t2 = tags[j];
            // 序位势能 (positional potential)
            const phi1 = n > 1 ? PHI_MAX - (PHI_MAX - PHI_MIN) * (t1.pos - 1) / (n - 1) : PHI_MAX;
            const phi2 = n > 1 ? PHI_MAX - (PHI_MAX - PHI_MIN) * (t2.pos - 1) / (n - 1) : PHI_MAX;
            const weight = phi1 * phi2;
            // ... add directed edge t1.id → t2.id with `weight`
        }
    }
};
```

**Constants**:
- `PHI_MAX = 0.9`, `PHI_MIN = 0.5` (TagMemoEngine.js:647-648)
- `LEGACY_PHI = 0.7` (TagMemoEngine.js:715) — used for `position = 0` fallback path
- Iteration: `WHERE position > 0 ORDER BY file_id, position ASC` (line 661-665)

**Position is 1-indexed**. The formula `(t1.pos - 1) / (n - 1)` confirms: pos=1 maps to phi=PHI_MAX (0.9), pos=n maps to phi=PHI_MIN (0.5).

**Legacy fallback** (line 706-720): rows with `position = 0` are joined separately with constant `LEGACY_PHI=0.7`, building **undirected** equal-weight edges (vs directed by position).

## Vector BLOB format

From `applyTagBoost` (TagMemoEngine.js:380-410, used in deduplication and final fusion):

```js
const vec = new Float32Array(data.vector.buffer, data.vector.byteOffset, dim);
```

And from `_clusterTags` (EPAModule.js:208-215):
```js
const vectors = tags.map(t => {
    const buf = t.vector;
    const aligned = new Float32Array(dim);
    new Uint8Array(aligned.buffer).set(buf);  // copy to aligned buffer
    return aligned;
});
```

**Format conclusions**:
- Storage: raw `Float32Array` bytes as SQLite BLOB (no header, no length prefix)
- Byte order: native little-endian (x86/ARM machines)
- Dimension is **not** stored per-row — relies on global `config.dimension` matching at read time
- Reads handle alignment by copying to a fresh `Float32Array` buffer

**Recommendation for TagMemoRAG**: store as little-endian Float32 BLOB to be byte-compatible with source dumps. Add `embedding_dim INTEGER NOT NULL` to tags table to validate at read time (defends against model swap).

In Python: `np.array(vec, dtype=np.float32).tobytes()` for write, `np.frombuffer(blob, dtype=np.float32)` for read.

## Residual energy computation pipeline

`tag_intrinsic_residuals` is loaded by `loadIntrinsicResiduals` (TagMemoEngine.js:738-755):

```js
const rows = this.db.prepare(
    'SELECT tag_id, residual_energy FROM tag_intrinsic_residuals'
).all();
this.tagIntrinsicResiduals = new Map();
for (const row of rows) {
    const clamped = Math.max(0.5, Math.min(2.0, row.residual_energy));
    this.tagIntrinsicResiduals.set(row.tag_id, clamped);
}
```

**Producer not found in TagMemoEngine.js**. The schema includes `neighbor_count` and `computed_at` — implying an offline computation pipeline writes this table.

Search `KnowledgeBaseManager.js`, `Plugin/LightMemo/LightMemo.js`, and any `build_*` / `compute_*` scripts in VCPToolBox. From the schema and the `ResidualPyramid` algorithm (ResidualPyramid.js:25-122), the **inferred computation** is:

For each tag T in `tags`:
1. Compute `T.vector`'s ResidualPyramid against all OTHER tags (project T onto basis spanned by neighbors)
2. `residual_energy(T) = ||residual||² / ||T.vector||²` (fraction of T not explained by neighbors)
3. `neighbor_count(T)` = number of tags used as basis
4. Insert/update `tag_intrinsic_residuals` row

**For Phase 0**: write the table schema, default `residual_energy=1.0`, `neighbor_count=0`. Producer pipeline is Phase 3's responsibility.

## Tag mutation patterns (rename / merge / delete)

Searching VCPToolBox for tag mutation methods finds **none in `KnowledgeBaseManager` directly**. Tags are managed implicitly:

- **Insertion**: `_flushBatch` (KnowledgeBaseManager.js:1003+) inserts tags during file ingestion
- **Deletion**: relies on FK `ON DELETE CASCADE`. When a `chunks` row is deleted, `file_tags` rows go with it. When a `files` row is deleted, both cascade.
- **Orphan cleanup**: `_cleanupDatabaseOrphans` (KnowledgeBaseManager.js:257-308) removes tags that have no `file_tags` references.

**No rename/merge in source**. Tag taxonomy is implicit, derived from file ingestion. **TagMemoRAG has stronger requirements** because of `tag_governance` (synonym/canonical/rewrite) — we need application-level UPDATE/DELETE on tags + chunk_tags.

## Recommendations for TagMemoRAG M1 schema

### Adopt from source verbatim
1. **`position` 1-indexed**, default 0 for legacy/unsorted
2. **`tag_intrinsic_residuals` schema**: include `neighbor_count` and `computed_at` (PRD missed these — update PRD M1)
3. **Vector BLOB as Float32 little-endian** (no header)
4. **PHI constants**: PHI_MAX=0.9, PHI_MIN=0.5, LEGACY_PHI=0.7 — bake into Phase 1 (out of scope for Phase 0 but good to document)

### Deviate from source intentionally

1. **Tag scope = (kb_name, name) instead of global `name UNIQUE`**
   - Source has one DB per diary, so global UNIQUE is fine
   - We have one shared DB across KBs; same tag name in different KBs should be **separate tags** (different domains, e.g. "noise" in fridge vs in air-conditioner KB has different semantics)
   - Schema: `UNIQUE(kb_name, name)`, drop global `UNIQUE` on `name`
   - **Implication for EPA basis**: even though tags are KB-scoped, we still train ONE global basis using all tags' vectors merged

2. **Mapping at chunk granularity, not file**
   - Source's `file_tags` maps tags to a file (whole document)
   - Our `chunk_tags` maps to chunks
   - Source's `processFileGroup` works on tags-of-a-file; for us it's tags-of-a-manual (manual ↔ file equivalence)
   - **Implementation**: each chunk inherits the manual's `metadata.tags`; chunk_tags rows are duplicated per chunk (chunk_count × tag_count rows)
   - **Alternative**: keep `manual_tags(manual_id, tag_id, position)` instead. **Recommended**: use `manual_tags` to reduce row count and match source semantics; chunks reach tags via `chunk.metadata.manual_id → manual_tags`. **Schema name change**: `chunk_tags` → `manual_tags`.

3. **Add `embedding_dim` and `embedded_at` to tags**
   - Source assumes global dimension constant; we have multiple embedder backends (HashingEmbedder, HttpEmbedder, local)
   - `embedding_dim` per row guards against model swap (fail-fast if mismatch)
   - `embedded_at` enables incremental re-embedding when embedder changes

4. **No global `tags.name UNIQUE`** — replace with `UNIQUE(kb_name, name)`

5. **No legacy `position=0` path needed for new data**
   - Phase 0 always writes 1-indexed position from `metadata.tags` array order
   - But keep the source's `LEGACY_PHI` fallback in Phase 1 cooccurrence builder — defends against any imported data with position=0

### Final M1 schema (revised)

```sql
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_name TEXT NOT NULL,
    name TEXT NOT NULL,
    vector BLOB,
    embedding_dim INTEGER,
    embedded_at TEXT,
    UNIQUE(kb_name, name)
);

CREATE TABLE IF NOT EXISTS manual_tags (
    kb_name TEXT NOT NULL,
    manual_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kb_name, manual_id, tag_id),
    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tag_intrinsic_residuals (
    tag_id INTEGER PRIMARY KEY,
    residual_energy REAL NOT NULL DEFAULT 1.0,
    neighbor_count INTEGER NOT NULL DEFAULT 0,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tags_kb ON tags(kb_name);
CREATE INDEX IF NOT EXISTS idx_manual_tags_tag ON manual_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_manual_tags_kb_manual ON manual_tags(kb_name, manual_id);
```

**FK note**: `manual_tags` does not FK to `manual_records(kb_name, manual_id)` because that table has compound PK and SQLite FK on compound keys requires explicit handling. We rely on application-level cleanup in DELETE /manuals path (see PRD M5).

## References

- VCPToolBox/KnowledgeBaseManager.js:185 — `_initSchema`
- VCPToolBox/TagMemoEngine.js:643 — `buildDirectedCooccurrenceMatrix`
- VCPToolBox/TagMemoEngine.js:738 — `loadIntrinsicResiduals`
- VCPToolBox/TagMemoEngine.js:380 — vector BLOB read pattern
- VCPToolBox/EPAModule.js:208 — `_clusterTags` vector handling
- TagMemoRAG/src/tagmemorag/manual_registry.py:271 — current `SQLiteManualRegistry._init_schema`
