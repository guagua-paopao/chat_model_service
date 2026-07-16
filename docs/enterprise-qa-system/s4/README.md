# S4 可溯源 RAG 闭环证据包

> 版本：s4-v1.0  
> 日期：2026-07-16  
> 数据边界：仅限合成、公开或明确批准的非敏感资料  
> 结论：S4 工程门禁通过；仅授权进入 S5 合成质量/可观测性开发，不代表真实数据、staging 或生产上线许可。

S4 把 S3 的安全文档集合接入问答：先在 tenant、发布状态、当前版本和文档 ACL 约束内分别执行 pgvector 与全文召回，再用加权 RRF、可替换 reranker、相邻块合并和 token 预算构造不可信证据上下文。回答在服务端缓冲，引用 ID 校验通过后才输出；证据不足或命中安全策略时不调用模型。检索配置、候选分数、模型/Prompt 版本、引用快照和用户反馈均可审计。

## 文档导航

| 文档 | 目的 |
|---|---|
| [需求与范围](01-s4-requirements-and-scope.md) | 场景、角色、需求、验收、非目标 |
| [检索、生成与安全设计](02-hybrid-retrieval-grounding-security.md) | ACL-first、hybrid、rerank、packing、注入和引用边界 |
| [API、数据、Prompt 与评测设计](03-api-data-prompt-evaluation-design.md) | 接口、SSE、字段、表、版本与指标 |
| [开发教学与故障注入](04-development-tutorial-and-fault-injection.md) | 从零实现顺序、本地操作和失败实验 |
| [测试与验证报告](05-test-and-verification-report.md) | 自动化、迁移、容器、评测和供应链证据 |
| [风险与开放项](06-risks-and-open-items.md) | 生产阻断、Owner、退出条件和残余风险 |
| [S4 Gate 评审](07-s4-gate-review.md) | 退出条件和下一阶段授权边界 |
| [决策日志](decision-log.md) | 重要决策、理由、ADR 与复审触发器 |
| [机器清单](manifest.yaml) | 能力、验证、风险和禁止事项 |

## 可执行产物

- RAG 编排：`apps/api/src/qa_api/rag.py`，检索、融合、重排、packing、拒答和引用验证。
- Reranker Adapter：`apps/api/src/qa_api/reranker.py`，本地确定性教学实现与 HTTPS Provider 实现。
- Chat 闭环：`chat.py`，支持 `general`、`grounded_answer`、`search_only`。
- 数据/迁移：`persistence.py` 与 `20260716_0004_s4_grounded_rag.py`。
- 契约：`docs/enterprise-qa-system/openapi.yaml`。
- Web/BFF：回答模式、检索状态、拒答/故障区分、引用再鉴权与反馈。
- 评测：`tests/evaluation/s4-mini-golden.json` 与 `scripts/evaluate_s4.py`。
- 部署：Compose 本地 Fake 路由；Helm 生产模板强制批准的 Chat/Embedding/Rerank Provider。

## 关键不变量

1. ACL 先于向量/全文评分和 Top-K；管理员权限不自动获得文档读取权。
2. 只检索 active、published、current version、未删除文档；旧引用使用不可变快照，但查看时按当前 ACL 再鉴权。
3. `SOURCE` 是不可信数据。文档内指令不改变系统规则，命中注入启发式的句子从模型上下文中移除并计数。
4. 模型只能引用本次选中的 `SRC-001` 形式 ID；缺失或未知 ID 整个回答 fail closed 为拒答。
5. grounded 流先缓冲模型内容；校验通过后才发送 `message.delta` 和 `citation`。
6. 没有足够证据或问题直接触发安全策略时不调用模型，并记录内部拒答原因。
7. feedback 保存本次检索、配置、Prompt、模型和知识版本快照，不覆盖历史引用。
8. local Fake Embedding/Reranker/Model 仅用于教学和确定性回归；生产配置会拒绝启动。

## 快速检查

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\evaluate_s4.py
.venv\Scripts\python.exe -m ruff check apps scripts tests
.venv\Scripts\python.exe -m mypy --strict apps/api/src
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run typecheck
docker compose -f infra/compose/compose.yaml config
```

本地已有 S3 Fake Embedding 数据需重新摄取：S4 的确定性实现版本为 `fake-embedding-v2/s4-v1`，不会把旧测试向量误认为同一模型质量证据。
