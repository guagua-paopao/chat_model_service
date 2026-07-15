# 10. 可观测性与运行手册

## 1. 可观测目标

运维人员应能在 10 分钟内回答：影响哪个租户/场景、从何时开始、是平台/检索/数据/模型/配额哪一层、用户影响多大、是否泄露/错误回答、当前成本、可以怎样安全降级或回滚。

采用 OpenTelemetry 统一 trace、metric、log 关联。生成式 AI 语义约定仍可能演进，落地时固定版本并经隐私评审；内部稳定字段不要直接追随实验字段频繁变化。

## 2. SLI/SLO 与错误预算

| SLI | 计算 | 月度目标 | 备注 |
|---|---|---:|---|
| API availability | 合格请求中非平台失败比例 | 99.9% | 用户 4xx/主动取消不算平台失败，错误分类需审计 |
| Successful stream | started 后 completed/cancelled 的比例 | 99.5% | error/孤儿流失败 |
| TTFT | 用户提交到首 token | P95 ≤ 2.5s | 同时报端到端与上游分段 |
| Complete latency | 提交到完成 | P95 ≤ 15s | 以基线问题长度分桶 |
| Retrieval latency | 检索+重排 | P95 ≤ 500ms（基线） | 真实规模压测校准 |
| Ingestion freshness | 文档完成上传到可检索 | P95 ≤ 10min | 50 MB 内普通文档 |
| Groundedness | 在线抽样/离线集 | ≥ 0.90 | 质量 SLO/产品门槛，不与可用性混为一谈 |
| ACL safety | 成功越权事件 | 0 | 安全硬门槛 |

错误预算用于平衡发布速度和可靠性：预算消耗过快时暂停高风险变更，优先修复可靠性。安全越权没有可消耗预算。

## 3. Trace 设计

建议 span：

```text
http.request
  auth.verify
  policy.authorize
  quota.reserve
  conversation.persist_user_message
  retrieval.run
    retrieval.vector
    retrieval.keyword
    retrieval.fuse
    rerank
    context.pack
  model.chat
    provider.attempt
  citation.validate
  conversation.persist_assistant_message
  usage.commit
```

Span 属性白名单：`request_id, tenant_hash/tier, operation, route_version, model, provider, kb_count, candidate_count, selected_count, cache_hit, input/output_tokens, error.type, retry_count`。不记录 API key、Authorization、完整问题/答案/文档、用户 email；`tenant_id/user_id/conversation_id` 是否记录原值由访问和隐私策略决定，默认哈希/仅日志受控字段。

采样：错误/高延迟/安全事件 100%，普通成功请求概率采样；tail sampling 需保证 trace 在决策前可关联。不能只采成功流造成故障不可见。

## 4. 结构化日志

公共字段：

```json
{
  "timestamp":"2026-07-15T02:15:10.123Z",
  "level":"INFO",
  "service":"qa-api",
  "environment":"production",
  "event":"chat.completed",
  "request_id":"...",
  "trace_id":"...",
  "tenant_ref":"hmac:...",
  "actor_type":"user",
  "resource_type":"message",
  "resource_id":"...",
  "result":"success",
  "duration_ms":2140,
  "model":"approved-model-alias",
  "input_tokens":1820,
  "output_tokens":210,
  "error_code":null
}
```

错误堆栈只进受控服务日志，不返回客户端；Provider 原始响应先脱敏。禁止把用户输入或文档正文拼入日志 message。日志 schema 版本化并在 CI 做敏感字段测试。

## 5. 指标目录

指标名使用低基数 label：`environment, service, operation, status_class, provider, model_alias, route_version, queue, stage`。禁止 `user_id, conversation_id, document_id, raw_tenant_id, question, error_message` 作为 label。

| 指标 | 类型 | 用途 |
|---|---|---|
| `qa_http_requests_total` | Counter | API 流量/状态 |
| `qa_http_request_duration_seconds` | Histogram | 端到端延迟 |
| `qa_chat_first_token_seconds` | Histogram | TTFT |
| `qa_chat_streams_active` | Gauge | SSE 并发 |
| `qa_model_requests_total` | Counter | provider/model/result |
| `qa_model_duration_seconds` | Histogram | 模型分段延迟 |
| `qa_model_tokens_total` | Counter | input/output/cached |
| `qa_model_cost_total` | Counter | 费用；财务以 usage ledger 为准 |
| `qa_retrieval_duration_seconds` | Histogram | 检索/重排 |
| `qa_retrieval_empty_total` | Counter | 空召回/拒答信号 |
| `qa_ingestion_jobs_total` | Counter | stage/result |
| `qa_ingestion_job_duration_seconds` | Histogram | 摄取耗时 |
| `qa_queue_depth` / `oldest_age_seconds` | Gauge | Worker 容量 |
| `qa_policy_denials_total` | Counter | 授权拒绝趋势，不含敏感资源 ID |
| `qa_quality_score` | Gauge/报告 | 固定数据集/版本的质量 |

成本 metric 便于近实时告警，但应对照追加式 `usage_ledger` 对账，处理延迟账单和估算 token。

## 6. 仪表盘

1. **Executive/Product**：活跃用户、问题数、任务完成/反馈、拒答、引用、单位成本、业务切片质量。
2. **SLO**：可用性、TTFT/总延迟、成功流、错误预算 burn rate、关键告警。
3. **Model Provider**：按 provider/model 的流量、429/5xx/超时、TTFT、fallback、token、成本、熔断状态。
4. **Retrieval/Quality**：空召回、候选/selected、score 分布、引用、拒答、黄金集版本对比。
5. **Ingestion**：队列深度/年龄、各 stage 吞吐/失败/耗时、文件类型、死信、Embedding 配额。
6. **Data/Platform**：DB 连接/慢查询/复制、Redis、对象错误、Pod/Node、CPU/内存、HPA。
7. **Security/Governance**：登录失败、授权拒绝、安全标签、上传拒绝、特权操作、审计导出、预算异常。

业务/安全仪表盘权限分离；默认不展示对话正文或原始用户身份。

## 7. 告警设计

| 告警 | 触发思路 | 严重度 | 自动动作 |
|---|---|---|---|
| SLO burn fast | 1h/5m 多窗口高 burn | SEV1/2 | 暂停发布，通知 on-call |
| Model provider failure | 5xx/timeout/429 高于动态/固定基线 | SEV2 | 合法时熔断/切备用 |
| No healthy route | 场景无符合数据政策的健康模型 | SEV1 | 拒答/只读降级 |
| Queue oldest age | 最老任务超过 freshness SLO | SEV2 | 扩 Worker/限上传 |
| Dead letters | 新增或持续增长 | SEV2/3 | 创建事件/人工重试评估 |
| DB saturation | 连接/CPU/锁/存储逼近保护线 | SEV1/2 | 限流、扩容、停止批任务 |
| Cost anomaly | 当日预测 > 预算或突增 | SEV2 | 限额/降级/调查 |
| ACL canary hit | 受控越权 canary 被返回 | SEV0/P0 | 关停检索/隔离/响应 |
| Quality regression | 关键切片低于门禁 | SEV2 | 阻止配置/知识发布 |
| Certificate/secret expiry | 剩余天数低于阈值 | SEV2/3 | 触发轮换流程 |

每个告警包含用户影响、Owner、Runbook、仪表盘、最近变更、抑制规则和关闭条件。避免仅按 CPU 80% 产生不可操作噪声。

## 8. Runbook：模型供应商故障

**症状**：`MODEL_TIMEOUT/429/5xx`、TTFT 上升、熔断。  
**诊断**：确认是单模型/单 region/全 provider；检查内部连接池、DNS/egress；关联供应商状态和最近 route 变更；比较 fallback。  
**处置**：停止重试风暴 → 熔断故障 route → 仅在数据政策/能力/质量批准时切备用 → 必要时进入检索结果/明确失败模式 → 通知业务。  
**恢复**：半开小流量探测 → 观察错误/质量/成本 → 分级恢复；对账重复/失败费用。  
**禁止**：临时把受限数据发到未批准供应商，或关闭 TLS/内容保护。

## 9. Runbook：摄取积压/失败

**诊断**：看 oldest age、stage、文件类型、Worker 资源、Provider Embedding 配额、死信与最近 Parser 版本。  
**处置**：暂停低优先级评测/大批量；按 stage 增加 Worker；限制新上传；对确定可重试错误批量重试；不可重试进入人工队列。  
**数据检查**：确认未发布 staged chunk 不可检索，重复任务没有 active 重复。  
**恢复**：逐步解除限流，观察队列斜率和成本，抽样新发布文档检索。

## 10. Runbook：疑似越权/数据泄露

1. 宣布 P0/SEV0，保存最小必要审计/trace/release/config 引用，限制访问。
2. 立即关闭相关知识库/检索路径/引用 URL 或租户，撤销 token/密钥；不要删除证据。
3. 确认影响租户、资源、时间窗、缓存/日志/模型供应商数据流。
4. 修复 Policy/缓存/索引/URL，并运行完整跨租户与 ACL 回归；必要时清缓存/重建索引。
5. 按企业事件和适用要求由授权负责人决定通知；恢复采用小流量和 canary。
6. 复盘把攻击/缺陷样本加入永久测试，修订威胁模型和控制。

## 11. Runbook：错误答案/质量下降

先区分：源文档错误、版本/ACL、解析、召回、重排、上下文截断、Prompt、模型变化、引用映射或 UI 渲染。使用 `message_id → release/config → retrieval hits → selected evidence → provider request → citation` 定位。修复优先级是源数据/权限/检索事实链，而不是立刻堆 Prompt。若影响高风险事实，先回滚配置/下线知识/强制拒答。

## 12. 容量与成本运营

每周查看：用户/问题增速、token/问题、上下文/输出分布、Provider 配额、SSE 峰值、DB/向量规模、队列到达/处理率、对象/log 增长、单位答案成本。每月用 P50/P95 和增长情景更新 3–6 个月容量。

保护线建议：DB/磁盘在扩容前保留 30%+；Provider 配额保留峰值余量；日志预算和采样有上限；队列以 oldest age 而非只看数量扩缩。配额/成本降级必须记录对质量和用户的影响。

## 13. 值班与复盘

SEV0（泄露/破坏性）、SEV1（广泛不可用/数据风险）、SEV2（显著部分影响）、SEV3（低影响）。每级定义响应/升级时间、指挥角色、业务/安全/供应商联系人和沟通模板。

无责复盘包含：影响、时间线、检测、根因/促成因素、哪些控制有效/失败、修复与预防项、Owner/截止日期、测试/Runbook 更新。复盘不以“操作员失误”结束，应找到系统为什么允许单点失误造成影响。

