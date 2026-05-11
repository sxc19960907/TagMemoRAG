# design.md — 浪潮RAG M0 功能核心技术设计

> 约束：本文档只覆盖 M0 里程碑。M1-M4 在此架构上叠加，不改核心。
> 父文档：[prd.md](./prd.md)

---

## 1. 模块边界与依赖关系

```
                       ┌──────────────────┐
                       │  CLI / API层     │
                       │ cli.py / api.py  │
                       └────────┬─────────┘
                                │ 通过 AppState 单例访问
                                ▼
                       ┌──────────────────┐
                       │   AppState       │
                       │   state.py       │
                       │ (current_graph,  │
                       │  stores, anchors,│
                       │  build_id, lock) │
                       └────────┬─────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
┌─────────────────┐   ┌──────────────────┐   ┌─────────────────┐
│ WaveSearcher    │   │  AnchorSystem    │   │   StoreLayer    │
│ wave_searcher.py│   │   anchor.py      │   │  storage/*.py   │
└───────┬─────────┘   └────────┬─────────┘   └────────┬────────┘
        │                      │                      │
        └──────────┬───────────┴──────────────────────┘
                   ▼
         ┌──────────────────┐
         │  GraphBuilder    │
         │ graph_builder.py │
         └────────┬─────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
┌──────────────┐   ┌──────────────┐
│DocumentParser│   │   Embedder   │
│  parser.py   │   │ embedder.py  │
└──────────────┘   └──────────────┘
```

**依赖方向**：自上而下，不允许反向依赖。`WaveSearcher` 不知道 `api.py` 存在；`GraphBuilder` 不知道 `AppState` 存在。

**纯函数层**：`parser / embedder / graph_builder / wave_searcher` 无副作用，便于单测。
**有状态层**：`AppState / AnchorSystem / StoreLayer`。

---

## 2. 数据契约（核心数据结构）

### 2.1 Chunk（文档块）

```python
@dataclass(frozen=True)
class Chunk:
    text: str                  # 块正文
    header: str                # 所属标题（最近一级）
    path: tuple[str, ...]      # 标题路径，如 ("安装", "电源连接")
    level: int                 # 标题层级（# = 1，## = 2）
    start_line: int            # 原文起始行号（溯源用）
    source_file: str           # 原文件相对路径
```

`path` 用 `tuple` 而非 `list` 是因为 `Chunk` 要能 hash（支持 `anchor_key` 计算前的 dedup）。

### 2.2 GraphNode（图节点属性）

NetworkX 节点 id = `int`（构图时顺序分配）。节点属性：

```python
{
    "text": str,
    "header": str,
    "path": list[str],          # JSON 序列化时 tuple → list
    "level": int,
    "start_line": int,
    "source_file": str,
    "anchor_key": str,          # 12 位稳定标识，见 §4.2
}
```

**不存** `embedding`：向量独立存在 `NpzVectorStore`，节点 id 即索引。

### 2.3 Edge（边属性）

```python
{
    "weight": float,            # 最终权重，∈ (0, 1]，上限 1.0
    "kind": str,                # "semantic" | "parent_child" | "sibling" | "consecutive"
}
```

同一对节点可能同时满足多种关系，按"**取最大权重 + 记录主导 kind**"合并，不建多重边（保持简单图）。

### 2.4 Anchor

```python
@dataclass
class Anchor:
    anchor_key: str             # sha256(path|header|text[:80])[:12]
    label: str                  # 人类可读标签
    boost: float                # 波源初始振幅倍率，默认 2.0
    propagation_boost: float    # 传播中增益倍率，默认 1.0（关）
    node_id: int | None         # reconcile 后绑定的节点；None = unresolved
```

---

## 3. 核心算法

### 3.1 文档分块（Parser）

```
输入：file_path: str
算法：
    1. 读取文件，按行扫描
    2. 识别 Markdown 标题（^#{1,6}\s+）
    3. 每遇到标题 → 提交当前块 + 开新块
    4. 维护标题栈（level → header），记录 path
    5. 基础块产出后：
       a. 长度 > 500 字符 → 按空行切割为子块，继承元数据
       b. 长度 < 50 字符 → 合并到上一块（除非是标题本身，标题独立保留）
    6. 输出 Chunk 列表
```

**边界**：
- 文件为空 → 返回 `[]`
- 无标题文件 → 整文档作为单一 path=("",) 的块
- 标题跨层级跳跃（H1 直接到 H3）→ path 按实际看到的填

### 3.2 向量化（Embedder）

- 模型：`BAAI/bge-small-zh-v1.5`，`sentence-transformers.SentenceTransformer`
- 归一化：`encode(normalize_embeddings=True)`，后续 `dot == cos`
- 批大小：默认 32；`encode_batch` 支持 `list[str]` 一次处理
- 缓存：M0 **不做** 查询 embedding 缓存，留到 M2
- 线程安全：`SentenceTransformer.encode` 内部 torch，OK 单进程多线程调用

### 3.3 图构建（GraphBuilder）

```
输入：chunks: list[Chunk], embeddings: np.ndarray[N, 384]
算法：
    1. 创建 nx.Graph()
    2. 为每个 chunk 添加节点（id = 顺序编号）
    3. 语义边：
       sims = embeddings @ embeddings.T        # O(N²)，N<10k 可接受
       mask = (sims > sim_threshold) & (上三角)
       对 mask 中每对 (i,j)：add_edge(i, j, weight=sims[i,j], kind="semantic")
    4. 结构边：
       - 父子：如果 chunk_j.path 是 chunk_i.path 的前缀扩展一层
               边权重 = min(1.0, existing + 0.2)
       - 兄弟：相同 parent path + 同 level
               边权重 = min(1.0, existing + 0.1)
       - 连续：chunk_i 与 chunk_{i+1}（原文相邻）
               边权重 = min(1.0, existing + 0.15)
    5. 合并规则：结构边叠加到既存语义边上（都是 Graph.add_edge 的 weight 字段），
       新边的 kind 取"奖励最大的那类"。
    6. 返回 graph
```

**复杂度**：O(N²) 语义 + O(N) 结构。1000 节点 ~ 10⁶ 次 dot，numpy 向量化下 <1s。

### 3.4 波扩散检索（WaveSearcher）

伪代码（与 PRD 中 `aggregate` / `propagation_boost` 参数对齐）：

```python
def wave_search(
    query_vec: np.ndarray,       # (384,) 归一化
    graph: nx.Graph,
    vectors: np.ndarray,         # (N, 384) 全部节点向量
    anchors: dict[int, Anchor],  # node_id -> Anchor
    top_k: int = 5,
    steps: int = 3,
    decay: float = 0.7,
    amplitude_cutoff: float = 0.01,
    aggregate: Literal["max", "sum"] = "max",
) -> list[Result]:
    # 1. 波源
    sims = vectors @ query_vec                    # (N,)
    source_ids = np.argpartition(-sims, 3)[:3]

    amplitudes = defaultdict(float)
    current_wave = {}
    for nid in source_ids:
        amp = sims[nid]
        if nid in anchors:
            amp *= anchors[nid].boost             # 波源 boost
        amplitudes[nid] = amp
        current_wave[nid] = amp

    # 2. 传播
    for _ in range(steps):
        next_wave = {}
        for nid, amp in current_wave.items():
            if amp < amplitude_cutoff:
                continue
            prop_amp = amp
            if nid in anchors:
                prop_amp *= anchors[nid].propagation_boost  # 默认 1.0
            for neighbor, attrs in graph[nid].items():
                new_amp = prop_amp * attrs["weight"] * decay
                if new_amp < amplitude_cutoff:
                    continue
                if aggregate == "max":
                    next_wave[neighbor] = max(next_wave.get(neighbor, 0.0), new_amp)
                else:  # sum
                    next_wave[neighbor] = next_wave.get(neighbor, 0.0) + new_amp

        # 干涉汇聚到全局 amplitudes
        for nid, amp in next_wave.items():
            if aggregate == "max":
                amplitudes[nid] = max(amplitudes[nid], amp)
            else:
                amplitudes[nid] += amp
        current_wave = next_wave

    # 3. 排序输出
    ranked = sorted(amplitudes.items(), key=lambda kv: -kv[1])[:top_k]
    return [make_result(nid, score, graph) for nid, score in ranked]
```

**性能预算**：steps=3, decay=0.7, N=1000，平均度 20 → 访问节点数 ≈ 3 × 20 × 20 = 1200，<20ms。

### 3.5 锚点 Reconcile

```
输入：old_anchors: list[Anchor], new_graph, new_vectors, embedder
算法：
    remapped, unresolved = [], []
    new_keys = {graph.nodes[i]["anchor_key"]: i for i in graph.nodes}

    for a in old_anchors:
        # Stage 1: anchor_key 精确匹配
        if a.anchor_key in new_keys:
            a.node_id = new_keys[a.anchor_key]
            remapped.append(a)
            continue

        # Stage 2: embedding 最近邻回退
        if a.node_id is None:  # 老锚点本身就 unresolved
            unresolved.append(a); continue

        # 拿老锚点对应的文本做 embedding（老文本存 Anchor.label 里? — 实际存 old_text 字段）
        # —— 为此，Anchor 还需要存 old_text 字段（见 §5 存储 schema）
        old_vec = embedder.encode_query(a.old_text)
        sims = new_vectors @ old_vec             # (N_new,)
        best = int(np.argmax(sims))
        if sims[best] >= 0.85:
            # 重新生成 anchor_key（基于新节点内容）
            new_key = compute_anchor_key(new_graph.nodes[best])
            a.anchor_key = new_key
            a.node_id = best
            remapped.append(a)
        else:
            a.node_id = None
            unresolved.append(a)

    return remapped, unresolved
```

**注**：`Anchor` 需要增加 `old_text: str` 字段（存创建时的文本快照），用于回退匹配。初次创建时 `old_text = graph.nodes[node_id]["text"]`。

---

## 4. AppState 并发模型（M0 单机 double-buffer）

### 4.1 状态对象

```python
@dataclass(frozen=True)
class GraphState:
    graph: nx.Graph
    vectors: np.ndarray          # (N, 384)
    anchors: dict[int, Anchor]   # node_id -> Anchor
    build_id: str                # UUID, 每次 rebuild 新生成
    built_at: datetime
    kb_name: str

class AppState:
    def __init__(self):
        self._current: GraphState | None = None
        self._current_lock = threading.Lock()       # 仅保护 _current 指针读写
        self._rebuild_lock = threading.Lock()       # 防止并发 rebuild
        self._rebuild_tasks: dict[str, RebuildTask] = {}  # task_id -> status

    def current(self) -> GraphState:
        with self._current_lock:
            if self._current is None:
                raise ServiceError("KB_NOT_LOADED")
            return self._current  # 返回引用，调用方不应长期持有

    def swap(self, new_state: GraphState) -> None:
        with self._current_lock:
            self._current = new_state
    ...
```

### 4.2 Rebuild 时序

```
Client                API(main loop)         RebuildWorker(thread)        AppState
  │   POST /rebuild       │                          │                       │
  │─────────────────────▶│                          │                       │
  │                       │  acquire _rebuild_lock   │                       │
  │                       │─────────────────────────▶│                       │
  │                       │  task_id = uuid4()       │                       │
  │                       │  spawn thread ───────────▶ parse docs            │
  │  202 {task_id}        │                          │ embed                 │
  │◀─────────────────────│                          │ build_graph           │
  │                       │                          │ reconcile anchors     │
  │                       │                          │ persist stores        │
  │                       │                          │ new_state = GraphState│
  │                       │                          │─── swap(new_state) ──▶│
  │                       │                          │ release _rebuild_lock │
  │                       │                          │                       │
  │   GET /rebuild/{id}   │                          │                       │
  │─────────────────────▶│ read _rebuild_tasks[id] │                       │
  │  {status:"done"}      │                          │                       │
  │◀─────────────────────│                          │                       │

期间的 /search 请求：
  Client ──▶ API ──▶ AppState.current() ──▶ 拿到旧 GraphState 引用
         ──▶ WaveSearcher(old_graph, old_vectors) ──▶ 正常响应
```

**失败处理**：worker 抛异常 → `_rebuild_tasks[task_id].status = "failed"` + error detail；`_current` 不变；`/search` 继续用旧图。

**并发 rebuild**：第二个 POST 发现 `_rebuild_lock` 已持（`acquire(blocking=False)`）→ 立即返回 `{code: "REBUILD_IN_PROGRESS"}`。

### 4.3 引用持有规则

`AppState.current()` 返回 `GraphState` 的引用。`/search` 的完整生命周期内持有同一引用（不允许中途再次 `current()`），这样即使 swap 发生，该请求也用一致的图完成。

实现：请求开始时 `state = app.current()`，之后所有操作基于 `state`，不再访问 `app.current()`。

### 4.4 启动路径

1. `serve` 命令启动 → `AppState()` 空
2. 从 `data/{kb}/` 加载 stores → 构造初始 `GraphState` → `app.swap(initial)`
3. FastAPI `lifespan` hook 完成后才对外服务（保证 `/search` 不会在未加载时收到）
4. `/health` = 进程存活；`/ready` = `app._current is not None`（M1 再真正实现 endpoint，M0 实现 getter 即可）

---

## 5. 存储 Schema

### 5.1 目录布局

```
data/
└── {kb_name}/                  # 默认 "default"
    ├── meta.json
    ├── graph.json
    ├── vectors.npz
    └── anchors.json
```

### 5.2 meta.json

```json
{
  "schema_version": 1,
  "kb_name": "default",
  "model_name": "BAAI/bge-small-zh-v1.5",
  "model_dim": 384,
  "built_at": "2026-05-11T10:30:00Z",
  "chunk_count": 142,
  "aggregate_default": "max",
  "sim_threshold": 0.5
}
```

加载时校验 `schema_version == 1`、`model_dim` 与当前 embedder 一致，否则拒绝加载。

### 5.3 graph.json

```json
{
  "nodes": [
    {
      "id": 0,
      "text": "...",
      "header": "蒸汽功能",
      "path": ["蒸汽功能"],
      "level": 2,
      "start_line": 45,
      "source_file": "coffee.md",
      "anchor_key": "a3f7b2c9d1e0"
    }
  ],
  "edges": [
    {"u": 0, "v": 3, "weight": 0.72, "kind": "semantic"},
    {"u": 0, "v": 1, "weight": 0.35, "kind": "parent_child"}
  ]
}
```

### 5.4 vectors.npz

```python
np.savez(
    path,
    ids=np.array([0, 1, 2, ...], dtype=np.int32),   # 与 graph.json nodes.id 对齐
    vecs=np.array([[...]], dtype=np.float32),        # (N, 384)
)
```

### 5.5 anchors.json

```json
{
  "anchors": [
    {
      "anchor_key": "a3f7b2c9d1e0",
      "label": "蒸汽故障E05",
      "boost": 2.0,
      "propagation_boost": 1.0,
      "node_id": 7,
      "old_text": "E05: 蒸汽管堵塞"
    }
  ],
  "unresolved": []
}
```

### 5.6 原子写工具

```python
def atomic_write(path: Path, write_fn: Callable[[Path], None]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp." + uuid4().hex[:8])
    try:
        write_fn(tmp)
        os.replace(tmp, path)  # POSIX 原子
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
```

所有 `*Store.save()` 都走这个。

---

## 6. 存储抽象接口（`storage/base.py`）

```python
from abc import ABC, abstractmethod

class GraphStore(ABC):
    @abstractmethod
    def save(self, graph: nx.Graph, path: Path) -> None: ...
    @abstractmethod
    def load(self, path: Path) -> nx.Graph: ...

    # M1+ 预留
    def add_nodes(self, nodes): raise NotImplementedError
    def remove_nodes(self, node_ids): raise NotImplementedError


class VectorStore(ABC):
    @abstractmethod
    def save(self, ids: np.ndarray, vecs: np.ndarray, path: Path) -> None: ...
    @abstractmethod
    def load(self, path: Path) -> tuple[np.ndarray, np.ndarray]: ...
    @abstractmethod
    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]: ...

    def delete(self, ids): raise NotImplementedError
    def update(self, ids, vecs): raise NotImplementedError


class AnchorStore(ABC):
    @abstractmethod
    def save(self, anchors: list[Anchor], path: Path) -> None: ...
    @abstractmethod
    def load(self, path: Path) -> list[Anchor]: ...
    @abstractmethod
    def reconcile(
        self, old_anchors, new_graph, new_vectors, embedder
    ) -> tuple[list[Anchor], list[Anchor]]: ...
```

---

## 7. API 契约

### 7.1 `POST /search`

请求：
```json
{
  "question": "蒸汽很小",
  "top_k": 5,
  "steps": 3,
  "decay": 0.7,
  "aggregate": "max",
  "kb_name": "default"
}
```

响应：
```json
{
  "query": "蒸汽很小",
  "build_id": "7f9a...",
  "results": [
    {"node_id": 3, "score": 0.83, "text": "...", "header": "蒸汽功能", "path": ["蒸汽功能"]}
  ],
  "search_time_ms": 12
}
```

### 7.2 `POST /rebuild`（异步）

请求：`{ "kb_name": "default", "docs_dir": "docs/" }`
响应：`202 { "task_id": "uuid", "status": "running" }`
或    `409 { "code": "REBUILD_IN_PROGRESS", "message": "...", "detail": {...} }`

### 7.3 `GET /rebuild/{task_id}`

响应：
```json
{"task_id": "uuid", "status": "running|done|failed", "started_at": "...",
 "finished_at": "...", "error": null, "unresolved_anchors": [...]}
```

### 7.4 锚点 CRUD

- `POST /anchor`：`{node_id, label, boost, propagation_boost}` → 服务端算 `anchor_key` 返回
- `DELETE /anchor/{anchor_key}`
- `GET /anchor` → `{anchors: [...], unresolved: [...]}`

### 7.5 `GET /graph_info`

```json
{"kb_name": "default", "build_id": "...", "chunk_count": 142,
 "edge_count": 537, "avg_degree": 7.6, "anchor_count": 12, "unresolved_count": 0}
```

### 7.6 统一错误格式

所有非 2xx：
```json
{"code": "REBUILD_FAILED", "message": "...", "detail": {"exception": "..."}}
```

错误码 M0 最小集：`KB_NOT_LOADED / REBUILD_IN_PROGRESS / REBUILD_FAILED / ANCHOR_NOT_FOUND / INVALID_INPUT / INTERNAL`

---

## 8. 配置文件

`config.yaml`（加载优先级：CLI --config > 默认 `./config.yaml`；环境变量 override 留 M1）

```yaml
model:
  name: BAAI/bge-small-zh-v1.5
  device: cpu
  batch_size: 32

graph:
  sim_threshold: 0.5
  parent_child_bonus: 0.2
  sibling_bonus: 0.1
  consecutive_bonus: 0.15

search:
  default_top_k: 5
  default_steps: 3
  default_decay: 0.7
  amplitude_cutoff: 0.01
  aggregate: max

anchor:
  default_boost: 2.0
  default_propagation_boost: 1.0
  reconcile_threshold: 0.85

storage:
  root: ./data
  schema_version: 1

server:
  host: 0.0.0.0
  port: 8000
```

---

## 9. 错误处理与可测性

- 所有公共函数在入参非法时抛 `ValueError`，服务层转 `INVALID_INPUT`
- `AppState` 未加载时抛自定义 `KbNotLoadedError`，转 `KB_NOT_LOADED`
- 测试友好：`WaveSearcher / GraphBuilder` 接受显式参数，不读全局 config；Config 只在 API/CLI 入口读一次
- 锚点 reconcile 失败不中断 rebuild，只进 unresolved 列表

---

## 10. 不做什么（重申）

- 不做 Docker / JSON 日志 / Prometheus（M1/M4）
- 不做 API key / 限流（M2）
- 不做 Eval 标注集（M3）
- 不做 Faiss / 增量更新实现（post-v1，接口已预留）
- 不做查询缓存（M2）
- 不做环境变量 override（M1）

---

## 附：字段可追溯性

| PRD 决策 | design.md 对应段 |
|----------|-----------------|
| max 聚合默认 | §3.4 `aggregate` 参数 |
| 锚点 anchor_key | §2.4 + §3.5 + §5.5 |
| 三层存储接口 | §6 + §5 |
| 锚点传播增益默认关 | §3.4 `propagation_boost` 默认 1.0 |
| 单机 double-buffer | §4 AppState |
| kb_name 预留 | §5.1 + §7 |
| 统一错误格式 | §7.6 |
| schema_version | §5.2 + §10 |
