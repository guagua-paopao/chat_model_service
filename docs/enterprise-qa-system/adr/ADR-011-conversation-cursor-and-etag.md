# ADR-011：会话分页游标与 ETag 并发控制

- Status：Accepted
- Decision date：2026-07-15
- Owners：Backend / Frontend / Architecture
- Review date：列表规模或共享会话需求变化时

## Context

会话列表需要在并发创建时保持稳定顺序；更新标题或状态需要避免浏览器覆盖其他写入。裸 offset 在插入时会重复/跳项，客户端自报版本若不校验会产生丢失更新。

## Decision

会话使用 UUIDv7，列表按 `(created_at DESC, id DESC)` keyset 分页。游标包含租户、用户、筛选条件与最后位置，并使用 HMAC 签名；篡改或跨作用域复用返回安全错误。

资源响应返回 `ETag: "v{version}"`。PATCH 必须提交 `If-Match`；缺失返回 428，格式错误返回 400，版本冲突返回 412。更新通过 `WHERE version = expected_version` 原子递增版本，客户端冲突后重新读取再决定是否重试。

## Alternatives

- offset/limit：实现简单但并发稳定性差。
- last-write-wins：可能静默丢失用户修改。
- 数据库锁跨请求：无法跨 HTTP 交互保持且吞吐较差。

## Consequences

游标是不可读的短期协议，不承诺客户端解析；签名 key 必须进入密钥管理并支持轮换策略。未来若筛选条件扩展，必须加入游标绑定或提升游标版本。

