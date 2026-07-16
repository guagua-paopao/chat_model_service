# S4 风险与开放项

## 1. 生产阻断项

| ID | 风险/缺口 | 当前控制 | Owner | 关闭证据 |
|---|---|---|---|---|
| R-S4-01 | 合成 20 条集不能代表业务 | 固定工程回归集并明示限制 | Product/QA | 业务双人复核、独立 test set、误差报告 |
| R-S4-02 | `simple` FTS 中文分词弱 | vector + lexical 双路、拒答 | Search/DBA | 批准 tokenizer/字典与中文 Recall benchmark |
| R-S4-03 | 无 ANN/容量证据 | 精确 pgvector、候选上限 | DBA/SRE | 固定维度 HNSW/IVFFlat recall-latency-cost 报告 |
| R-S4-04 | Fake Reranker/Model 不代表供应商 | production fail-fast | AI Platform/Security | Provider、区域、DPA、模型卡、回归和故障测试 |
| R-S4-05 | Source ID 不能验证每个 claim | valid-ID fail closed、引用快照 | AI/QA | claim-level evaluator + 人工抽检 + 对抗集 |
| R-S4-06 | 注入过滤为启发式 | context data boundary、redaction、buffer | Security | parser sandbox、red-team、模型安全评估、监控 |
| R-S4-07 | confidential Chat 路由审批未闭环 | external embedding/reranker 分类阻断 | Data Owner/Security | classification-aware model policy 与书面批准 |
| R-S4-08 | 共享配额/取消仍为进程内 | 单副本开发限制 | Platform | Redis 原子配额、取消、断线/多副本压测 |
| R-S4-09 | citation 仅受控 preview | 无 raw URL、每次 ACL | Product/Security | 原文定位 UX、短期授权 URL、下载审计与渗透测试 |
| R-S4-10 | Web conversation detail N+1 citation | 小规模 MVP | API | batched query、查询计划和 P95 证据 |
| R-S4-11 | RAG 配置无双人发布工作流 | immutable seed config | Product/Platform | 管理 API/UI、审批、回滚演练、RBAC |
| R-S4-12 | 无安全 semantic cache | 明确禁用 | Architecture/Security | ACL/version/config key、失效和侧信道证明 |
| R-S4-13 | 真实身份/Group/SCIM 未接 | user/role ACL；group fail closed | IAM | 企业 OIDC、组同步、禁用/撤权时限测试 |
| R-S4-14 | 生产基础设施未验证 | Compose + Helm 静态模板 | Platform/SRE | Helm lint/install、TLS、NetworkPolicy、Secret、DR |

## 2. 继承的阻断项

- S0：业务/数据/安全/法务具名 Owner，真实数据目录、保留/删除、预算与 SLO 未签署。
- S1：企业 OIDC、组织映射、RLS 策略、Kubernetes dev 和真实 CI/CD 未验证。
- S2：真实 Model Provider、共享配额/并发/取消、目标 SSE 代理/负载和成本告警未验证。
- S3：S3 IAM/KMS/TLS/lifecycle、ClamAV HA、解析 sandbox/资源限额、orphan reconciliation、真实文档 UAT、多 Worker lease 压测未验证。

S4 不能用新功能关闭这些基础风险。

## 3. 残余设计风险

1. Query hash 仍可能被低熵字典推测；需要租户 HMAC/pepper 才适合更高敏感度审计。
2. Exact vector scan 随 chunk 数线性增长；候选上限不减少扫描成本。
3. Context sanitizer 可能删除合法的安全培训文本，或漏掉变体/编码攻击；当前 metrics 可帮助发现但不能消除风险。
4. Grounded 输出缓冲使长答案占用内存并增加 TTFT；应设置 Provider output、body 和并发硬限制并压测。
5. Citation quote 是当时快照；即使 ACL 允许，也需按保留/法律删除要求执行异步清理或加密擦除。
6. FTS 与向量两个查询之间的知识发布状态可变化；当前数据库 session 可复盘，但生产需要明确事务隔离和并发发布测试。

## 4. 下一阶段候选

- 扩充真实/合成黄金集，加入中文、多轮、冲突、过期、表格、长文、注入和越权矩阵。
- 加入 OpenTelemetry retrieval spans、质量/拒答/引用/成本 dashboards 和安全告警。
- 建立 RAG config 管理/审批/灰度/回滚，并保存线上实验 cohort。
- 在固定生产 embedding 维度后评估 HNSW 与中文 FTS。
- 实现共享 quota/cancellation 和多副本 PostgreSQL/Redis load test。

这些工作只能在相应 Owner/审批范围内进行，不自动获得真实数据或外部供应商授权。
