# S4 Gate 评审

> 评审日期：2026-07-16  
> 决定：**Conditional GO — 允许 S5 在合成/公开/批准非敏感范围内开发评测、可观测性和配置治理；禁止真实企业数据扩大使用、staging 多副本和生产上线。**

## 1. 退出条件

| 条件 | 结果 | 证据/限制 |
|---|---|---|
| ACL-first vector + lexical retrieval | 通过（合成） | PostgreSQL SQL/Compose smoke；中文 tokenizer/容量待补 |
| deterministic fusion/rerank | 通过 | RRF、Fake/HTTP Reranker、协议/超时测试；真实模型待批 |
| context packing/provenance/budget | 通过 | 去重、相邻合并、Source ID、token 上限、hit 快照 |
| 证据不足/安全拒答 | 通过（小集） | no-evidence/direct-injection 零模型调用；真实攻击集待补 |
| grounded 输出引用校验 | 通过 | 缓冲输出、unknown/missing ID fail closed |
| immutable citations + current ACL | 通过 | 撤权/恢复、跨租户与受控 preview 测试 |
| config/run/hit/prompt/model 快照 | 通过 | 0004 数据模型与集成断言 |
| feedback 闭环 | 通过 | user/message upsert + answer snapshot |
| Web/BFF | 通过 | 模式、状态、引用、反馈、精确路径白名单 |
| 合成评测 | 通过 | 20 cases 指标 1.0、泄漏 0；不等于业务 UAT |
| API/迁移/部署/供应链 | 通过或有记录限制 | OpenAPI、SQLite/PostgreSQL、容器/Compose、审计；Helm 集群未跑 |
| 性能/真实 Provider/中文/DR | 未通过 | 继续阻断生产 |

## 2. 下一阶段授权范围

允许：

- 在当前合成/批准范围扩大 golden set、claim-level evaluator 和人工误差分析流程。
- 增加 retrieval/groundedness/citation/abstention/成本/延迟观测，建立 dashboard 与告警草案。
- 建立 immutable RAG config 的管理、审批、灰度和回滚流程。
- 在固定批准 embedding 维度的隔离环境做 ANN/中文 FTS benchmark。
- 继续实现共享 Redis 配额、取消和多副本负载实验。

不允许：

1. 因 20 条合成集满分就宣称真实业务质量或 production readiness。
2. 在 ACL 过滤前做全局 ANN/缓存，或返回未重新鉴权的 citation/raw object URL。
3. 在 grounded 模式提前流出未经 Source ID 校验的模型 token。
4. 用 Fake Model/Embedding/Reranker 或 SQLite 作为生产质量/容量证据。
5. 未经数据 Owner/安全/法务批准向外部 Provider 发送 confidential/restricted 数据。
6. 用本 Gate 关闭 S0–S3 IAM、存储、扫描、共享状态、Kubernetes、SLO 或 DR 风险。

## 3. Gate 解释

Conditional GO 表示代码和文档已形成可复现的 S4 工程基线，可安全继续合成开发。它不表示业务签字、数据获批、供应商获批、目标负载/SLO、集群安全、恢复或运维准备完成。任何公开发布 S4 到 GitHub 也仍需用户另行明确确认；本阶段只做本地 Git 归档。
