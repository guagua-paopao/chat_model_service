# ADR-012：浏览器 BFF 会话与 CSRF 边界

- Status：Accepted
- Decision date：2026-07-15
- Owners：Frontend / Security / Backend
- Review date：企业网关或统一会话平台接入时

## Context

浏览器需要调用 API，但把 bearer token 放入 localStorage 会扩大 XSS 后的凭据窃取面；把 token 放入 cookie 后又必须防御 CSRF。浏览器也不应看到 OIDC client secret 或内部 API 地址。

## Decision

Next.js 作为 Backend-for-Frontend：完成 Authorization Code + PKCE，access token 只保存在 `HttpOnly`、`SameSite=Lax` cookie 中，不暴露给页面脚本；生产 cookie 强制 `Secure`。页面只调用同源 `/api/qa/*` 白名单代理。

所有变更请求同时要求 CSRF cookie 与 `X-CSRF-Token` 双提交一致；代理不转发任意目标、客户端 Authorization header 或未列入白名单的方法/路径。登录 `state`、PKCE verifier 和 callback 参数均为短期 HttpOnly 会话材料，登出删除本地 cookie。

## Alternatives

- SPA 直接保存 bearer token：实现简单但 token 暴露面更大。
- 只使用 SameSite：不能作为唯一 CSRF 控制。
- 通用开放代理：存在 SSRF 与越权接口暴露风险。

## Consequences

BFF 成为浏览器会话安全边界，需要独立测试 cookie、CSRF、路径白名单和登出。S1 本地 Compose 为 HTTP 显式关闭 Secure；Helm 默认开启，生产 TLS 终止与可信代理配置仍需部署验证。

