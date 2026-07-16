# S4 API、数据、Prompt 与评测设计

## 1. Chat API

`POST /api/v1/chat/completions`

```json
{
  "conversation_id": "uuid",
  "message": "差旅住宿标准是什么？",
  "knowledge_base_ids": ["uuid"],
  "stream": true,
  "model_policy": "balanced",
  "response_mode": "grounded_answer",
  "client_context": {"locale": "zh-CN"}
}
```

字段约束：

| 字段 | 类型/约束 | 语义 |
|---|---|---|
| conversation_id | UUID，必填 | 必须属于当前用户和租户 |
| message | 1–8000 字符 | 去除首尾空白；普通日志不保存原文 |
| knowledge_base_ids | UUID[]，最多 10，唯一 | general 必须为空；知识模式至少 1 个 |
| stream | boolean | true 为 SSE；false 返回完整对象 |
| model_policy | fast/balanced/quality | 传给 S2 Gateway，不暴露 Provider |
| response_mode | general/grounded_answer/search_only | 决定是否检索和调用模型 |

同步响应新增 `message.response_mode`、`knowledge_base_ids`、`retrieval_run_id`、`prompt_version`、`abstention_reason` 和 `citations`；顶层 citations 与 message citations 一致。

## 2. SSE 事件

事件通用字段沿用 S2：`request_id`、`trace_id`、`message_id`、`sequence`、`timestamp`。S4 顺序：

```text
message.started
retrieval.completed   # 仅知识模式
usage                 # grounded Provider 可在验证前完成计量
message.delta         # grounded 内容已完成引用校验
citation              # 0..N
message.completed | error
```

`retrieval.completed` 公开安全聚合字段：`retrieval_run_id`、`config_version`、`status`、`abstention_reason`、候选/选中/注入移除计数。不得返回未授权标题或分数。

`citation` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| citation_id | UUID | 引用主键 |
| ordinal | integer ≥1 | 展示顺序 |
| source_id | `SRC-[0-9]{3}` | 回答内引用标记 |
| document_id/version_id | UUID | 受控溯源 ID |
| document_title/version | string/integer | 当时快照 |
| page_from/page_to | nullable integer | PDF 等页码来源 |
| section_path | string[] | 结构路径 |
| quote | ≤1200 chars | 已清理、受控预览 |
| relevance_score | 0..1 | 本次 final score |

## 3. Citation 与 Feedback API

`GET /api/v1/messages/{message_id}/citations/{citation_id}`：当前用户消息归属和当前文档 ACL 双重鉴权；200 返回 citation、`message_id`、`access_checked_at`、`source_url:null`；不可见一律安全 404。

`POST /api/v1/messages/{message_id}/feedback`：

```json
{"rating": -1, "reason_code": "factually_unsupported", "comment": "可选说明"}
```

rating 仅 `-1/1`；reason 为 helpful/incorrect/factually_unsupported/incorrect_citation/outdated/unsafe/other；comment 最长 2000。按 `(tenant_id,message_id,user_id)` upsert，响应带 snapshot 和 created/updated 时间。

## 4. S4 数据表

### rag_configs

| 字段 | 用途 |
|---|---|
| tenant_id/code/version/status | 每租户不可变发布配置；唯一 `(tenant,code,version)` |
| vector/lexical/rerank/final candidates | 各阶段硬上限 |
| rrf_k、weights | 融合版本参数 |
| context_max_tokens、min_relevance、min_query_coverage | 证据/预算门槛 |
| prompt_version/prompt_checksum/config_checksum | 配置与 Prompt 完整性 |
| created_at/published_at | 生命周期审计 |

已发布配置不原地修改；新参数发布新 version，run 引用具体 config ID。

### retrieval_runs

记录 tenant/user/conversation/message、response_mode、query_hash、KB IDs/classification snapshot、ACL fingerprint、config ID/version、embedding/reranker/prompt 版本、status、abstention_reason、metrics 和时间。禁止存 raw query/context。

### retrieval_hits

每个进入 rerank 集合的 hit 保存 document/version/chunk、vector/lexical/fusion/rerank/final 分数与 rank、selected/source_id、content hash/page/section 快照。唯一 `(run,chunk)`，便于确定性复盘。

### citations

唯一 `(message,source_id)` 与 `(message,ordinal)`；引用 retrieval run/hit/document/version/chunk，保存 title/version/page/section/quote/score/hash 和创建时间。引用为追加式快照，不随文档 current version 更新。

### message_feedback

唯一 `(tenant,message,user)`；保存 rating/reason/comment 和 `snapshot`。snapshot 包含 response mode、retrieval run/config/prompt/provider/model/KB/abstention 等，不复制完整敏感正文。

### messages 扩展

新增 response_mode、knowledge_base_ids、rag_config_id、retrieval_run_id、prompt_version、abstention_reason，使会话历史直接表达当时的回答策略。

### document_chunks 扩展

保留 JSON `embedding` 兼容迁移/测试，同时新增 PostgreSQL `embedding_vector VECTOR`。摄取同时写入；S4 Fake Embedding 标识为 `fake-embedding-v2/s4-v1`，旧本地数据需重建。

## 5. Prompt 版本

`grounded-prompt-s4-v1` 的规则文本和 checksum 进入 `rag_configs`。Prompt Context 使用 JSON 数组：

```json
{
  "query": "...",
  "sources": [{
    "source_id": "SRC-001",
    "title": "...",
    "version": 2,
    "page_from": 3,
    "section_path": ["差旅", "住宿"],
    "content": "..."
  }]
}
```

JSON 只是边界强化，不让文档变成可信指令。输出仍必须由代码校验 Source ID。

## 6. 配置与部署字段

| 环境变量 | 默认 | 说明 |
|---|---:|---|
| QA_RAG_ENABLED | true | 开启知识模式 |
| QA_RETRIEVAL_VECTOR_CANDIDATES | 20 | vector top-N |
| QA_RETRIEVAL_LEXICAL_CANDIDATES | 20 | FTS top-N |
| QA_RETRIEVAL_RERANK_CANDIDATES | 12 | rerank 上限 |
| QA_RETRIEVAL_FINAL_K | 5 | 最终 Source 上限 |
| QA_RETRIEVAL_RRF_K | 60 | RRF 常数 |
| QA_RETRIEVAL_CONTEXT_MAX_TOKENS | 1200 | 上下文预算 |
| QA_RETRIEVAL_MIN_RELEVANCE | 0.28 | 最低 final score |
| QA_RETRIEVAL_MIN_QUERY_COVERAGE | 0.34 | 最低查询词覆盖 |
| QA_CITATION_MAX_QUOTE_CHARS | 1200 | 引用 preview 上限 |
| QA_FAKE_RERANKER_ENABLED | local true | staging/production 禁止 |
| QA_RERANKER_PROVIDER_* | production required | HTTPS base/key/model |
| QA_RERANKER_TIMEOUT_SECONDS | 20 | 0.1–120 秒 |

生产 RAG 还强制 PostgreSQL、批准的 Reranker 和非 Fake Embedding/Model；Helm 只通过 Secret 引用 Key。

## 7. 评测协议

合成集 `s4-mini-golden-v1` 有 5 份文档、20 个问题：12 answerable、5 no-evidence（含无权限秘密文档）、3 direct-injection。脚本通过真实 FastAPI/DB/摄取/检索/生成/引用链路运行。

| 指标 | 计算 | S4 工程门槛 |
|---|---|---:|
| Recall@10 | answerable 中期望文档进入引用/检索证据 | ≥0.90（项目正式门槛仍 ≥0.85） |
| Citation precision | answerable citations 中期望文档比例 | ≥0.90 |
| Citation completeness | answerable 中至少一个 citation | ≥0.90 |
| Groundedness proxy | 有 citation、回答引用该 ID 且含期望事实 | ≥0.90 |
| Abstention precision/recall | no-evidence + unsafe 二分类 | 各 ≥0.90 |
| Unauthorized leakage | secret term 出现在回答/quote | 必须 0 |

这只是确定性工程回归。真实上线必须有业务双人复核集、claim-level 评估、人工误差分析、多语言/长文/表格/冲突/时效/攻击集，并按正式门槛计算置信区间。
