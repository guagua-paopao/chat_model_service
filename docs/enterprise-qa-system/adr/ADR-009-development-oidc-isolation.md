# ADR-009：开发 OIDC 与企业身份源隔离

- Status：Accepted
- Decision date：2026-07-15
- Owners：Architecture / Security / Backend / Frontend
- Review date：企业 OIDC 联调前

## Context

S1 必须完整体验浏览器登录与服务端 JWT 验证，但当前没有企业 OIDC issuer、客户端注册、组映射和禁用传播 SLA。仅签发一个静态开发 JWT 无法覆盖 Authorization Code、PKCE、JWKS、code 重放和浏览器会话边界。

## Decision

本地环境提供独立 Fake IdP，实现 OIDC discovery、RS256 JWKS、Authorization Code + PKCE(S256)、一次性短期 code 和三个合成人员。Fake IdP 只进入本地 Compose，不进入 Helm 或生产镜像清单。

API 的生产路径校验签名、`iss`、`aud`、`exp`、`iat`、`sub`、`tenant_id`，再用 `(tenant_id, issuer, subject)` 查询本地用户状态与角色。HS256 开发令牌必须显式开启，且配置层在 staging/production 拒绝启动。

## Alternatives

- 直接信任反向代理 header：无法独立验证签名和声明，拒绝。
- 只用静态 JWT：适合单元测试，但不能证明浏览器 OIDC 流程。
- 在开发中强依赖企业 IdP：在企业注册完成前会阻塞工程纵切。

## Consequences

Fake IdP 不是标准完整性认证，也不证明企业组映射正确；企业联调必须重新执行负向测试并记录 issuer、audience、JWKS 轮换、登出和禁用传播结果。开发便利配置不得复制到生产。

