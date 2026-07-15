# S0-06. 容量与成本基线

## 1. 方法

S0 不绑定厂商价格，而是固定业务量、token、数据和资源假设。接入模型时只填入批准的价格快照即可得到预算，避免把易变化的公开单价写死在架构中。

## 2. 三档情景

| 指标 | Pilot | Baseline | Growth |
|---|---:|---:|---:|
| 注册用户 | 200 | 2,000 | 10,000 |
| 月问题数 | 5,000 | 100,000 | 500,000 |
| 峰值查询 RPS | 5 | 50 | 200 |
| 活动 SSE | 20 | 200 | 800 |
| 文档数 | 10,000 | 100,000 | 500,000 |
| 向量 chunks | 300,000 | 5,000,000 | 25,000,000 |
| 月文档变更率 | 5% | 5% | 5% |

Baseline 是当前工程假设，不是业务承诺。

## 3. Token 假设

每个问题平均：系统/规则 700、历史 1,200、用户/改写 300、检索上下文 3,800，共 6,000 input tokens；平均输出 500 tokens。

| 情景 | 月 input tokens | 月 output tokens |
|---|---:|---:|
| Pilot | 30M | 2.5M |
| Baseline | 600M | 50M |
| Growth | 3,000M | 250M |

公式：

```text
ChatCost = InputTokens / 1M × P_input
         + OutputTokens / 1M × P_output
         + CachedTokens / 1M × P_cache（如适用）
```

其中 `P_*` 来自调用时不可变价格版本。按 fast/balanced/quality 路由分别计算，不用单一平均价掩盖高成本场景。

## 4. Embedding 假设

平均每份文档 15,000 tokens，初始总量：Pilot 150M、Baseline 1.5B、Growth 7.5B。按月 5% 内容变化时，月增量约 7.5M、75M、375M tokens。

```text
EmbeddingCost = ChangedDocumentTokens / 1M × P_embedding
```

内容 hash 不变不重复嵌入；模型/维度切换需要按全量重建单独预算。

## 5. 存储估算

按每 chunk 约 12 KB 估算正文、1536 维 float32 向量、元数据和索引开销：

| 情景 | 主数据估算 | 含副本/备份 3× 规划量 |
|---|---:|---:|
| Pilot | 3.6 GB | 11 GB |
| Baseline | 60 GB | 180 GB |
| Growth | 300 GB | 900 GB |

实际索引开销受 HNSW 参数、正文长度、MVCC、WAL 和备份策略影响，S3 前用真实数据压测校准。

## 6. 计算资源起点

| 组件 | Pilot 起点 | Baseline 起点 | 扩缩信号 |
|---|---|---|---|
| Web | 2×0.25 vCPU/512MB | 2–3×0.5/1GB | RPS/CPU |
| API | 2×1 vCPU/2GB | 3×2/4GB | RPS、TTFT、活动 SSE |
| Parse Worker | 1×2/4GB | 2×2/4GB | parse queue oldest age |
| Embed Worker | 1×1/2GB | 2×2/4GB | embed queue/Provider quota |
| PostgreSQL | 2 vCPU/8GB | 8 vCPU/32GB 起测 | CPU、IOPS、连接、P95 |
| Redis | 1–2GB | 4–8GB | 内存、延迟、队列 |

这只是压测起点，不是生产 sizing。生产数据库、Redis 和对象存储优先托管高可用服务。

## 7. 平台成本项

- Web/API/Worker/Scheduler 计算与负载均衡。
- PostgreSQL/pgvector、只读/高可用、存储、IOPS、PITR。
- Redis、对象存储、版本/备份、跨区/出网。
- 模型 Chat/Embedding/Rerank/OCR。
- 日志、指标、Trace、SIEM 和长期审计归档。
- WAF、KMS/Secret、镜像仓库、安全扫描和域名/TLS。
- 人力、供应商支持、漏洞/升级和 20% 风险缓冲。

## 8. 预算保护

- 单问题 input/output token 上限和最大检索上下文。
- 用户/租户日月 token、金额、并发和请求配额。
- Provider 独立并发池、429 退避、熔断和最大 fallback 次数。
- 预算达到 70/85/100% 时预警、限制高成本路由或阻断新请求。
- 成本指标用于近实时告警，最终以追加式 usage ledger/账单对账。

## 9. 待确认输入

真实月/峰值流量、文档规模与变更、平均问题/回答长度、供应商精确价格/区域、可用性与 DR 目标、日志保留和预算上限。确认后生成 `capacity-baseline-v2`，不覆盖本版本。

