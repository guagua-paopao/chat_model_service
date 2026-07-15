# S3 Gate 评审

> 评审日期：2026-07-16  
> 决定：**Conditional GO — 允许 S4 合成 RAG 闭环开发；禁止真实企业数据、真实外部模型扩大使用、staging 多副本和生产上线。**

## 1. 退出条件

| 条件 | 结果 | 证据/限制 |
|---|---|---|
| 签名上传与双 bucket 隔离 | 通过（合成） | local HMAC + S3/MinIO Adapter；生产 IAM/KMS 待验证 |
| 大小/SHA/MIME/恶意扫描 | 条件通过 | 自动化通过；生产 ClamAV/恶意语料/资源隔离待验证 |
| 四格式统一解析 | 通过（合成） | PDF/DOCX/TXT/MD 单测；真实复杂文档 UAT 未做 |
| 结构分块和 provenance | 通过 | page/section/hash/token + parser/chunker/model version |
| Embedding batch/retry/reuse | 条件通过 | Fake/协议实现；真实供应商、数据条款、成本未验证 |
| Worker lease/idempotency/dead-letter | 条件通过 | SQLite/单 Worker 功能；PostgreSQL 多 Worker 压测未做 |
| 不可变版本与原子发布 | 通过 | v1/v2 发布前后集成断言；orphan reconciliation 待补 |
| tenant/ACL 前置过滤 | 通过（user/role） | 跨 tenant 和 role 测试；group fail closed，企业 IAM 待接 |
| 管理 UI 状态/错误/检索 | 通过 | BFF 白名单、上传、轮询、进度、错误、debug search |
| 聊天不冒充知识能力 | 通过 | grounded/search/KB chat 409；UI/OpenAPI 明示 debug only |
| API/迁移/部署/文档 | 通过或有记录限制 | OpenAPI、0003、Compose PostgreSQL/Redis/MinIO 全栈 smoke、Helm 静态模板、S3 证据包；Helm CLI/集群验证仍阻断生产 |
| 自动化质量门禁 | 通过 | 45 tests、86% coverage、Ruff/Mypy/ESLint、迁移、契约、容器构建、Python/npm 已知漏洞 0 |
| Kubernetes/性能/DR/生产安全 | 未通过 | 继续为生产阻断 |

## 2. S4 授权范围

允许：

- 在 tenant + published + ACL 安全集合中实现 pgvector/full-text/hybrid retrieval。
- 保存 retrieval run/hits/config version，加入 deterministic fusion/rerank。
- context packing、受控 source IDs、引用生成/再鉴权、证据不足拒答。
- 只用合成/公开/批准非敏感数据和 Fake/批准沙箱模型运行质量实验。
- 扩充黄金集的 retrieval、groundedness、citation、abstention 和 prompt injection 测试。

不允许：

1. 绕过 ACL 做全局 ANN/top-k 或缓存无 ACL 指纹结果。
2. 让模型自由编造 citation/document URL。
3. 把 debug lexical score 当 Recall@k 或生产检索质量。
4. 在没有真实数据/供应商/安全审批时上传 confidential/restricted 或扩大外部传输。
5. 用本 Gate 关闭 R-S1/R-S2/R-S3 生产风险。

## 3. Gate 解释

“GO”只表示 S3 工程基线足以安全支撑下一阶段合成开发。它不表示业务 Owner 接受、真实数据可用、SLO 达标、Kubernetes 已验证、供应商获批或允许生产流量。任何发布决策必须引用新的环境证据和未关闭风险清单。
