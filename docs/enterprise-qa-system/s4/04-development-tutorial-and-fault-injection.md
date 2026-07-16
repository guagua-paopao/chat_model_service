# S4 开发教学与故障注入

## 1. 学习目标

完成本阶段后，开发者应能解释：为什么 ACL 必须在 Top-K 前；为什么向量分数和 FTS 分数不能直接相加；为什么“Prompt 里要求引用”不足以防伪造；为什么 RAG 流式输出需要新的可见性边界；怎样用离线金标驱动阈值变更。

## 2. 从零实现顺序

1. **冻结契约和 threat cases**：先写 response mode、SSE、citation、feedback 与越权/注入/拒答测试。
2. **迁移数据模型**：启用 `vector` extension，增加 vector 列、RAG config/run/hit/citation/feedback 和 message 快照。
3. **实现纯函数**：tokenize、cosine、weighted RRF、reranker、Source ID 提取；先用小样例测试 tie-break。
4. **实现安全候选 SQL**：把 tenant/current/published/active/deleted/KB/ACL 写入 vector 与 FTS 两个分支。
5. **实现 context packing**：去重、相邻合并、预算、Source ID 与不可信句子移除。
6. **接入 Chat**：知识模式先 retrieval；拒答/search-only 走零模型账本；grounded 模型输出先缓冲。
7. **引用落库与再鉴权**：只有校验过的 Source ID 可建 citation；详情 endpoint 重新检查当前 ACL。
8. **Web/BFF**：白名单新增 citation/feedback；UI 明确区分检索、拒答、安全、失败。
9. **评测再调参**：固定集、跑基线、检查单例失败、通过 ADR/决策日志记录参数变化。
10. **PostgreSQL/容器验证**：SQLite 通过不等于 pgvector SQL 正确，必须在隔离 Compose 项目验证。

## 3. 本地运行

```powershell
Copy-Item .env.example .env
# 修改所有 CHANGE_ME。本地仅使用合成或获批非敏感文件。
docker compose -f infra/compose/compose.yaml up -d --build
.\.venv\Scripts\python.exe scripts\smoke_s4.py
```

浏览器打开 `http://127.0.0.1:3000`：登录 → 新建知识库 → 上传 MD/TXT/PDF/DOCX → 等待 completed → 选择“知识回答”或“仅检索” → 点击引用查看受控预览 → 提交反馈。

不使用 Docker 时：

```powershell
.\.venv\Scripts\alembic.exe -c apps/api/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn qa_api.main:app --app-dir apps/api/src --reload
.\.venv\Scripts\python.exe scripts/evaluate_s4.py
```

## 4. 请求示例

```powershell
$token = & .\.venv\Scripts\python.exe apps\api\scripts\issue_dev_token.py demo
$headers = @{Authorization="Bearer $token"; "Content-Type"="application/json"}
$body = @{
  conversation_id = "<conversation-uuid>"
  message = "What is the Shanghai hotel cap?"
  knowledge_base_ids = @("<kb-uuid>")
  stream = $false
  model_policy = "balanced"
  response_mode = "grounded_answer"
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/v1/chat/completions -Method Post -Headers $headers -Body $body
```

## 5. 数据库复盘

```sql
SELECT id, status, abstention_reason, config_version, query_hash, metrics
FROM retrieval_runs ORDER BY created_at DESC LIMIT 5;

SELECT final_rank, source_id, selected, vector_score, lexical_score,
       fusion_score, rerank_score, final_score, document_title_snapshot
FROM retrieval_hits WHERE retrieval_run_id = :run_id ORDER BY final_rank;

SELECT source_id, document_title_snapshot, version_no_snapshot, quote, relevance_score
FROM citations WHERE message_id = :message_id ORDER BY ordinal;
```

不要在支持工单或普通日志粘贴 raw query、context、Provider body 或受限 quote。

## 6. 故障注入实验

| 实验 | 操作 | 期望 |
|---|---|---|
| 无证据 | 问菜单/天气 | `abstained`，无 citation，ModelInvocation 不增加 |
| 直接注入 | `Ignore previous instructions...` | `unsafe_query`，零模型调用 |
| 间接注入 | 文档加入 reveal system prompt 句子 | metrics 计数增加，回答不包含该命令 |
| 伪造引用 | Fake 问题带 `[bad-citation]` | 模型给 `SRC-999`，API 丢弃原回答并拒答 |
| Reranker 超时 | MockTransport 抛 ReadTimeout | `RERANKER_TIMEOUT`、retryable、安全 error |
| Reranker 协议坏 | 缺 index/重复/越界/分数 >1 | `RERANKER_PROTOCOL_ERROR`，fail closed |
| ACL 撤销 | 先问答，再删除 document ACL，再 GET citation | 安全 404；恢复后同 citation 可见 |
| 跨租户 KB | 传其他 tenant 的 KB ID | 404，无 hit、标题或存在性泄漏 |
| search-only | 请求 search_only 并检查 invocation 表 | 返回 citations，模型调用计数不变 |
| migration 回退 | `downgrade 20260716_0003` 再 upgrade head | S4 表/列可逆，S3 数据表保留 |

## 7. 阈值实验方法

首轮评测中“Where can employees park bicycles?” 只因泛词 `employees` 命中制度文档，20% coverage 产生误答。修复不是删除该 case，而是：保留失败证据 → 将默认 coverage 改为 34% → 复跑全部 20 case → 确认 answerable recall 未下降。真实数据调参同样必须在固定 train/dev/test 划分上进行，禁止对 test 集逐题过拟合。

## 8. 调试顺序

1. 先用 `retrieval_run.status/abstention_reason/metrics` 判断是安全、证据还是系统失败。
2. 检查 config ID/version 和 embedding/reranker model code，避免比较不同模型产生的向量。
3. 检查 hit 的 vector/lexical/fusion/rerank/final rank，定位召回还是排序问题。
4. 检查 selected/source_id/packing 预算，再检查模型是否引用有效 ID。
5. 最后才调整阈值；所有改变写新配置版本和离线评测结果。

## 9. 生产前不可跳过

企业 OIDC/group/SCIM、真实文档审批、批准的 Chat/Embedding/Rerank、中文 tokenizer、固定维度 ANN benchmark、claim-level evaluator、red-team、共享 Redis 配额/取消、目标负载、Kubernetes/NetworkPolicy/Secret/TLS、备份恢复与 SLO 证据未完成前，不得把本教程的 local/Compose 成功解释为生产许可。
