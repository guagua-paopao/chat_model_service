# S2 Model Gateway 与流式聊天证据包

> 版本：s2-v1.0  
> 日期：2026-07-15  
> 结论：**合成环境功能门禁通过；可进入 S3 合成知识摄取开发，真实模型与生产部署仍受审批和分布式控制项阻断**

S2 在 S1 的身份、租户、会话和 BFF 纵切上，增加了可运行的通用大模型问答链路。浏览器可通过 BFF 创建会话、流式提问、停止和重试；API 通过供应商中立的 Model Gateway 调用确定性 Fake Adapter 或经批准的 OpenAI-compatible 端点，并保存模型调用、用量、成本快照和安全错误信息。

S2 明确不声称已经实现企业知识问答。`response_mode=general` 只表示裸模型通用回答；`grounded_answer/search_only` 和任何知识库 ID 都会被拒绝，避免把未实现的 RAG 伪装成有依据答案。

## 文档导航

| 文档 | 用途 |
|---|---|
| [需求与范围](01-s2-requirements-and-scope.md) | 场景、功能/非功能需求、验收条件和边界 |
| [网关、韧性与安全设计](02-model-gateway-and-security-design.md) | 组件、信任边界、路由、超时、重试、熔断和取消 |
| [API、SSE、数据与成本设计](03-api-sse-data-and-cost-design.md) | 接口、字段、事件、状态机、表结构和错误码 |
| [开发教学与故障注入](04-development-tutorial-and-fault-injection.md) | 从零运行、流式调试、Fake 指令、Adapter 教学和排障 |
| [测试与验证报告](05-test-and-verification-report.md) | 自动化、迁移、前端构建、全栈冒烟及证据限制 |
| [风险与开放项](06-risks-and-open-items.md) | 生产阻断项、Owner、退出条件 |
| [S2 Gate 评审](07-s2-gate-review.md) | 逐条退出条件与下一阶段授权范围 |
| [决策日志](decision-log.md) | S2 重要决策、理由和复审触发器 |
| [机器清单](manifest.yaml) | 阶段版本、产物、验证和禁止事项 |

## 可执行产物

- Model Gateway：`apps/api/src/qa_api/model_gateway.py`。
- 聊天编排与持久化：`apps/api/src/qa_api/chat.py`。
- REST/SSE 入口：`apps/api/src/qa_api/main.py`。
- 数据迁移：`apps/api/migrations/versions/20260715_0002_s2_model_gateway.py`。
- Web 问答界面与 BFF 白名单：`apps/web/app/page.tsx`、`apps/web/app/api/qa/[...path]/route.ts`。
- 契约：`docs/enterprise-qa-system/openapi.yaml`。
- 自动化：`tests/unit/test_model_gateway.py`、`tests/integration/test_chat.py`、`scripts/smoke_s2.py`。

## 当前边界

1. Fake Provider 只能用于 `local/test/dev`；`staging/production` 启动时强制拒绝。
2. 外部 Provider 只有在显式开启、HTTPS 地址、模型名和密钥同时存在时才可用；密钥只由 Secret 注入。
3. SSE 已实现 15 秒心跳，但不承诺 token 级断点续传；断线后读取已持久化消息，失败/取消消息可显式重试。
4. 配额与主动取消注册表当前为单进程实现。多副本生产必须先接入 Redis 等共享协调层，详见 ADR-018。
5. 没有真实模型、真实知识、企业 IdP、Kubernetes 集群和负载环境的验证证据，因此不能据此批准生产上线。
