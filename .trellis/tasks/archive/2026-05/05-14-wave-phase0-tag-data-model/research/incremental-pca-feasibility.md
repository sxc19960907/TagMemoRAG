# Research: Incremental PCA Feasibility & Concurrency

**Goal**: Settle the open implementation questions for the EPA basis training & storage layer:
1. IncrementalPCA vs full retrain
2. Save/load layout for `epa_basis.npz`
3. Cold-start fallback (precise behavior)
4. File locking & atomic write
5. Concurrency / race scenarios

This document complements `epa-basis-training.md` (which decided the algorithm) by nailing down the engineering details.

## IncrementalPCA vs full PCA at our scale

### TagMemoRAG scale ceiling

- Embedding dim: **384** (BAAI/bge-small-zh-v1.5)
- Tag count growth profile:
  - Fixture: ~10
  - Pilot deployment: 100-300
  - Production worst case: ~10,000 (1000 manuals × 10 tags each, with high overlap → maybe 2000-3000 unique)
- K-Means clusters before PCA: ≤ 32 (per `epa-basis-training.md` recommendation)

### Memory and compute

- **Worst-case raw matrix**: 10,000 tags × 384 dim × 4 bytes = **15 MB** → trivially RAM-resident
- **K-Means `n_clusters=32`** on 10K samples × 384 dim: ~50 ms with sklearn
- **PCA on 32 × 384 centroid matrix**: ~5 ms with sklearn
- **Total training time**: << 1 second even at production worst case

### IncrementalPCA characteristics

`sklearn.decomposition.IncrementalPCA`:
- **Designed for**: data that doesn't fit in RAM (out-of-core training)
- **API**: `partial_fit(batch)` called repeatedly; state preserved between calls
- **Numerical behavior**: differs from batch PCA by O(batch_size) — components converge to same subspace but ordering of low-variance components is unstable
- **Save/load**: pickle/joblib the entire estimator object (not portable across sklearn versions)

**Recommendation: skip IncrementalPCA, use full retrain.**

Reasons:
1. Our data fits in RAM by 3 orders of magnitude
2. Full retrain is < 1 second
3. IncrementalPCA serialization is sklearn-version-fragile (joblib pickle); npz is forever
4. IncrementalPCA's batch ordering complicates concurrency reasoning
5. Numerical reproducibility is better with batch PCA + fixed seed

### When to retrain (full)

Trigger conditions (any one):
1. **Manual**: `tagmemorag epa rebuild --force` CLI invocation
2. **Significant tag growth**: `|current_tag_count - tag_count_at_train| / tag_count_at_train > 0.20`
3. **Tag taxonomy mutation**: any successful `commit_tag_rewrite` (rename/merge/delete)
4. **Service startup**: if `epa_basis.npz` is absent

Each Phase 0 rebuild evaluates conditions 2 and 3 at the end of `incremental_rebuild`.

## Save/load layout for `epa_basis.npz`

### File structure

`data/_global/epa_basis.npz` is a numpy `.npz` (zip of `.npy` files):

| Field | Dtype | Shape | Description |
|---|---|---|---|
| `orthoBasis` | float32 | (K, D) | K orthonormal basis vectors, each D-dim |
| `basisMean` | float32 | (D,) | Weighted mean of training centroids |
| `basisEnergies` | float32 | (K,) | Eigenvalues / explained variance for each axis |
| `basisLabels` | object array | (K,) | Tag name (str) closest to each basis axis |
| `meta_K` | int32 | () | Effective basis dimension (== K) |
| `meta_dim` | int32 | () | D (embedding dimension, sanity check) |
| `meta_train_kind` | object | () | "cold-start" or "real-pca" |
| `meta_tag_count_at_train` | int32 | () | Tag count at training time (for trigger condition 2) |
| `meta_trained_at` | object | () | ISO 8601 UTC timestamp string |
| `meta_schema_version` | int32 | () | npz layout version (start at 1) |

### Save function

```python
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
import os

def save_epa_basis(
    path: Path,
    orthoBasis: np.ndarray,
    basisMean: np.ndarray,
    basisEnergies: np.ndarray,
    basisLabels: list[str],
    K: int,
    dim: int,
    train_kind: str,        # "cold-start" | "real-pca"
    tag_count_at_train: int,
) -> None:
    assert orthoBasis.shape == (K, dim)
    assert basisMean.shape == (dim,)
    assert basisEnergies.shape == (K,)
    assert len(basisLabels) == K
    assert train_kind in ("cold-start", "real-pca")

    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)

    np.savez(
        tmp,
        orthoBasis=orthoBasis.astype(np.float32),
        basisMean=basisMean.astype(np.float32),
        basisEnergies=basisEnergies.astype(np.float32),
        basisLabels=np.array(basisLabels, dtype=object),
        meta_K=np.int32(K),
        meta_dim=np.int32(dim),
        meta_train_kind=np.array(train_kind, dtype=object),
        meta_tag_count_at_train=np.int32(tag_count_at_train),
        meta_trained_at=np.array(
            datetime.now(timezone.utc).isoformat(), dtype=object
        ),
        meta_schema_version=np.int32(1),
    )

    # fsync the data file before rename
    fd = os.open(tmp, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

    os.replace(tmp, path)  # atomic on POSIX

    # fsync the directory to persist the rename
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
```

### Load function

```python
def load_epa_basis(path: Path) -> dict | None:
    if not path.exists():
        return None

    npz = np.load(path, allow_pickle=True)
    schema_version = int(npz['meta_schema_version'])
    if schema_version != 1:
        raise RuntimeError(f"unsupported epa_basis schema_version={schema_version}")

    return {
        'orthoBasis': npz['orthoBasis'],
        'basisMean': npz['basisMean'],
        'basisEnergies': npz['basisEnergies'],
        'basisLabels': [str(x) for x in npz['basisLabels']],
        'K': int(npz['meta_K']),
        'dim': int(npz['meta_dim']),
        'train_kind': str(npz['meta_train_kind']),
        'tag_count_at_train': int(npz['meta_tag_count_at_train']),
        'trained_at': str(npz['meta_trained_at']),
    }
```

## Cold-start scheme: precise behavior

### Trigger

`len(canonical_tag_vectors_global) < min_K * 2`, where `min_K = 8`. So threshold = **16 tags**.

### Cold-start basis construction

```python
def build_cold_start_basis(dim: int, K: int = 8) -> dict:
    """When tag_count < K*2, return a placeholder basis.

    The placeholder uses the first K columns of the dim-dimensional identity
    matrix (i.e., the first K standard unit vectors). This means projection
    becomes 'take the first K components of the centered query vector', which
    has no semantic meaning but won't crash downstream code.
    """
    assert K >= 1 and K <= dim

    return {
        'orthoBasis': np.eye(dim, dtype=np.float32)[:K],         # (K, D)
        'basisMean': np.zeros(dim, dtype=np.float32),             # (D,)
        'basisEnergies': np.ones(K, dtype=np.float32),
        'basisLabels': [f"axis-{k}" for k in range(K)],
        'K': K,
        'dim': dim,
        'train_kind': 'cold-start',
    }
```

### `project()` behavior under cold-start

The downstream `EPAProjector.project(query_vec)` should work identically regardless of `train_kind`:

```python
def project(self, query_vec: np.ndarray) -> dict:
    centered = query_vec - self.basisMean       # zero-mean → no-op for cold-start
    projections = self.orthoBasis @ centered     # (K,)
    total_energy = float((projections ** 2).sum())

    if total_energy < 1e-12:
        return {'dominantAxes': [], 'logicDepth': 0.0, 'entropy': 0.0}

    probs = (projections ** 2) / total_energy
    entropy = -float((probs * np.log2(probs + 1e-12)).sum())
    normalized_entropy = entropy / np.log2(self.K) if self.K > 1 else 0.0

    dominant_axes = sorted([
        {'index': k, 'label': self.basisLabels[k],
         'energy': float(probs[k]), 'projection': float(projections[k])}
        for k in range(self.K) if probs[k] > 0.05
    ], key=lambda a: -a['energy'])

    return {
        'projections': projections,
        'probabilities': probs,
        'entropy': normalized_entropy,
        'logicDepth': 1.0 - normalized_entropy,
        'dominantAxes': dominant_axes,
    }
```

Under cold-start: `dominantAxes` will have `label='axis-0'` etc., `logicDepth` will be uniform-ish (high entropy on identity projection of unit-normalized embedding). This is acceptable — Phase 2a's simplified `applyTagBoost` doesn't depend on `logicDepth` semantics yet (full EPA semantics arrive in Phase 2b).

### Graduation rule

In `train_epa_basis` (the orchestrator):

```python
def train_epa_basis_orchestrator() -> dict:
    tag_vectors = load_all_canonical_tag_vectors()  # (N, D)
    N = tag_vectors.shape[0]

    if N < 16:  # min_K * 2
        log.info(f"epa: cold-start ({N} tags)")
        return build_cold_start_basis(dim=cfg.model.dim, K=8)

    log.info(f"epa: real-pca on {N} tags")
    return train_real_pca(tag_vectors)  # see epa-basis-training.md
```

**Graduation is automatic**: next time the trigger fires (incremental_rebuild end with >20% tag delta), if `N >= 16`, real PCA runs and overwrites `epa_basis.npz` with `train_kind='real-pca'`. No special "graduation" code path.

## File locking and atomic write pattern

### Locking primitive: `fcntl.flock`

Python stdlib, POSIX-native, no extra dependency. Lock file alongside the data file:

```python
import fcntl
import contextlib

@contextlib.contextmanager
def epa_basis_lock(lock_path: Path, timeout_sec: float = 30.0):
    """Exclusive blocking lock with timeout via SIGALRM-free polling."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR)
    deadline = time.monotonic() + timeout_sec
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"epa_basis lock contention > {timeout_sec}s")
                time.sleep(0.1)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
```

### Why fcntl over alternatives

| Option | Pro | Con |
|---|---|---|
| `fcntl.flock` (chosen) | stdlib, advisory, no PID dance | POSIX only — Windows needs portalocker |
| `portalocker` | cross-platform | new dep |
| SQLite-as-lock | already in deployment | abuses DB; awkward semantics for a non-DB resource |
| `filelock` package | popular | new dep |

**Decision**: `fcntl.flock` for now. Project Dockerfile is Linux-only (`tool.uv.sources` has linux-only torch). If we ever need Windows local dev, swap to `filelock` package (uniform API).

### Atomic write pattern

Already covered in `save_epa_basis` above. Steps:
1. Write to `epa_basis.npz.tmp`
2. `fsync(tmp_fd)` — flush data to disk
3. `os.replace(tmp, dest)` — atomic on POSIX (single inode swap)
4. `fsync(dir_fd)` — persist the rename across crash

This guarantees: at any moment, `epa_basis.npz` either points to old fully-written data or new fully-written data, never partial.

## Race scenarios and safe sequencing

### Scenario 1: Two KBs trigger retrain simultaneously

```
KB-A: rebuild done, tag_count delta > 20% → call epa_retrain()
KB-B: rebuild done, tag_count delta > 20% → call epa_retrain()  (concurrent)
```

**Resolution**: `epa_basis_lock` serializes them. Whoever acquires the lock first does the work; the second one acquires the lock after, sees `tag_count_at_train` close to current count (because A's retrain bumped it), and the >20% delta check returns false → no-op.

```python
def epa_retrain_if_needed():
    with epa_basis_lock(LOCK_PATH):
        current = load_epa_basis(BASIS_PATH)
        new_tag_count = count_global_tags()
        if current and abs(new_tag_count - current['tag_count_at_train']) / max(current['tag_count_at_train'], 1) < 0.20:
            log.debug("epa: skip retrain (within 20% threshold)")
            return
        basis = train_epa_basis_orchestrator()
        save_epa_basis(BASIS_PATH, **basis, tag_count_at_train=new_tag_count)
```

### Scenario 2: Reader during writer

`load_epa_basis` is called by query path (or service startup). It reads `epa_basis.npz` without acquiring the lock — `os.replace` is atomic, so reader sees either old or new file content, never partial.

**Edge case**: reader opens file at moment T, file is replaced at T+1. The reader's open file descriptor still points to the old inode (POSIX semantics) — no corruption, just stale. Acceptable for query path.

If we want strict freshness, readers can acquire LOCK_SH (shared lock) — but for our use case this is over-engineering.

### Scenario 3: Service crash mid-write

Possibilities:
- Crash before `os.replace`: `.tmp` file remains, `epa_basis.npz` is old version → next startup ignores `.tmp` (or cleans it). System is consistent.
- Crash during `os.replace`: `os.replace` is atomic at the syscall level on POSIX — either old or new, never partial.
- Crash before `fsync(dir_fd)`: rename may not be persisted across power loss → next boot may see old file. Recovery: next retrain will run anyway (tag_count delta likely > 0% on resume). Acceptable.

### Scenario 4: Tag table modified between training and saving

```
T0: epa_retrain() acquires lock, starts loading tags
T1: load_all_canonical_tag_vectors() reads N=100 tags
T2: another rebuild commits, adds 10 tags → tag table has N=110
T3: epa_retrain() saves basis with tag_count_at_train=100
T4: epa_retrain releases lock
```

**Issue**: `tag_count_at_train=100` but actual count is 110. Next retrain check: `(110-100)/100 = 10% < 20%` → no retrain triggered, even though basis is missing 10 tags' info.

**Fix**: hold the lock around BOTH the read AND the train-and-save:

```python
def epa_retrain_if_needed():
    with epa_basis_lock(LOCK_PATH):  # holds for entire critical section
        current = load_epa_basis(BASIS_PATH)
        # Re-read tag count INSIDE the lock
        new_tag_count = count_global_tags()
        if current and abs(...) < 0.20:
            return
        # Read tag vectors INSIDE the lock
        tag_vectors = load_all_canonical_tag_vectors()
        basis = train_real_pca(tag_vectors) if len(tag_vectors) >= 16 else build_cold_start_basis(...)
        save_epa_basis(BASIS_PATH, **basis, tag_count_at_train=len(tag_vectors))
```

But the **rebuild process** that writes new tags also goes through the same lock? No — rebuild writes to `tags` table (SQLite), not to `epa_basis.npz`. They're different resources.

**Correct fix**: snapshot tag count at the moment of reading vectors:

```python
with epa_basis_lock(LOCK_PATH):
    tag_vectors_with_ids = load_all_canonical_tag_vectors_with_ids()  # SQLite read
    # tag_count_at_train = number actually used to train, NOT live count
    basis = train_real_pca(tag_vectors_with_ids[:, vector_cols])
    save_epa_basis(BASIS_PATH, **basis,
                   tag_count_at_train=len(tag_vectors_with_ids))
```

Then if tags table gains new rows during/after training, the next `epa_retrain_if_needed()` will compute delta against `tag_count_at_train` (= what we trained on) vs current. The 10-tag drift becomes part of the next delta check naturally. **No data loss** — just slight retrain delay. Acceptable.

## Final recommendation

| Decision | Choice | Reason |
|---|---|---|
| Algorithm | sklearn KMeans + sklearn PCA (full retrain) | Simpler; <1s at our scale; numerical stability |
| IncrementalPCA | **No** | Overkill for 15 MB matrix; complicates serialization |
| Storage format | numpy `.npz` (schema_version=1) | Forever-stable; easy to inspect |
| Locking | `fcntl.flock` on sibling `.lock` file | stdlib; sufficient for Linux deploys |
| Atomic write | `tmp + fsync + replace + fsync(dir)` | POSIX-standard pattern; crash-safe |
| Cold-start | Identity matrix `I_dim[:K]`, zero mean | Placeholder; auto-graduates when N≥16 |
| Retrain triggers | startup (if missing) / >20% tag delta / tag_rewrite / manual CLI | Bounded compute, follows real changes |
| Reader concurrency | No lock (rely on os.replace atomicity) | Stale data acceptable for projection |

## References

- sklearn PCA: https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html
- sklearn IncrementalPCA: https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.IncrementalPCA.html
- POSIX `os.replace` atomicity: https://pubs.opengroup.org/onlinepubs/9699919799/functions/rename.html
- `fcntl.flock` semantics: https://docs.python.org/3/library/fcntl.html#fcntl.flock
- numpy savez format: https://numpy.org/doc/stable/reference/generated/numpy.savez.html
- Atomic file write pattern (LWN): https://lwn.net/Articles/457667/
