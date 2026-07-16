# ADR-033：服务端目录态用户组与集中策略判定

- 状态：Accepted
- 日期：2026-07-16
- Owner：IAM / API / Security

## 背景

S1～S4 只从数据库解析用户和角色，`group` ACL 虽已进入契约但检索端始终拒绝，权限检查也散落在 API 路由。直接信任 JWT 中的角色或组会造成陈旧权限、跨租户映射和令牌篡改风险。

## 决策

1. JWT 只提供经过签名验证的 issuer、subject 和 tenant 标识；用户状态、角色、权限和组成员关系均从租户作用域数据库解析。
2. `PolicyEngine` 是路由层唯一权限判定入口，默认拒绝未知权限；资源级 tenant/owner 条件通过 `PolicyContext` 表达。
3. 组 ACL 与 user/role ACL 一样必须在候选召回和引用查看前生效，ACL fingerprint 纳入组集合。
4. 用户停权在下一次请求解析 Principal 时立即生效；不得依赖令牌自然过期。
5. 本地 persona 仅用于合成开发。真实生产必须由企业 IdP/SCIM 或批准的目录同步器维护，并验证五分钟内传播目标。

## 后果

权限来源单一、组 ACL 可验证，且停权不会等待令牌过期。数据库查询增加；后续需批量目录同步、缓存失效、SCIM 重放/乱序和真实 IdP 演练。S5 不声称已经接入企业 IdP。

