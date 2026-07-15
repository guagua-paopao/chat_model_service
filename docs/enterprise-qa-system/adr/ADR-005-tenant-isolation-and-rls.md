# ADR-005：逻辑租户隔离 + 可选 PostgreSQL RLS

- Status：Accepted
- Decision date：2026-07-15
- Owners：Architecture / Security / Backend
- Review date：S1 安全测试后、商业模式变化时

## Context

即使首期只有一个企业，也需要验证跨租户安全并保留未来多企业能力。数据、缓存、队列、对象、引用和日志都可能形成串租户侧信道。

## Decision

所有租户业务表含 `tenant_id`；TenantContext 只从已验证 token/服务端映射产生。Repository API 必须显式接收 TenantContext，缓存/队列/对象 key/幂等也包含租户边界。

高敏/生产部署可启用 PostgreSQL RLS 作为双保险，但不替代应用授权。文档 ACL 在安全候选集合内召回；引用/下载/导出再次鉴权。

## Alternatives

- 每租户独立数据库：隔离强，但小规模运维和升级成本高。
- 只靠应用 WHERE：简单但单点失误风险高，仍需测试/可选 RLS。
- 向量召回后再过滤：拒绝，会泄露并损失正确 top-k。

## Consequences

查询与索引更复杂，需要 tenant/ACL 组合索引和大量负向测试。RLS 需正确设置/清理连接池 session context，后台任务必须显式绑定租户。

## Security and Cost

跨租户成功访问为 P0，门槛为 0。单库成本低但逻辑隔离风险需要代码、RLS、测试和审计补偿；若未来合规要求物理隔离，提交新 ADR。

