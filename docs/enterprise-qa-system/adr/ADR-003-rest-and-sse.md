# ADR-003：REST + SSE 流式协议

- Status：Accepted
- Decision date：2026-07-15
- Owners：Architecture / API / Frontend
- Review date：外部 API v2 或实时需求变化时

## Context

浏览器需要流式展示模型输出、引用和用量。当前交互是客户端发一个问题，服务端单向推送多个事件，不需要持续双向音视频。

## Decision

资源管理使用 REST/JSON，聊天使用 `POST /chat/completions` 建立 `text/event-stream`。SSE 事件包含公共 `request_id/message_id/sequence/created_at`，类型包括 started、retrieval.completed、delta、citation、usage、completed 和 error。

流建立前错误使用 HTTP `application/problem+json`；建立后使用 SSE error 事件。心跳、网关 timeout、取消和优雅终止作为协议一部分。

## Alternatives

- WebSocket：双向灵活，但网关、鉴权、重连和契约更复杂，当前无必要。
- 长轮询：兼容好但延迟、连接和实现体验较差。
- gRPC streaming：服务间高效，但浏览器与企业集成门槛较高。

## Consequences

前端与 API 实现简单、可使用标准 HTTP 设施；但 SSE 断线后的 token 级恢复不在 v1 保证内，客户端需要查询最终消息状态。代理缓冲和 idle timeout 必须测试。

## Security and Cost

流式响应仍执行认证、配额和输入限制；引用事件只返回限长预览并再次鉴权。活动 SSE 是容量指标，必须防止连接耗尽。

