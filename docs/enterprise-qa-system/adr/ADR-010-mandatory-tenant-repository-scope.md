# ADR-010：Repository 强制租户与用户作用域

- Status：Accepted
- Decision date：2026-07-15
- Owners：Architecture / Security / Backend
- Review date：S3 文档 ACL 实现时、启用 RLS 时

## Context

ADR-005 确定逻辑租户隔离，但 S1 需要把原则落实为可测试的函数边界。若 Repository 允许只传资源 ID，调用方极易遗漏租户过滤；如果跨租户 ID 与不存在 ID 返回不同结果，还会形成枚举侧信道。

## Decision

所有业务 Repository 公共方法以 keyword-only 参数显式要求 `tenant_id`；用户私有资源同时要求 `user_id`。资源查询、更新、软删除、分页游标与审计写入使用同一可信作用域。调用方不得从请求 body/query 读取 `tenant_id`，只能使用已验证 Principal。

跨租户或不可见资源统一返回 404。组合外键约束 `tenant_id` 与关联实体一致。类型/签名测试证明缺少作用域无法调用，集成测试证明跨租户 ID 猜测不可见。PostgreSQL RLS 仍作为后续高敏部署的纵深防御，不替代应用层授权。

## Alternatives

- 依靠代码评审发现缺失 WHERE：不够可重复，拒绝。
- 全局隐式 TenantContext：后台任务与连接池中容易串线。
- 每租户独立数据库：S1 成本过高，若合规要求变化另立 ADR。

## Consequences

方法签名更冗长，但安全边界可见、可静态检查、可单元测试。S3 增加知识库 ACL 时必须保持相同模式，并补充 PostgreSQL RLS/连接池清理验证。

