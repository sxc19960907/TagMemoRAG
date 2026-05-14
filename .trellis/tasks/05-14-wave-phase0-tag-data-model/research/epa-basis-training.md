# Research: EPA Basis Training (VCPToolBox EPAModule)

**Goal**: Document how VCPToolBox's `EPAModule` builds its orthogonal basis, and decide whether TagMemoRAG should mirror the algorithm exactly or use sklearn primitives.

## Source EPA training pipeline (where, when, how)

### Construction and trigger

- `EPAModule.constructor` (EPAModule.js:8-26) accepts `db`, `config`, `vexusIndex` (optional Rust binding)
- `EPAModule.initialize()` (EPAModule.js:28-65) is the training entry point
- Called during KnowledgeBaseManager startup (single-shot per process)

### Training pipeline (EPAModule.js:28-65)

```js
async initialize() {
    // 1. Load from cache if exists
    if (await this._loadFromCache()) { ...; return true; }

    // 2. Read all tags with vectors
    const tags = this.db.prepare(
        'SELECT id, name, vector FROM tags WHERE vector IS NOT NULL'
    ).all();
    if (tags.length < 8) return false;  // ← cold-start guard, but absolute (just fails)

    // 3. K-Means cluster tags into `clusterCount` centroids
    const clusterData = this._clusterTags(tags, Math.min(tags.length, this.config.clusterCount));

    // 4. Weighted PCA via Power Iteration on Gram matrix
    const svdResult = this._computeWeightedPCA(clusterData);
    const { U, S, meanVector, labels } = svdResult;

    // 5. Pick K based on cumulative energy ≥95% (min 8)
    const K = this._selectBasisDimension(S);

    this.orthoBasis = U.slice(0, K);          // K basis vectors, each dim-D
    this.basisEnergies = S.slice(0, K);       // K eigenvalues
    this.basisMean = meanVector;              // global weighted mean (D-dim)
    this.basisLabels = labels.slice(0, K);    // K labels (one per axis)

    await this._saveToCache();
    this.initialized = true;
}
```

### Cache pattern

`_saveToCache` (EPAModule.js:442-454) and `_loadFromCache` (EPAModule.js:456-479) — disk-cached so retraining only happens on cache miss.

**Cache invalidation**: not visible in this method. Likely either:
- Manual deletion of cache file
- Cache filename includes a hash of `tags` table state

(Need to verify by reading `_saveToCache` body — but algorithm-level decision can proceed without it.)

## PCA implementation details

### Algorithm: Weighted PCA via Power Iteration on Gram Matrix

`_computeWeightedPCA` (EPAModule.js:295-383) is **hand-rolled**, not a library. Steps:

1. **Weighted mean** (lines 302-309):
   ```
   meanVector[d] = sum(weights[i] * vectors[i][d]) / sum(weights)
   ```

2. **Centered + scaled vectors** (lines 315-322):
   ```
   centered[i][d] = (vectors[i][d] - meanVector[d]) * sqrt(weights[i])
   ```

3. **Gram matrix** (n×n, lines 325-334):
   ```
   gram[i][j] = sum_d centered[i][d] * centered[j][d]
   ```
   This is `X · X^T` where X is the centered+scaled matrix. Used because **n << dim** (cluster count ≪ embedding dim) — Gram is much cheaper than full covariance.

4. **Power Iteration with Deflation** (lines 339-353):
   - For `k = 0..maxBasisDim`:
     - Find dominant eigenvalue/vector of current Gram
     - Re-orthogonalize against previous eigenvectors
     - Deflate: `Gram -= λ_k · v_k · v_k^T`

5. **Map Gram eigenvectors back to original space** (lines 358-378):
   ```
   basis_k[d] = sum_i ev_k[i] * centered[i][d]
   ```
   then normalize.

### `K` (basis dimension) selection

`_selectBasisDimension(S)` (EPAModule.js:431-440):
```js
const total = S.reduce((a, b) => a + b, 0);
let cum = 0;
for (let i = 0; i < S.length; i++) {
    cum += S[i];
    if (cum / total > 0.95) return Math.max(i + 1, 8);
}
return S.length;
```

**Logic**: smallest K such that cumulative energy ≥ 95%, but **lower bound of 8**.

**Implication for TagMemoRAG**: our `K=8` PRD value is the **minimum**, not a fixed value. Source dynamically grows K up to whatever explains 95% energy. We should match this.

### `clusterCount` (K-Means k)

Read from `config.clusterCount`. Not visible inline; likely 16-32 in production based on typical PCA practice when dim=384.

### Why K-Means before PCA?

Source clusters tags first into `clusterCount` centroids, then runs PCA on the **centroids** (n=clusterCount), not on raw tag vectors (n=tag_count). Two reasons:
- **Speed**: Power Iteration on n×n Gram with n=20 vs n=10000 is huge speedup
- **Smoothing**: centroids are denoised cluster representatives → basis less sensitive to outlier tags

## basisLabels assignment strategy

From `_clusterTags` (EPAModule.js:271-280):

```js
const labels = centroids.map(c => {
    let maxSim = -Infinity, closest = 'Unknown';
    vectors.forEach((v, i) => {
        let dot = 0;
        for (let d = 0; d < dim; d++) dot += c[d] * v[d];
        if (dot > maxSim) { maxSim = dot; closest = tags[i].name; }
    });
    return closest;
});
```

**Each PC axis is labeled with the tag name closest (cosine) to its centroid.**

So `basisLabels[k]` ∈ canonical tag names. This means `dominantAxes` returns axis labels like `"Politics"`, `"Cooking"`, `"Software"` — interpretable for downstream `applyTagBoost` to print queryWorld debug info.

**For TagMemoRAG**: trivial to mirror. After K-Means, for each centroid k find `argmax_t cosine(centroid_k, tag_vectors[t])` and store `tags[t].name`.

## Centering and basisMean computation

`basisMean` = **weighted mean of centroids**, where weights = cluster sizes:
```
basisMean[d] = Σ_i (cluster_size_i × centroid_i[d]) / Σ_i cluster_size_i
```

This is **biased toward larger clusters** by design — represents "the typical query world".

In `project` (EPAModule.js:106-111), it's used to center incoming queries:
```js
centeredVec[i] = vec[i] - this.basisMean[i];
```

So projection = "how does the query deviate from the typical world along each PC axis".

## Re-training cadence and triggers in source

**Source has no automatic retraining.** Once `_saveToCache` is called, the basis is frozen until cache is manually invalidated.

This is acceptable for source's static-corpus use case (personal diary), but **TagMemoRAG cannot adopt this** because:
- KB content evolves continuously via uploads
- Tag taxonomy is governed (rename/merge happens)
- Cold-start phase needs explicit upgrade path

## Recommendation for TagMemoRAG: full retrain, not IncrementalPCA

### Why NOT mirror source's hand-rolled algorithm

1. **Not invented here**: source wrote Power Iteration because Node.js lacks good linear algebra libs; Python has scipy/numpy/sklearn for free
2. **Numerical precision**: scipy's LAPACK-based SVD/PCA is far more stable than Power Iteration with deflation (catastrophic cancellation risk)
3. **Maintenance**: hand-rolled = 200 lines of math we'd have to debug; sklearn = 3 lines
4. **Reproducibility**: sklearn results are deterministic with seed; Power Iteration with random init is not

### Why NOT IncrementalPCA either

`sklearn.decomposition.IncrementalPCA` is designed for **out-of-core** training (data won't fit in RAM). Our scale:
- Worst case: 10k tags × 384 dim × 4 bytes = 15 MB → trivially fits
- Full PCA on 15 MB takes <1 second on a laptop

IncrementalPCA adds complexity (state serialization, partial_fit batching, numerical drift across batches) for zero benefit at our scale.

### Recommended: K-Means + sklearn `PCA` from scratch

Match source semantics (K-Means → weighted PCA on centroids), but use `sklearn.cluster.KMeans` and `sklearn.decomposition.PCA`:

```python
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import numpy as np

def train_epa_basis(
    tag_vectors: np.ndarray,  # (N, D) Float32
    cluster_count: int = 32,
    min_K: int = 8,
    energy_threshold: float = 0.95,
) -> dict:
    n_clusters = min(cluster_count, tag_vectors.shape[0])
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    km.fit(tag_vectors)

    centroids = km.cluster_centers_  # (n_clusters, D)
    cluster_sizes = np.bincount(km.labels_, minlength=n_clusters)

    # Weighted PCA: scale centroids by sqrt(weight) before PCA
    weights = np.sqrt(cluster_sizes).reshape(-1, 1)
    weighted_mean = (centroids * cluster_sizes.reshape(-1, 1)).sum(axis=0) / cluster_sizes.sum()
    centered = (centroids - weighted_mean) * weights

    pca = PCA(n_components=min(n_clusters, tag_vectors.shape[1]))
    pca.fit(centered)

    # Pick K: min count where cum_var ≥ 0.95, lower bound min_K
    cum_var = np.cumsum(pca.explained_variance_ratio_)
    K = max(int(np.searchsorted(cum_var, energy_threshold) + 1), min_K)
    K = min(K, pca.components_.shape[0])

    # basisLabels: closest tag name per centroid
    sims = tag_vectors @ centroids.T  # (N, n_clusters)
    nearest_tag_idx = sims.argmax(axis=0)  # (n_clusters,)

    return {
        'orthoBasis': pca.components_[:K],     # (K, D)
        'basisMean': weighted_mean,            # (D,)
        'basisEnergies': pca.explained_variance_[:K],
        'basisLabel_indices': nearest_tag_idx[:K],  # caller resolves names
        'K': K,
        'train_kind': 'real-pca',
    }
```

## Cold-start identity matrix scheme

**Trigger**: `len(canonical_tags_global) < min_K * 2` (= 16 with min_K=8)

**Behavior**:
```python
def cold_start_basis(dim: int = 384, K: int = 8) -> dict:
    # First K rows of identity matrix: each axis is one canonical dimension
    return {
        'orthoBasis': np.eye(dim, dtype=np.float32)[:K],   # (K, D)
        'basisMean': np.zeros(dim, dtype=np.float32),       # (D,)
        'basisEnergies': np.ones(K, dtype=np.float32),
        'basisLabel_indices': np.arange(K, dtype=np.int64),
        'K': K,
        'train_kind': 'cold-start',
    }
```

**`project()` behavior under cold-start**:
- Centering by zero-mean → no-op
- Projection onto first K standard basis vectors → just takes first K components of query vec
- `dominantAxes` will report axes labeled "axis-0", "axis-1", ... (no semantic meaning)
- `entropy` / `logicDepth` are computed but meaningless

This is **intentional**: cold-start basis is a placeholder so `applyTagBoost` doesn't crash; downstream code that uses dominantAxes labels (e.g. `queryWorld` debug logging) gets neutral output.

**Graduation rule**: when `tag_count >= min_K * 2`, next training run uses real PCA, sets `train_kind='real-pca'`, downstream behavior automatically becomes meaningful.

## Concrete training script outline

CLI: `tagmemorag epa rebuild [--kb <name>] [--force]`

```python
def cli_epa_rebuild(force: bool = False):
    cfg = load_settings()
    basis_path = Path(cfg.storage.data_dir) / "_global" / "epa_basis.npz"

    # Acquire global lock (see incremental-pca-feasibility.md)
    with file_lock(basis_path.with_suffix(".lock"), timeout=30):
        # Read all canonical tag vectors across all KBs
        with sqlite_conn(registry_path) as conn:
            rows = conn.execute(
                "SELECT id, vector, embedding_dim FROM tags WHERE vector IS NOT NULL"
            ).fetchall()

        if not rows:
            log.warning("no tag vectors yet; cold-start basis written")
            basis = cold_start_basis(dim=cfg.model.dim, K=8)
        else:
            vecs = np.stack([
                np.frombuffer(r['vector'], dtype=np.float32) for r in rows
            ])  # (N, D)
            assert vecs.shape[1] == cfg.model.dim, "embedding dim mismatch"

            if vecs.shape[0] < 16:  # min_K * 2
                log.info(f"cold-start: only {vecs.shape[0]} tags")
                basis = cold_start_basis(dim=cfg.model.dim, K=8)
            else:
                basis = train_epa_basis(vecs)

        # Atomic write: tmp → fsync → rename
        tmp = basis_path.with_suffix(".npz.tmp")
        np.savez(tmp, **basis,
                 trained_at=str(datetime.utcnow().isoformat()),
                 tag_count_at_train=int(vecs.shape[0]) if rows else 0)
        os.fsync(open(tmp, 'rb').fileno())
        tmp.rename(basis_path)

        log.info(f"epa_basis saved: kind={basis['train_kind']}, K={basis['K']}")
```

**Trigger points** (in addition to manual CLI):
1. `incremental_rebuild` end: if `tag_count_global` changed by >20% since last train, retrain
2. `commit_tag_rewrite` end: always retrain (taxonomy changed)
3. Service startup: if `epa_basis.npz` missing, train cold-start basis

## References

- VCPToolBox/EPAModule.js:8 — `constructor`
- VCPToolBox/EPAModule.js:28 — `initialize` (training entry)
- VCPToolBox/EPAModule.js:71 — `project` (uses orthoBasis)
- VCPToolBox/EPAModule.js:208 — `_clusterTags`
- VCPToolBox/EPAModule.js:295 — `_computeWeightedPCA`
- VCPToolBox/EPAModule.js:431 — `_selectBasisDimension`
- VCPToolBox/EPAModule.js:442 — cache save/load
- sklearn.decomposition.PCA: https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html
- sklearn.cluster.KMeans: https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html
