# S4 测试与验证报告

> 日期：2026-07-16  
> 范围：S4 合成/批准非敏感数据工程基线  
> 最终结论：功能与确定性工程门禁通过；生产环境门禁未通过。

## 1. 自动化测试

完整 Python 套件：58 tests passed。S4 新增重点：

- grounded 同步/SSE、`retrieval.completed → validated delta → citation` 顺序。
- run/hit/config/citation 落库及 message 快照。
- search-only/no-evidence/direct-injection 零 ModelInvocation。
- invalid Source ID fail closed，不向客户端泄漏模型原文。
- citation 当前 ACL 撤销/恢复与跨租户 KB 安全 404。
- feedback upsert 与检索/模型/Prompt 快照。
- deterministic reranker 排序/CJK token；HTTP 重排顺序恢复、timeout、429 和坏协议。
- PostgreSQL pgvector distance 必须使用类型化绑定参数，防止字面 SQL命名参数漏绑定回归。
- S1–S3 身份、租户、会话、模型网关、摄取、版本/ACL 回归。

执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest --cov=qa_api --cov-report=term-missing
```

## 2. S4 评测门禁

`scripts/evaluate_s4.py` 通过真实 API、摄取与 RAG 链运行 `s4-mini-golden-v1`：

| 指标 | 结果 | 工程门槛 |
|---|---:|---:|
| cases | 20 | 20 |
| Recall@10 | 1.000 | ≥0.90 |
| Citation precision | 1.000 | ≥0.90 |
| Citation completeness | 1.000 | ≥0.90 |
| Groundedness proxy | 1.000 | ≥0.90 |
| Abstention precision | 1.000 | ≥0.90 |
| Abstention recall | 1.000 | ≥0.90 |
| Unauthorized leakage | 0 | 0 |

首轮结果为 recall/completeness/groundedness 0.9167、abstention precision/recall 0.875。误差分析发现泛词覆盖阈值过低；默认 coverage 从 0.20 调到 0.34 后全量复测通过。此过程记录于教学与决策日志。

限制：数据是 5 文档/20 问题的英文合成集，Fake Embedding/Reranker/Model 完全确定；结果不代表中文真实制度、复杂 PDF/表格、真实 Provider、claim-level factuality 或线上质量。

## 3. 静态、契约与前端

| 检查 | 结果 |
|---|---|
| Ruff（API/migration/scripts/tests） | passed |
| Mypy `--strict`（API source） | passed |
| Python compileall | passed |
| OpenAPI 3.1 refs + S0–S4/Compose/Helm YAML | passed |
| Next ESLint | passed |
| TypeScript `tsc --noEmit --incremental false` | passed |
| Next production build | passed |

Python `qa_api` 总覆盖率为 88%；S4 核心 `rag.py` 89%、`reranker.py` 94%。覆盖率只说明已执行路径，不替代权限矩阵和 AI 质量指标。

OpenAPI 版本 `1.4.0-s4`，9 份 YAML、169 个本地 `$ref`、20 个 paths 验证通过；新增 citation detail，补齐 feedback/message/citation/SSE 字段。BFF 只允许精确 message citation/feedback 路径，不开放通配任意代理。

## 4. 数据库与迁移

- SQLite：empty → 0001 → 0002 → 0003 → 0004，downgrade 0003，再 upgrade 0004 通过。
- PostgreSQL 16 + pgvector：extension、0004 migration、vector 写入、ACL-first hybrid chat、citation/feedback 在隔离 Compose 项目通过。
- `embedding_vector` 在 PostgreSQL 使用 `VECTOR`，SQLite 使用 JSON；迁移保留原 JSON embedding 便于可逆与测试。
- S4 当前未建 ANN index，故本证据不包含目标规模性能结论。

## 5. 容器与部署

- `docker compose config` 通过；local 明确 Fake Model/Embedding/Reranker。
- API、Worker、Web 干净镜像构建通过。
- 隔离 Compose smoke 覆盖 PostgreSQL、Redis、MinIO、Fake OIDC、预签名上传、Worker 摄取、grounded chat、citation 再鉴权和 feedback。
- Helm values/configmap/Secret refs 已加入批准 Reranker；production 强制 `fake=false`。本机无 Helm CLI/集群，`helm lint/install` 仍未执行。

## 6. 供应链与秘密

| 门禁 | 结果 |
|---|---|
| Python pinned dependencies + `pip-audit --no-deps` | 0 known vulnerabilities |
| npm audit（lockfile） | 0 known vulnerabilities |
| tracked diff secret pattern scan | no committed runtime secret found |
| pgvector Python client | pinned `0.5.0` |

网络审计只查询公开漏洞数据库；其结果受扫描时间和数据库覆盖限制。生产还需 SBOM、镜像签名、registry policy 和持续扫描。

## 7. 未验证项

真实 Chat/Embedding/Rerank Provider、企业身份/group、真实数据 UAT、中文 FTS、固定维度 ANN、目标容量/P95、red-team、模型内容安全、Kubernetes/Ingress/NetworkPolicy/Secret、共享 Redis 配额/取消、备份恢复与灾难演练均未完成。它们在 Gate 中继续阻断生产。
