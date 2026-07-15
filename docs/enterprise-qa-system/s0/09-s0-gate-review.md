# S0-09. Gate 评审记录

> 评审版本：s0-v1.0  
> 日期：2026-07-15  
> 结论：**CONDITIONAL GO FOR S1 SYNTHETIC DEVELOPMENT**  
> 明确禁止：真实数据、未批准真实模型、生产承诺

## 1. 退出条件检查

| S0 退出条件 | 证据 | 结果 |
|---|---|---|
| 1–2 个首发场景明确 | 内部员工制度 + IT 支持 | PASS（假设待业务签字） |
| 项目范围、目标、非目标和质量门槛 | 章程、Context、发现基线 | PASS |
| 数据流和数据清单 | 合成数据清单与分类策略 | PASS FOR SYNTHETIC；真实盘点 PENDING |
| 至少 50 条样例且含 ≥10 条无答案/越权/攻击 | 60 条 JSONL；19 个显式高风险样例 + 1 个授权正向对照 | PASS FOR ENGINEERING；双人业务复核 PENDING |
| C4/架构与首批 ADR | 总体架构 + ADR-001～008 | PASS |
| 威胁模型 v0 | TM-01～15 | PASS |
| 风险登记册 | R-001～016 | PASS；阻断项有 Owner 角色 |
| 容量/成本情景 | Pilot/Baseline/Growth | PASS AS ASSUMPTION |
| 裸模型 vs 人工证据实验 | 固定协议和 10 问 | PENDING：无获批模型凭证 |
| 产品/安全/技术/运维批准 | 尚未提供真实签字人 | PENDING |
| 模型/开源许可无无主阻断风险 | Owner 角色已指定，具体模型/代码未批准 | CONDITIONAL PASS |

## 2. Gate 决定

允许进入 S1 的工作：仓库骨架、Compose、CI、开发 OIDC、租户中间件、健康检查、OpenAPI 契约、合成数据和 Fake Provider。

在以下条件完成前，不允许接触真实企业数据或生产模型：

1. OQ-001～005 有具名决定人和批准记录。
2. 真实数据完成 `02-data-inventory.md` 的进入 Gate。
3. 模型合同/区域/保留/训练条款和密钥管理获批准。
4. 黄金集至少两名业务复核，ACL 由知识 Owner 确认。
5. 裸模型/RAG 实验完成且报告保存。

## 3. 已接受决策

- 业务：内部员工制度 + IT 支持；只读问答；合成数据先行。
- 架构：模块化单体 + Worker；PostgreSQL+pgvector；REST+SSE；Model Gateway。
- 安全：逻辑租户 + 可选 RLS；召回前 ACL；数据分类路由；无写工具。
- 治理：不可变文档版本；Prompt/检索配置版本化；评测作为发布门禁。

详细记录见 [decision-log.md](decision-log.md) 和 [ADR 目录](../adr/)。

## 4. S1 启动检查

- [ ] 创建 monorepo 与开发说明。
- [ ] 固定 Python/Node/PostgreSQL/pgvector/Redis/MinIO 版本。
- [ ] 建立 Fake OIDC/Fake Provider 和两个合成租户。
- [ ] 建立 lint/type/unit/integration/OpenAPI/secret/SCA CI。
- [ ] 实现 `/health/live`、`/health/ready`、`/me` 和会话骨架。
- [ ] 编写跨租户负向测试，任何没有 tenant context 的 Repository 调用失败。

## 5. 复审

当开放问题得到回答、真实黄金集建立或模型获批后，发布 `s0-v1.1` Gate addendum，不修改本记录以保留审计历史。
