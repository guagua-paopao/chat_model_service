# ADR-015：SSE 终态事件、心跳与断线语义

- Status：Accepted
- Decision date：2026-07-15
- Owners：API / Web / SRE
- Review trigger：需要跨设备续传、WebSocket 或代理平台变化

## Context

流式回答需要低 TTFT、代理存活和可预测终态。HTTP 流建立后无法用新的 HTTP 状态表达 Provider 失败；把每个 token 事务化保存又会显著增加数据库写放大。

## Decision

采用具名 SSE 事件 `message.started/message.delta/usage/message.completed/error`，每个业务事件有单调 `sequence`；15 秒无事件发送无 ID 的注释心跳。流内错误通过 `error` 终态表达，非流式继续使用 Problem JSON。

S2 不持久化每个 delta、不支持 `Last-Event-ID` token 续传。客户端断开会取消活动生成、释放许可并将助手消息标记 `cancelled`；客户端随后读取会话并按需显式重试。

## Consequences

协议简单、数据库写入可控，但断线会丢失尚未提交的部分回答。若未来业务要求无缝续传，需要引入持久事件日志并另立 ADR，不能把当前 sequence 误当可恢复游标。
