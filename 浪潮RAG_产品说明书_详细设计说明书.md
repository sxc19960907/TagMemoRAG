# 🌊 浪潮RAG for 产品说明书 — 详细设计说明书

**版本**: v1.0
**编制日期**: 2026-05-10
**交付对象**: Claude / 开发团队

---

## 1. 概述

### 1.1 背景与目标

产品说明书（如家电、医疗器械、工业设备说明书）的知识特点是：
- 知识分章节（安装→操作→维护→故障排查）
- 用户提问口语化（"滴滴响"、"不转了"）
- 问题常跨章节（故障现象涉及操作步骤+维护+警告）

**目标**：构建一个轻量级、可离线部署的语义检索引擎，接受模糊口语查询，返回跨章节融合的精准知识块。

### 1.2 核心创新

采用 **浪潮检索算法（WAVE-RAG）**，核心思想：
- **语义拓扑图**：用节点（知识块）+ 边（语义/结构关联）组织知识
- **波扩散检索**：将用户查询作为波源，沿拓扑图传播能量（振幅），干涉汇聚后取Top-K
- **联想锚定**：手动标记关键概念作为锚点，改变语义引力

---

## 2. 系统架构

```
+----------------+    +-------------------+    +----------------+
|   用户界面     | --> |  REST API服务     | --> |  浪潮检索引擎  |
| (CLI/Web/API)  |    |    (FastAPI)      |    |    (Python)    |
+----------------+    +-------------------+    +-------+--------+
                                                      |
                                         +---------+---------+
                                         |                   |
                                  +------------+     +-------------+
                                  | 语义拓扑图 |     | 联想锚定系统 |
                                  | (NetworkX) |     | (锚点增益)   |
                                  +------------+     +-------------+
                                         |
                               +----------+----------+
                               |                     |
                         +------------+        +------------+
                         | 文档分块器 |        | 向量化引擎 |
                         | (Markdown/ |        | (BGE-small)|
                         |    PDF)    |        |            |
                         +------------+        +------------+
```

### 2.1 数据流

```
说明书原文 → 分块 → 向量化 → 构建拓扑图 → 保存图文件
用户查询 → 向量化 → 初始化波源 → 波扩散 → 排序输出Top-K
```

---

## 3. 核心模块详细设计

### 3.1 文档分块器（Document Parser）

**输入**：产品说明书的 Markdown / TXT / PDF（PDF需先转TXT）
**输出**：语义块列表 `List[dict{text, header, level, meta}]`

**分块策略**：
- **基础分块**：按标题层级（`#`, `##`, `###`）分割。每个标题及其紧随的文本为一个基本块。
- **长度裁剪**：若块长度 > 500 字符，按段落（空行）切割；若块长度 < 50 字符，合并到上一个块。
- **元数据保留**：每个块保存其所属的标题路径（如 `安装 > 电源连接`），层级深度，以及块在原文的起始行号（用于溯源）。

**接口设计**：
```python
def parse_document(file_path: str) -> List[Chunk]:
    """
    :param file_path: 支持 .md / .txt / .pdf (自动识别)
    :return: 每个 Chunk 包含 text, header, level, path
    """
```

### 3.2 向量化引擎（Embedder）

**模型选择**：`BAAI/bge-small-zh-v1.5` (384维，支持中文，仅CPU即可运行)
**配置**：归一化输出向量（便于后续内积=余弦）

**接口**：
```python
def encode_batch(texts: List[str]) -> np.ndarray:
    """返回 (N, 384) 的归一化嵌入矩阵"""

def encode_query(query: str) -> np.ndarray:
    """返回 (384,) 归一化查询向量"""
```

### 3.3 语义拓扑图构建器（Graph Builder）

**核心数据结构**：NetworkX 无向图 `G`

**节点属性**：
- `text`: 块文本
- `embedding`: 384维向量（list格式）
- `header`: 所属标题
- `level`: 标题层级
- `path`: 标题路径（如 `["安装", "电源连接"]`）

**边建立规则（两个层次）**：

1. **语义边**：计算任意两节点嵌入的余弦相似度，若 > 阈值（默认0.5），建立边，权重 = 相似度值。
   ```python
   for i, j in combinations(range(N), 2):
       sim = dot(emb[i], emb[j])
       if sim > SIM_THRESHOLD:
           G.add_edge(i, j, weight=sim)
   ```

2. **结构边**：基于文档原生结构强制加边
   - **父子边**：同一条父子路径的节点（如 `安装` → `安装/电源连接`），边权重+0.2
   - **兄弟边**：同一父标题下的相邻子节点（如 `安装/步骤1` ↔ `安装/步骤2`），边权重+0.1
   - **连续块边**：原文中相邻的块（即使标题跨层），边权重+0.15

**最终权重** = 语义相似度 + 结构奖励（上限1.0）

**构建接口**：
```python
def build_graph(chunks: List[Chunk], sim_threshold=0.5) -> nx.Graph:
    """返回完整的语义拓扑图"""
```

**优化建议**：十万级节点时，用 Faiss 近似最近邻代替全量计算语义边（阈值以上成对计算），但第一阶段数据集<1万节点时直接全量即可。

### 3.4 波扩散检索引擎（Wave Searcher）

这是系统的核心算法。步骤分解：

#### 3.4.1 初始化波源
- 计算查询向量与所有节点的余弦相似度
- 取 Top-3 最相似节点作为波源
- 每个波源的初始振幅 = 相似度值（0~1）

#### 3.4.2 波传播
- **参数**：
  - `steps`（传播步数）：默认 3，控制跨章节深度
  - `decay`（衰减系数）：默认 0.7，每步振幅乘此系数再乘边权重
  - `amplitude_cutoff`（振幅截断）：0.01 以下忽略，加速传播
- **每步传播规则**：
  - 从当前活跃节点出发，沿所有边传播到邻居
  - 新振幅 = 当前振幅 × 边权重 × decay
  - 每个节点的**总振幅累加**（多源干涉取最大值，或求和？此处使用取最大值，避免过度膨胀）
  - 本轮传播完毕，更新活跃节点集

#### 3.4.3 干涉汇聚
- 多波源传播到达同一节点时，取所有到达波中的最大振幅作为该节点的最终振幅（保证不重复叠加噪声）
- 亦可实验采用**求和**方式（对强关联信号更敏感），但需调整截断阈值

#### 3.4.4 结果排序与输出
- 按最终振幅降序排列
- 返回 Top-K（默认5）个节点，包含：节点ID、文本、标题路径、振幅

**接口**：
```python
def wave_search(query: str, graph: nx.Graph, top_k=5, steps=3, decay=0.7) -> List[Result]:
    """
    Result: {
        node_id: int,
        text: str,
        header: str,
        score: float
    }
    """
```

### 3.5 联想锚定系统（Anchor System）

允许管理员手动标记某些节点为概念锚点。锚点具有以下特性：
- 节点上存储 `anchor_label` 和 `boost`（增益倍率，默认×2）
- 在波源初始化阶段，若波源节点是锚点，其初期振幅乘以 boost
- 在传播过程中，锚点节点被激活时，其传播振幅也乘以 boost（可选）

**接口**：
```python
def set_anchor(node_id: int, label: str, boost=2.0):
    """设置锚点"""

def clear_anchor(node_id: int):
    """移除锚点"""

def list_anchors() -> List[dict]:
    """列出所有锚点"""
```

应用场景示例：
- 将 `安全警告`、`紧急操作` 节点设为锚点，用户在输入"注意"类查询时自动优先召回
- 将 `故障代码E05` 设为锚点，用户输入"E05"、"堵了"、"蒸汽小"都会高权重关联

---

## 4. API 接口设计

### 4.1 查询接口 `POST /search`

**请求体**：
```json
{
    "question": "咖啡机蒸汽很小",
    "top_k": 5,
    "steps": 3,
    "decay": 0.7
}
```

**响应体**：
```json
{
    "query": "咖啡机蒸汽很小",
    "results": [
        {
            "score": 0.8321,
            "text": "旋转蒸汽旋钮调节大小",
            "header": "蒸汽功能",
            "path": ["蒸汽功能"],
            "node_id": 3
        },
        {
            "score": 0.6543,
            "text": "E05: 蒸汽管堵塞",
            "header": "故障代码",
            "path": ["故障代码"],
            "node_id": 7
        },
        {
            "score": 0.5127,
            "text": "每周清洗蒸汽管",
            "header": "维护与清洁",
            "path": ["维护与清洁"],
            "node_id": 5
        }
    ],
    "search_time_ms": 12
}
```

### 4.2 锚点管理接口

- `POST /anchor` : 设置锚点（参数：`node_id`, `label`, `boost`）
- `DELETE /anchor` : 移除锚点（参数：`node_id`）
- `GET /anchor` : 列出所有锚点

### 4.3 系统状态接口

- `GET /graph_info` : 返回图节点数、边数、平均度数
- `POST /rebuild` : 重新加载文档并重建图（耗时操作）

---

## 5. 部署与运行

### 5.1 环境要求

- Python 3.10+
- 依赖：`fastapi uvicorn networkx numpy sentence-transformers pymupdf python-multipart`（约300MB安装空间）
- 硬件：CPU 2核，内存 4GB（可处理万级节点图）

### 5.2 启动步骤

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 准备说明书（放入 docs/ 目录）
# 3. 构建图
python build_graph.py --docs docs/ --output graph.pkl

# 4. 启动服务
python run_server.py --graph graph.pkl --port 8000
```

### 5.3 配置文件 `config.yaml`

```yaml
model:
    name: BAAI/bge-small-zh-v1.5
    device: cpu

graph:
    sim_threshold: 0.5
    store_path: graph.pkl

search:
    default_top_k: 5
    default_steps: 3
    default_decay: 0.7
    amplitude_cutoff: 0.01
```

---

## 6. 测试与验证

### 6.1 单元测试覆盖

| 模块 | 测试内容 |
|------|----------|
| DocumentParser | 正确按标题切分，超长块分割，合并短块 |
| GraphBuilder | 边构建正确，同章节节点有额外权重 |
| WaveSearcher | 模糊输入能召回正确章节，跨章节有效，参数敏感性 |
| AnchorSystem | 锚点增益生效，清除后恢复 |

### 6.2 端到端测试用例

| 输入 | 期望召回 |
|------|----------|
| "蒸汽很小" | 蒸汽功能 + 故障E05 + 清洗说明 |
| "滴滴响" | 报警音说明(若有) + 相关故障码 |
| "不出咖啡" | 制作咖啡步骤 + 故障E01(缺水) |
| "换滤芯后漏水" | 滤芯更换 + 漏水排查 |

### 6.3 性能基准

- **图构建**：1000个节点，全量计算约2秒（CPU）
- **单次检索**：3步传播，平均8ms（1000节点）
- **每增加1000节点**，构建时间约增加1.5倍；检索时间线性增加（边数增多）

---

## 7. 扩展方向（后续版本）

1. **多模态支持**：替换嵌入模型为 `BAAI/bge-m3` 或 `CLIP`，支持图文混合检索
2. **增量更新**：新文档只需计算与现有节点的相似边，局部插入，无需全量重建
3. **会话上下文**：维护对话状态，将前一轮波源作为下一轮的初始偏置，实现多轮导航
4. **可视化管理UI**：基于 `pyvis` 或 `d3.js` 展示拓扑图，支持拖拽锚点
5. **反馈学习**：用户点击结果可反馈正/负信号，微调边权重（相当于人工强化）

---

## 8. 附录：波扩散伪代码

```python
function wave_search(query, G, top_k=5, steps=3, decay=0.7):
    # 1. 波源初始化
    q_emb = embed(query)
    embs = [node.embedding for node in G.nodes]
    sims = dot(q_emb, embs)
    sources = top_k_indices(sims, 3)  # 取最相似3个

    amplitudes = dict(all_nodes, default=0.0)
    for node_id in sources:
        amplitudes[node_id] = sims[node_id]

    current_wave = {node_id: sims[node_id] for node_id in sources}

    # 2. 波传播
    for step in range(steps):
        next_wave = {}
        for node_id, amp in current_wave.items():
            if amp < 0.01: continue
            for neighbor, edge_weight in G.edges(node_id).items():
                new_amp = amp * edge_weight * decay
                if new_amp < 0.01: continue
                # 干涉叠加（取多来源最大值）
                if neighbor not in next_wave or new_amp > next_wave[neighbor]:
                    next_wave[neighbor] = new_amp
        for node_id, amp in next_wave.items():
            amplitudes[node_id] = max(amplitudes[node_id], amp)
        current_wave = next_wave

    # 3. 排序输出
    sorted_results = sort(amplitudes.items(), by=score, descending=True)
    return sorted_results[:top_k]
```
