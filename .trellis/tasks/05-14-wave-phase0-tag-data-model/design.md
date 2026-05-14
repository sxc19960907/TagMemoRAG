# Design — 浪潮回归 Phase 0：tag 数据模型对齐

## 目录与决策定位

本文档基于 `prd.md` 的 Resolved Decisions（D1-D5）与 `research/` 三份调研结果，给出 Phase 0 的技术设计。

实施顺序由 `implement.md` 接管。

## 范围回顾

Phase 0 = **数据基底**。完成后整个检索路径（execute_search）行为字节级不变，但 SQLite 中多出三张表 + 一个全局 `epa_basis.npz`，为 Phase 1+ 移植 `applyTagBoost / spike / geodesicRerank` 提供数据。

## 整体架构

```
                ┌──────────────────────────────────────────┐
                │  现有路径（Phase 0 不动）                 │
                │  upload → manual_records → rebuild       │
                │      → graph_builder → AppState.swap_kb  │
                │      → execute_search                    │
                └──────────────────────────────────────────┘
                                  │
                                  ▼  Phase 0 在这里挂钩
        ┌────────────────────────────────────────────────────┐
        │  incremental_rebuild 末尾追加：                     │
        │   1. upsert_canonical_tags_to_sqlite(kb, manuals)  │
        │   2. embed_dirty_tags(embedder)                    │
        │   3. epa_retrain_if_needed() (受全局锁)             │
        │   4. update task.impact_report 字段                │
        └────────────────────────────────────────────────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │  tags        │  │  manual_tags │  │  tag_intrins │
        │  (kb,name)   │  │  (kb,manual, │  │  ic_residual │
        │  vector BLOB │  │   tag_id,pos)│  │  s (留空1.0) │
        └──────────────┘  └──────────────┘  └──────────────┘
                              │
                              ▼
                     data/_global/epa_basis.npz
                     (受 .lock 文件锁保护)
```

**双缓冲不变**：tags / manual_tags / residuals 是 graph-independent 的全局资产，不参与 `AppState.swap_kb`。写入即生效，rebuild 失败不回滚（fail-forward；后续 rebuild 会修复）。EPA basis 同理。

## 模块划分

新增模块（5 个文件）：

| 模块 | 职责 | 依赖 |
|---|---|---|
| `src/tagmemorag/tag_store.py` | tags / manual_tags / residuals 三表的 CRUD（DAO 层） | manual_registry.py 的 SQLite 连接复用 |
| `src/tagmemorag/tag_embedder.py` | 增量计算 / upsert tag vectors | tag_store.py + Embedder |
| `src/tagmemorag/epa_basis.py` | 加载/训练/保存 epa_basis.npz；冷启动降级；文件锁 | sklearn (PCA, KMeans), tag_store |
| `src/tagmemorag/epa_projector.py` | 加载 basis 的纯读对象，提供 `project(query_vec)` API（Phase 0 不接入检索路径，仅供 Phase 2 使用） | epa_basis.py |
| `src/tagmemorag/cli.py` (修改) | 新增 `tagmemorag epa rebuild [--force]` 子命令 | epa_basis.py |

**修改的现有模块**：

| 模块 | 修改点 |
|---|---|
| `manual_registry.py` | `_init_schema` 增加三张表的 CREATE；`SQLiteManualRegistry` 暴露 `connection()` 上下文管理给 tag_store 复用 |
| `incremental_rebuild.py` | dirty manual 处理末尾调用 `tag_store.upsert_manual_tags` + `tag_embedder.embed_dirty_tags`；rebuild 末尾调用 `epa_basis.retrain_if_needed` |
| `tag_governance.py` | `commit_tag_rewrite` 末尾同步 SQLite tags / manual_tags + 标记 EPA dirty |
| `manuals.py` (delete 路径) | DELETE /manuals/{id} 时清理 manual_tags 行 + 孤儿 tags + EPA dirty 标记 |
| `state.py` | `RebuildTask` dataclass 增加四个字段：`tag_embeddings_added`, `tag_embeddings_skipped`, `epa_basis_train_kind`, `orphan_tags_removed` |
| `api.py` | rebuild 任务响应序列化时带上新字段（保持向后兼容，旧客户端忽略未知字段） |

**测试新增**：

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/unit/test_tag_store.py` | DAO 层 CRUD + UNIQUE 约束 + CASCADE |
| `tests/unit/test_tag_embedder.py` | 增量计算的幂等性、batch 行为、维度校验 |
| `tests/unit/test_epa_basis.py` | 冷启动降级、graduation、save/load roundtrip、schema_version |
| `tests/unit/test_epa_concurrency.py` | flock 串行化、双 KB 并发 retrain |
| `tests/unit/test_tag_governance_sqlite_sync.py` | tag_rewrite 同步 SQLite 路径 |
| `tests/integration/test_phase0_rebuild.py` | 完整 rebuild→tag 写入→EPA basis 文件生成的端到端流程 |
| `tests/e2e/test_search_baseline_invariance.py` | 验证 Phase 0 前后 execute_search 输出字节一致 |

## 数据契约

### SQLite schema（来自 research/source-data-model.md 终稿）

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

**关键决策**：
- **schema 名变更**：PRD 原写 `chunk_tags`，研究后改为 `manual_tags`（粒度对齐源头 file_tags，避免 chunk_count × tag_count 行膨胀）
- **`UNIQUE(kb_name, name)`** 替代源头的全局 `name UNIQUE`（不同 KB 同名 tag 视为不同实体）
- **`embedding_dim` + `embedded_at`** 是源头没有的新字段（防 embedder 模型切换）
- **`position` 1-indexed**，按 metadata.tags 数组下标 + 1 写入；保留 0 作 LEGACY_PHI 兼容值（Phase 0 不写 0）

### Vector BLOB 格式

- Float32 little-endian raw bytes，无 header
- Python：`np.array(vec, dtype=np.float32).tobytes()` 写；`np.frombuffer(blob, dtype=np.float32)` 读
- 读时强制校验 `len(blob) // 4 == tags.embedding_dim`，不一致则抛 `EmbeddingDimMismatchError` 并跳过该 tag（不阻塞 rebuild）

### epa_basis.npz 字段（来自 research/incremental-pca-feasibility.md）

| Field | Dtype | Shape | 说明 |
|---|---|---|---|
| orthoBasis | float32 | (K, D) | K 个正交基底向量 |
| basisMean | float32 | (D,) | 加权中心化均值 |
| basisEnergies | float32 | (K,) | 特征值/能量 |
| basisLabels | object[str] | (K,) | 每轴最近 tag 名 |
| meta_K | int32 | () | 实际 K |
| meta_dim | int32 | () | D（embedding 维度） |
| meta_train_kind | object[str] | () | "cold-start" 或 "real-pca" |
| meta_tag_count_at_train | int32 | () | 训练时 tag 总数 |
| meta_trained_at | object[str] | () | ISO 8601 UTC |
| meta_schema_version | int32 | () | 1（首版） |

存放路径：`{cfg.storage.data_dir}/_global/epa_basis.npz`
锁文件：`{cfg.storage.data_dir}/_global/epa_basis.lock`

## 关键算法

### Tag 增量 upsert（incremental_rebuild 钩子）

```python
def upsert_manual_tags(
    conn: sqlite3.Connection,
    kb_name: str,
    manual_id: str,
    metadata_tags: list[str],
) -> set[int]:
    """Returns the set of tag_ids referenced by this manual after upsert."""
    referenced: set[int] = set()
    for position, tag_name in enumerate(metadata_tags, start=1):  # 1-indexed
        tag_id = upsert_canonical_tag(conn, kb_name, tag_name)
        conn.execute(
            "INSERT OR REPLACE INTO manual_tags(kb_name, manual_id, tag_id, position) VALUES (?,?,?,?)",
            (kb_name, manual_id, tag_id, position),
        )
        referenced.add(tag_id)

    # 删除该 manual 不再引用的 tag 关联
    conn.execute(
        "DELETE FROM manual_tags WHERE kb_name=? AND manual_id=? AND tag_id NOT IN ({})".format(
            ",".join("?" * len(referenced)) or "NULL"
        ),
        (kb_name, manual_id, *referenced),
    )
    return referenced
```

**幂等性**：`INSERT OR REPLACE` 处理重复；末尾 DELETE 清理不再被该 manual 引用的关联。

### Tag embedding 增量

```python
def embed_dirty_tags(conn, kb_name: str, embedder: Embedder) -> dict[str, int]:
    rows = conn.execute(
        "SELECT id, name FROM tags WHERE kb_name=? AND vector IS NULL",
        (kb_name,),
    ).fetchall()
    if not rows:
        return {"added": 0, "skipped": 0}

    names = [r["name"] for r in rows]
    vectors = embedder.encode(names, batch_size=cfg.model.batch_size)
    # vectors: np.ndarray (N, D), dtype float32

    embedded_at = datetime.now(timezone.utc).isoformat()
    with conn:  # 单事务
        for row, vec in zip(rows, vectors):
            conn.execute(
                "UPDATE tags SET vector=?, embedding_dim=?, embedded_at=? WHERE id=?",
                (vec.astype(np.float32).tobytes(), int(vec.shape[0]), embedded_at, row["id"]),
            )
    return {"added": len(rows), "skipped": 0}
```

**为什么只 embed `vector IS NULL` 的 tag**：tag 文本不变就不重算（节省 embedder I/O）。tag 改名时 `commit_tag_rewrite` 会清空旧 vector 字段，下次 rebuild 自动重算。

### EPA retrain 决策与执行

```python
def retrain_if_needed(cfg: Settings, force: bool = False) -> dict | None:
    basis_path = Path(cfg.storage.data_dir) / "_global" / "epa_basis.npz"
    lock_path = basis_path.with_suffix(".lock")

    with epa_basis_lock(lock_path, timeout_sec=30.0):
        current = load_epa_basis(basis_path)

        # 读取所有 KB 的 canonical tag vectors
        with sqlite_conn(...) as conn:
            rows = conn.execute(
                "SELECT id, name, vector FROM tags WHERE vector IS NOT NULL"
            ).fetchall()
        N = len(rows)

        if not force and current is not None:
            prev_N = current["tag_count_at_train"]
            if prev_N > 0 and abs(N - prev_N) / prev_N < 0.20:
                return None  # 不需要重训

        if N < 16:  # min_K * 2
            basis = build_cold_start_basis(dim=cfg.model.dim, K=8)
            train_kind = "cold-start"
        else:
            tag_vectors = np.stack([
                np.frombuffer(r["vector"], dtype=np.float32) for r in rows
            ])
            basis = train_real_pca(tag_vectors, tag_names=[r["name"] for r in rows])
            train_kind = "real-pca"

        save_epa_basis(basis_path, **basis, tag_count_at_train=N)
        return {"train_kind": train_kind, "K": basis["K"], "tag_count": N}
```

**触发点**：
1. 服务启动检查（如 epa_basis.npz 不存在）
2. `incremental_rebuild` 末尾（带 force=False，跑 20% 阈值检查）
3. `commit_tag_rewrite` 末尾（带 force=True）
4. `tagmemorag epa rebuild` CLI（force 由 --force 决定）

## 一致性与失败处理

### tag_rewrite 一致性

`commit_tag_rewrite` 现在的逻辑（tag_governance.py:519-571）操作 `metadata.tags` 数组 + tag_policy.json。Phase 0 在末尾追加：

```python
def commit_tag_rewrite(...):
    # ... existing logic that mutates metadata.json across manuals ...

    # NEW: Phase 0 SQLite sync
    with sqlite_conn(...) as conn:
        for op in operations:  # rename / merge / delete
            if op.kind == "rename":
                conn.execute("UPDATE tags SET name=?, vector=NULL, embedded_at=NULL WHERE kb_name=? AND name=?",
                             (op.new_name, op.kb, op.old_name))
            elif op.kind == "merge":
                # 把 source tag 的所有 manual_tags 重定向到 target tag
                target_id = lookup_tag_id(conn, op.kb, op.target_name)
                source_id = lookup_tag_id(conn, op.kb, op.source_name)
                conn.execute("UPDATE OR IGNORE manual_tags SET tag_id=? WHERE tag_id=?", (target_id, source_id))
                conn.execute("DELETE FROM manual_tags WHERE tag_id=?", (source_id,))
                conn.execute("DELETE FROM tags WHERE id=?", (source_id,))
            elif op.kind == "delete":
                tag_id = lookup_tag_id(conn, op.kb, op.name)
                conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))  # CASCADE 处理 manual_tags

    # 标记 EPA dirty（force=True 触发立即重训）
    epa_basis.retrain_if_needed(cfg, force=True)
```

**注意**：`UPDATE OR IGNORE manual_tags` 处理"同一 manual 已经有 target tag"的冲突 — 此时旧关联保留 target 的 position。这是合理的 — merge 后用户体感是"同一 tag 出现两次"被去重。

### Manual 删除级联

`api.py` 的 `DELETE /manuals/{manual_id}` 当前调用 `manual_library.delete_manual`。Phase 0 在该函数末尾追加：

```python
def delete_manual(kb_name: str, manual_id: str, ...):
    # ... existing logic: registry status update + blob delete + dirty marking ...

    # NEW: Phase 0 SQLite cleanup
    with sqlite_conn(...) as conn:
        # 1. 删除该 manual 的所有 tag 关联
        conn.execute("DELETE FROM manual_tags WHERE kb_name=? AND manual_id=?",
                     (kb_name, manual_id))
        # 2. 找到无引用的 tag（孤儿）
        orphans = conn.execute(
            """SELECT t.id FROM tags t
               LEFT JOIN manual_tags mt ON mt.tag_id = t.id
               WHERE t.kb_name = ? AND mt.tag_id IS NULL""",
            (kb_name,),
        ).fetchall()
        if orphans:
            conn.execute(
                "DELETE FROM tags WHERE id IN ({})".format(",".join("?" * len(orphans))),
                tuple(o["id"] for o in orphans),
            )
            # 标记 EPA dirty
            mark_epa_dirty(...)

    return {"orphan_tags_removed": len(orphans)}
```

**EPA dirty 标记**：在 `RebuildTask` 增加 `epa_dirty: bool` 内存字段，rebuild 末尾检查 + 触发 retrain。这避免每次 manual 删除都立即 retrain（高频操作时浪费）。

### Embedder 失败的容错

`embed_dirty_tags` 在单事务内 batch encode，失败后整批 vectors 不写入。下次 rebuild 自动重试（vector 仍是 NULL）。**不阻塞 rebuild 主流程**：捕获异常，写 task.impact_report 的 `tag_embedding_failed_count` 字段。

### EPA retrain 失败的容错

`retrain_if_needed` 内部 try/except 包住训练逻辑。失败时：
- 不更新 `epa_basis.npz`（保留旧文件 — 可能是过期的，但能用）
- 写 task.impact_report 的 `epa_train_error` 字段
- 释放锁
- 不阻塞 rebuild

服务启动时若发现 `epa_basis.npz` 完全缺失，强制走 cold-start 路径生成一个最小可用版本。

## 配置变更

新增 `config.yaml` 字段：

```yaml
wave_phase0:                    # 整个组保留为 Phase 0 标记
  tag_embedding_enabled: true   # 紧急回滚开关；false 时跳过 embed_dirty_tags
  epa_basis_enabled: true       # 紧急回滚开关；false 时跳过 retrain
  epa_min_K: 8                  # research 推荐
  epa_cluster_count: 32         # K-Means 簇数
  epa_energy_threshold: 0.95    # 累计方差阈值
  epa_retrain_delta: 0.20       # tag count 变化触发阈值
  epa_lock_timeout_sec: 30.0
```

**为什么有开关**：Phase 0 是底层改动，万一在生产触发非预期问题，运维可以一键关掉 tag embedding 或 EPA 训练，不必回滚代码。回滚比开关代价大得多。

## 可观测性

`RebuildTask` 字段新增：

```python
@dataclass
class RebuildTask:
    # ... existing ...
    tag_embeddings_added: int = 0
    tag_embeddings_skipped: int = 0
    tag_embeddings_failed: int = 0
    epa_basis_train_kind: str = ""    # "" | "cold-start" | "real-pca" | "skipped"
    epa_basis_K: int = 0
    epa_basis_tag_count: int = 0
    epa_train_error: str = ""
    orphan_tags_removed: int = 0
```

通过 `GET /rebuild/{task_id}` 暴露给运维。

Prometheus metrics（observability/metrics.py 复用现有模式）：

- Counter: `tagmemorag_tag_embeddings_total{kb_name, status="added|skipped|failed"}`
- Gauge: `tagmemorag_tags_total{kb_name}`
- Counter: `tagmemorag_epa_basis_retrain_total{kind="cold-start|real-pca|skipped"}`
- Histogram: `tagmemorag_epa_basis_retrain_duration_seconds`

## 回滚（rollback shape）

回到 Phase 0 之前的状态需要：

1. **数据**：
   ```sql
   DROP TABLE IF EXISTS manual_tags;
   DROP TABLE IF EXISTS tag_intrinsic_residuals;
   DROP TABLE IF EXISTS tags;
   ```
   ```bash
   rm -rf data/_global/
   ```

2. **配置**：删除 `config.yaml` 的 `wave_phase0` 段

3. **代码**：git revert 整个 Phase 0 commit 范围

**关键不变量**：execute_search 的输出在 Phase 0 前后字节级一致 — 这是 AC6 的硬要求，由 `tests/e2e/test_search_baseline_invariance.py` 锁住。所以即使数据全清，搜索质量也不会回退（因为 Phase 0 根本没读 tags 表参与检索）。

## 兼容性

- **旧 manual_registry.sqlite3**：`CREATE TABLE IF NOT EXISTS` 幂等，旧库直接 attach 即可
- **旧 metadata.json**：tags 数组照旧解析，position 由 Phase 0 写入时的下标决定
- **未升级客户端**：rebuild 任务响应新增字段，旧客户端 JSON 解析时忽略未知字段（Pydantic / Go json 默认行为）

## 不预防的事

明确 NOT 处理：
- **多语言 tag 翻译**：fixture 已混合 zh-CN / en，BAAI/bge-small-zh-v1.5 是双语模型，直接 embed tag 字面（"fault-code" / "故障码"）。如果未来发现跨语言 tag 召回差，再做翻译预处理。
- **synonym tag embedding**：当前 tags 表只存 canonical。synonym 由 `tag_governance` 在 metadata 写入前已折叠成 canonical。
- **Tag 删除时的全局 EPA 立即重训**：用 dirty 标记延迟到 rebuild 末尾，避免高频抖动。
- **跨 KB 检索**：`/search` 仍只搜单 KB，不读 EPA basis。EPA 是为 Phase 2+ 准备的。

## Open implementation questions（实施期间可能浮现）

这些不是 blocking decision，留给 implement 阶段处理：

1. `manual_registry.py` 的 `connection()` 上下文是否需要新接口？或者 tag_store 直接复用 `_connect()`？
2. `embedder.encode` 的 batch 失败语义：单条失败影响整批吗？需读现有实现。
3. EPA basis 训练失败时是否记 metrics counter？（建议：记）
4. 现有 `incremental_rebuild` 的事务边界 — tag upsert 是放在 graph swap 之前还是之后？（设计倾向：之前，因为 tag 表是 graph-independent 的全局资产）

implement.md 会逐一回答。
