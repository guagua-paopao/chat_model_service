# S5 重要决策日志

| ID | 日期 | 决策 | 理由 | 证据/ADR | 复审触发器 |
|---|---|---|---|---|---|
| S5-D01 | 2026-07-16 | JWT 只用于认证，role/group 从 tenant 目录态解析 | token claim 可能陈旧或映射错误，停权必须在下一请求生效 | ADR-033、identity 集成测试 | 企业 IAM/SCIM 契约确定 |
| S5-D02 | 2026-07-16 | 权限入口统一为 fail-closed `PolicyEngine`，repository 仍保留 tenant 条件 | 集中决策不应替代数据层隔离 | ADR-033、普通用户 403 | 引入 ABAC/OPA/Cedar |
| S5-D03 | 2026-07-16 | group ACL 加入检索前过滤、citation 再鉴权和 ACL fingerprint | 防止无权结果占 top-k，并保证撤权后引用不可见 | ADR-033、group-only ACL 测试 | ACL cache/搜索引擎拆分 |
| S5-D04 | 2026-07-16 | 配置采用 draft → evaluate → approve → publish；发布行不可变 | 让每次回答可追溯，阻止跳过质量证据 | ADR-034、状态机测试 | 外部评测/灰度平台上线 |
| S5-D05 | 2026-07-16 | evaluator/dataset/evidence 由服务器选择，客户端不能声明 passing | 防止伪造门禁结果 | ADR-034、strict request schema | 独立签名 evaluator 上线 |
| S5-D06 | 2026-07-16 | 创建者不能审批同一候选，即使同时拥有 approver 角色 | 限制单账号错误或滥用 | ADR-034、临时授予角色负向测试 | 正式审批矩阵变更 |
| S5-D07 | 2026-07-16 | rollback 创建更高版本 clone，不修改旧 published 记录 | 保持历史、checksum 和审计可复现 | ADR-034、rollback smoke | canary/自动回滚上线 |
| S5-D08 | 2026-07-16 | local structural evaluator 仅允许 local/test/dev，staging/production fail closed | 它只能验证结构安全，不能充当业务质量证据 | ADR-034、Settings validation | 批准的外部 evaluator 可用 |
| S5-D09 | 2026-07-16 | 配额先用 PostgreSQL tenant 锁、窗口和 TTL lease 做强一致基线 | 当前栈已有事务边界，先证明正确故障语义 | ADR-035、quota 测试、Compose | 目标负载证明 DB 锁不满足 SLO |
| S5-D10 | 2026-07-16 | 配额账本与活动租约分责：账本管 token/费用，lease 管并发 | 避免把估算、结算和运行中状态混在一个计数器 | ADR-035、schema/API | 引入 Provider 最终对账 |
| S5-D11 | 2026-07-16 | 高风险治理事件按 tenant sequence 做 canonical hash chain | 低成本检测插入、删除或字段修改 | ADR-036、tamper test | SIEM/WORM 外部锚定上线 |
| S5-D12 | 2026-07-16 | 不把 hash chain 宣称为不可篡改 | DB 管理者可重写并重算整条链 | ADR-036、Gate No-Go | 独立可信时间戳/WORM 证据 |
| S5-D13 | 2026-07-16 | 管理控制台先只读，写操作保留 API 的 ETag/reason/approval | 避免在未完成 CSRF/二次确认前扩大高风险写入口 | ADR-037、Next build | 管理写入 UX 安全评审通过 |
| S5-D14 | 2026-07-16 | 用量/质量接口只返回 31 天内 tenant 低基数摘要 | 降低 PII/正文暴露和指标基数爆炸 | ADR-037、summary API 测试 | 合规/运营需要新维度 |
| S5-D15 | 2026-07-16 | 安全事件只存安全摘要和 evidence refs，不存 raw prompt/正文 | 事件系统不是敏感内容副本库 | ADR-037、incident schema | 正式证据保全平台接入 |
| S5-D16 | 2026-07-16 | S5 只做本地分支和提交，不上传 GitHub | 每个阶段公开发布都需要用户新的明确确认 | 本次任务边界 | 用户明确确认完整 S5 公开发布 |

## 决策维护规则

- 改变任何不变量时，新建 ADR；不要静默改写旧决策的理由。
- 复审时记录数据、基准、批准人和替代方案，不以“更流行”作为迁移依据。
- 本日志保存阶段选择；精确技术上下文见 `docs/enterprise-qa-system/adr/ADR-033`～`ADR-037`。
