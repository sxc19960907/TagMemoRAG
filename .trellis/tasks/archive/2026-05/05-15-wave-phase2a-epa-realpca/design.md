# Design — Phase 2a：EPA real-PCA 通路验证 + dynamic boost 接通

## 目的

把 PRD 的 6 个决策（D1-D6）落到模块级契约和数据契约，给 implement.md 一个可执行的步骤蓝图。Phase 2a 是 Lightweight 任务，本设计只做最小化的"模块边界 + 数据契约 + 关键算法步骤 + 失败语义"四项。

## 模块边界

```
┌─────────────────────────────────────────────────────────────────────┐
│ Edge: api.py / cli.py — 不动                                        │
└────────────────┬────────────────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────────────────┐
│ Search core                                                         │
│   wave_tag_spike._resolve_dynamic_boost ★MOD                        │
│     └─ strategy="epa" 路径：dynamic = max(epa_floor, logicDepth*K)  │
│   wave_tag_spike.apply_tag_boost — 不动（继续调用 _resolve）        │
│   search_runtime.execute_search — 不动                              │
└────────────────┬────────────────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────────────────┐
│ Phase 0 EPA pipeline — 不动算法                                     │
│   epa_basis.retrain_if_needed — 不动                                │
│   epa_basis.train_real_pca — 不动                                   │
│   epa_projector.project — 不动                                      │
└────────────────┬────────────────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────────────────┐
│ Config                                                              │
│   config.WavePhase1Config ★MOD: + epa_logic_depth_scale=1.0         │
│                                  + epa_floor=0.0                    │
│   config.yaml ★MOD: 同步加两个字段（默认值等价 Phase 1）            │
└────────────────┬────────────────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────────────────┐
│ Diagnostics & Fixtures                                              │
│   scripts/diag_epa_logic_depth.py ★ NEW                             │
│   tests/fixtures/product_manuals/<one>.metadata.json ★MOD           │
│     +2 tags 让全局 unique 从 10 → 12                                │
│   tests/unit/test_epa_logic_depth.py ★ NEW                          │
└─────────────────────────────────────────────────────────────────────┘
```

## 数据契约

### WavePhase1Config 新增字段

```python
class WavePhase1Config(BaseModel):
    ...  # 现有字段不动
    # Phase 2a：EPA dynamic boost 形态
    epa_logic_depth_scale: float = Field(default=1.0, ge=0.0)
    epa_floor: float = Field(default=0.0, ge=0.0)
```

默认值（1.0 / 0.0）让 `dynamic = max(0.0, logicDepth * 1.0)` 等价 Phase 1 现状（除了 logicDepth=0 时不再被 floor 抬起 — 但 Phase 1 也是直接返回 logicDepth 让 dynamic_boost_min 在外层 clip 兜底，语义等价）。

### `_resolve_dynamic_boost` 新逻辑

```python
def _resolve_dynamic_boost(query_vec: np.ndarray, settings: Settings) -> float:
    strategy = settings.wave_phase1.dynamic_boost_factor_strategy
    if strategy == "constant":
        return 1.0
    if strategy == "epa":
        try:
            from .epa_basis import basis_path
            from .epa_projector import EPAProjector
        except Exception:
            return 1.0
        try:
            projector = EPAProjector.from_path(basis_path(settings))
        except Exception:
            return 1.0
        try:
            projection = projector.project(np.asarray(query_vec, dtype=np.float32))
        except Exception:
            return 1.0
        logic_depth = max(0.0, float(projection.get("logicDepth", 0.0)))
        scale = float(settings.wave_phase1.epa_logic_depth_scale)
        floor = float(settings.wave_phase1.epa_floor)
        return max(floor, logic_depth * scale)
    return 1.0
```

外层 `apply_tag_boost` 仍然 `np.clip(dynamic, [dynamic_boost_min, dynamic_boost_max])` 后乘 `base_tag_boost`，最后 `min(1.0, ...)` 得 alpha。

### 诊断脚本输出格式

```
=== EPA Diagnostic ===
Cold-start: train_kind=cold-start  K=8
  PCA explained_variance_ratio: N/A (cold-start)
  logicDepth: mean=X std=X range=[X, X]
  alpha:      mean=X std=X range=[X, X]

Real-PCA (epa_min_k=4, tag_count=12): train_kind=real-pca  K=8
  PCA explained_variance_ratio: [0.31, 0.18, ...] sum_top_K=0.85
  logicDepth: mean=X std=X range=[X, X]
  alpha:      mean=X std=X range=[X, X]
  std(alpha) > 0.005:               PASS / FAIL
  range(alpha)/mean(alpha) > 0.1:   PASS / FAIL

=> overall: PASS / FAIL
```

### Fixture 扩展（最小改动）

挑 1 个现有 manual（推荐 `air_conditioner/ac_ap12.metadata.json`，因为现有 tag 集独立度高）补 2 个新 tag。具体哪 2 个 tag implement 阶段决定，原则：
- 选语义合理的（"airflow", "filter-cleaning"）
- 不要复用其他 manual 已有 tag（保证全局 unique 真涨 2）
- 不要触发 8 个 eval suite 任何 question 的 tag-filter 行为（保持 baseline 不漂）

## 关键算法步骤

### 诊断脚本（M1 / `scripts/diag_epa_logic_depth.py`）

```python
def run_diag(*, embedder="hashing", min_k=4) -> DiagReport:
    # 1. 临时 data_dir + cfg 调低 min_k
    cfg = Settings(
        model={"provider": "hashing", "dim": 64, "batch_size": 16},
        wave_phase0={"epa_min_k": min_k},
        ...,
    )
    with tempfile.TemporaryDirectory() as tmp:
        cfg.storage = StorageConfig(data_dir=tmp)

        # 2. build_kb 在 12-tag fixture 上 → 触发 real-pca
        build_kb(fixture_root, "default", cfg, embedder=hashing_embedder)
        basis = load_epa_basis(basis_path(cfg))

        # 3. 收集 query 集
        queries = []
        for suite in glob("tests/fixtures/eval/*.jsonl"):
            for line in open(suite):
                queries.append(json.loads(line)["question"])

        # 4. 双 strategy × N queries 跑 alpha
        results_constant = [...]
        results_epa = []
        for q in queries:
            qv = embedder.encode(q)
            ld = projector.project(qv)["logicDepth"]
            cfg.wave_phase1.dynamic_boost_factor_strategy = "epa"
            _, info = apply_tag_boost(qv, kb_name="default", settings=cfg, base_tag_boost=0.03)
            results_epa.append((ld, info.boost_factor_applied))

        # 5. 输出诊断
        report = DiagReport(
            train_kind=basis.train_kind,
            explained_variance=...,  # only for real-pca
            cold_start_alpha=...,
            real_pca_alpha=...,
            d2_pass=(std > 0.005 and range_over_mean > 0.1),
        )
        return report
```

输出渲染按上面的表格格式打到 stdout，return-code = 0 if PASS else 1（让 CI 可选用）。

### Fallback 单测（M2 / `tests/unit/test_epa_logic_depth.py`）

3 段单测：

```python
def test_resolve_dynamic_constant_unchanged():
    # strategy=constant ⇒ 1.0，与 Phase 1 一致
    ...

def test_resolve_dynamic_epa_with_real_pca_basis(tmp_path):
    # 写真 PCA basis 到 tmp，调 _resolve_dynamic_boost(strategy=epa)
    # 期望：返回值 = max(floor, logicDepth * scale)
    ...

def test_resolve_dynamic_epa_degenerate_query_falls_back_to_floor(tmp_path):
    # AC4 锁底：写真 PCA basis，传一个 logicDepth 必然为 0 的 query
    # 期望：返回值 = epa_floor（不爆炸）
    ...

def test_resolve_dynamic_epa_default_params_equivalent_to_phase1():
    # AC6 锁底：scale=1.0 / floor=0.0 时，返回值 == max(0, logicDepth * 1.0) == logicDepth
    ...
```

加一段 e2e：

```python
def test_apply_tag_boost_strategy_epa_passes_d2_threshold(tmp_path):
    # AC3 锁底：epa_min_k=4 + 12 unique tags + strategy=epa
    # 跑诊断 query 集 → 收集 alpha 序列 → 验证 D2 阈值
    ...
```

## 集成点细节

### config.py 修改

```python
class WavePhase1Config(BaseModel):
    ...  # 现有 19 个字段不动
    epa_logic_depth_scale: float = Field(default=1.0, ge=0.0)
    epa_floor: float = Field(default=0.0, ge=0.0)
```

### config.yaml 同步

```yaml
wave_phase1:
  ...  # 现有字段不动
  dynamic_boost_factor_strategy: constant
  dynamic_boost_min: 0.3
  dynamic_boost_max: 2.0
  epa_logic_depth_scale: 1.0      # ★ NEW
  epa_floor: 0.0                  # ★ NEW
```

## 失败 / 降级语义

| 场景 | 行为 |
|---|---|
| `strategy="constant"` | 同 Phase 1，恒等 1.0 |
| `strategy="epa"` + EPA basis 不存在 | `EPAProjector.from_path` 抛 FileNotFoundError ⇒ except 捕获 ⇒ return 1.0（同 Phase 1） |
| `strategy="epa"` + EPA basis 加载失败 | 同上，return 1.0 |
| `strategy="epa"` + projector.project 抛错（dim 不匹配等） | 同上，return 1.0 |
| `strategy="epa"` + logicDepth = 0（query 退化） | `max(epa_floor, 0)` = epa_floor。默认 0.0 ⇒ 后续 `np.clip(dynamic, [0.3, 2.0])` 抬到 0.3。等价 Phase 1 |
| `strategy="epa"` + scale 配置过小（如 0.0） | `max(0, 0)` = 0 ⇒ clip 到 0.3 ⇒ 等价 Phase 1 dynamic_boost_min 兜底 |
| 诊断脚本跑出 FAIL | 不阻塞 implement；implement 阶段决定调 scale 默认值还是接受 FAIL（决策回写 PRD） |

## 兼容性

| 维度 | 行为 |
|---|---|
| 旧 `config.yaml` 没新字段 | pydantic 默认值 1.0 / 0.0 兜住，行为等同 Phase 1 |
| `strategy="constant"`（默认） | 完全等价 Phase 1 |
| Phase 0 e2e baseline invariance | spike-off 路径不动，继续过 |
| 8 个 hashing eval suite | spike-on 路径下，alpha 浮动幅度仅在 strategy=epa 时改变；strategy=constant 默认 ⇒ baseline 不漂 |
| EPA 训练失败 | 既有 `epa_train_error` 字段沿用，本任务不动 |

## 回滚

```yaml
# 软回滚（不删数据）
wave_phase1:
  dynamic_boost_factor_strategy: constant   # 等价 Phase 1
  # 或保持 strategy=epa 但
  epa_logic_depth_scale: 1.0    # 等价 Phase 1
  epa_floor: 0.0
```

```bash
# 硬回滚（删数据 + revert）
rm -f data/_global/epa_basis.npz
git revert <phase2a-commit-range>
```

## Open implementation questions（implement 阶段回答）

1. **fixture 加哪 2 个 tag**：implement 阶段挑选，原则见上文 Fixture 扩展段。
2. **诊断脚本默认 scale 调多少**：implement 阶段跑出诊断结果再决定。如果 scale=1.0 已 PASS ⇒ 不动；如果 FAIL ⇒ 试 scale=1.5/2.0/3.0 找最小达标值，决策回写 PRD 作为 D7。
3. **诊断脚本是否进 CI**：默认不进（一次性投资，跑 1-2s）；implement 阶段决定是否加到 `run_eval_ci.py` 之后做 sanity。建议不进 CI（避免在 EPA basis 漂动时无端 fail）。
