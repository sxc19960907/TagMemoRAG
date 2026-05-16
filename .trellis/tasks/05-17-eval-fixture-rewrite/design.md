# Technical Design — Phase A: coffee.jsonl 重标注

> 父文档：[prd.md](./prd.md)
> Phase B（剩 7 套）单独建任务时设计仿此模板。

## 1. 数据流

```
coffee.jsonl (input)
    │
    ▼
relabel_eval_fixture.py  ──── for each query:
    │                            ├─ wave_search(hashing) → top-K node_ids
    │                            ├─ wave_search(siliconflow + Qwen-VL) → top-K node_ids
    │                            ├─ extra-candidates (manual override, optional)
    │                            └─ union & dedupe → ProposalRecord
    │
    ▼
research/coffee-proposals.jsonl  ── one ProposalRecord per query
    │
    ▼
[Claude session 内对话作 LLM]  ── 我对每个候选给出 relevant/borderline/not_relevant + 理由
    │
    ▼
research/coffee-review.md  ── 你 review 决策（可推翻 AI 建议）
    │
    ▼
[手动落地 fixture]
    │
    ├─→ coffee.jsonl 改 (扩 relevant + 删 min_*)
    ├─→ build_eval_baseline --embedder hashing  → hashing.json 重 capture
    ├─→ build_eval_baseline --embedder siliconflow  → siliconflow.json 重 capture
    └─→ pytest + run_eval_ci ×2 验收
```

## 2. 数据契约

### 2.1 ProposalRecord (relabel_eval_fixture 输出，per query)

```json
{
  "case_id": "coffee-steam-weak",
  "query": "蒸汽很小怎么办",
  "kb_name": "default",
  "current_relevant": [
    {"source_file": "...", "header": "...", "text_contains": [...]}
  ],
  "candidates": [
    {
      "source": "hashing|siliconflow|extra",
      "rank_in_source": 1,
      "node_id": 7,
      "source_file": "coffee_machine.md",
      "header": "蒸汽功能",
      "text_excerpt": "首50字...",
      "tags": ["coffee", "steam"]
    }
  ],
  "ai_suggestion": null
}
```

`ai_suggestion` 由后续 LLM 调用 / 我对话填入；脚本本身只生成结构化候选。

### 2.2 Review 决策记录 (coffee-review.md, per query)

```markdown
### coffee-steam-weak — "蒸汽很小怎么办"

**当前 relevant**：
- coffee_machine.md / 蒸汽功能 / ["蒸汽很小", "喷嘴"]
- coffee_machine.md / 喷嘴清洗 / ["喷嘴堵塞", "蒸汽变小"]

**候选清单（hashing ∪ siliconflow ∪ extra）**：
1. [hashing#1, sf#3] coffee_machine.md / 蒸汽功能 — "...蒸汽很小..."
2. [hashing#2] coffee_machine.md / 喷嘴清洗 — "...喷嘴堵塞..."
3. [sf#1] coffee_machine.md / 故障 E05 — "...E05 蒸汽管路..."
4. ...

**AI 建议**：
- #1 relevant - 直接命中关键字
- #2 relevant - 维护章节同主题
- #3 relevant - E05 故障与蒸汽弱密切相关
- #4 not_relevant - ...

**人工决定**：
- 加入 relevant：#3 (E05 故障 — 同主题不同 header，扩展覆盖)
- 保留：#1, #2
- 不加：#4 (虽然提及蒸汽，但是关于温度调节)
- 阈值：删除全部 min_*

**理由**：D1/D2 决议 — 多 header 同主题答案应全部进 relevant。
```

### 2.3 fixture jsonl 修改 (coffee.jsonl)

每条 query 的修改规则：
- `relevant` 数组：扩展为 review 决策的 union；保留 `text_contains` 严格性。
- `min_recall_at_k` / `min_mrr` / `min_hit_at_k` / `min_precision_at_k`：全部删除（D3）。
- `top_k_override`：保留（这是 query 自身行为，与 fixture 标注无关）。
- `negatives`：仅在 review 明确标 `not_relevant_and_should_not_appear` 时新增。
- 整条删除：dropped 决定（D6.g）。

## 3. relabel_eval_fixture.py 关键设计

### 3.1 双 embedder 召回

复用 build_kb 接口分别构建 hashing-KB 和 siliconflow-KB（tempdir 隔离），分别跑 wave_search top-K：

```python
# 伪代码
hashing_state = build_kb(docs, "default", _hashing_cfg(tmp1))
siliconflow_state = build_kb(docs, "default", _siliconflow_cfg(tmp2))

for case in load_eval_suite("coffee.jsonl"):
    query_vec_h = hashing_embedder.encode_query(case.query)
    hashing_results = wave_search(query_vec_h, hashing_state.graph, ..., top_k=10)

    query_vec_s = siliconflow_embedder.encode_query(case.query)  # via _with_retry
    siliconflow_results = wave_search(query_vec_s, siliconflow_state.graph, ..., top_k=10)

    candidates = _dedupe_union(hashing_results, siliconflow_results, extra=args.extra)
    write_proposal_record(case, candidates)
```

### 3.2 抗抖

调 siliconflow encoder 的 `encode_query` 包一层 `build_eval_baseline._with_retry`（D6.h）。
KB 构建本身（一次性 embed manuals）也包 retry。

### 3.3 第三层兜底

`--extra-candidates "coffee_machine.md:故障E05,coffee_machine.md:维护周期"` 让你能手动加入候选（D6.f）。

## 4. AI 建议生成 (Phase A 在 Claude session 内)

Phase A 不外调 LLM API：

- relabel 脚本只生成结构化候选清单（json）。
- 你把候选清单粘贴给我，我对每条候选给 `relevant/borderline/not_relevant + 1 句理由`。
- 我直接更新 `coffee-review.md` 草稿。
- 你在 review.md 内推翻或确认我的建议。

Phase B 量大时再考虑外部 LLM（决定不在本任务内做）。

## 5. 验收脚本

```bash
# 1. fixture 改完，重 capture
python scripts/build_eval_baseline.py --embedder hashing \
  --output tests/fixtures/eval/baselines/hashing.json \
  --compare-with .trellis/tasks/05-17-eval-fixture-rewrite/research/hashing-pre-rewrite-snapshot.json

# 2. siliconflow capture
python scripts/build_eval_baseline.py --embedder siliconflow \
  --output tests/fixtures/eval/baselines/siliconflow.json \
  --compare-with .trellis/tasks/05-17-eval-fixture-rewrite/research/siliconflow-pre-rewrite-snapshot.json

# 3. 三条验收
python -m pytest tests/ -q
python scripts/run_eval_ci.py
python scripts/run_eval_ci.py --baseline tests/fixtures/eval/baselines/siliconflow.json \
  --embedder siliconflow --no-default-thresholds
```

## 6. 兼容性 / 回滚

- **不改 src/**：`matching.py / dataset.py / runner.py` 不动。
- **改了 fixture 就要重 capture baseline**（D6）；忘记会让 CI 直接红（config_hash 不匹配）。
- **回滚**：git revert 单 commit，coffee.jsonl + 双 baseline 一起回到上一版。
- **失败检测**：D6 sanity check 是 fixture 写飞了的 canary（hashing 任意 metric 跌 >0.05）。

## 7. 不在本设计中（Phase B / 后续）

- 7 套剩余 suite 的批量化（cross_kb_negatives / fault_codes 等）。
- AI 建议外部 LLM API。
- diag 脚本同步（diag 不读 eval/*.jsonl）。
