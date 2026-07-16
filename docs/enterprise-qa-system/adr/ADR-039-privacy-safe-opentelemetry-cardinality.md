# ADR-039：OpenTelemetry 仅使用隐私安全的低基数属性

- 状态：Accepted
- 日期：2026-07-16
- Owner：SRE / Security / Privacy

## 决策

- 指标属性只允许 HTTP 方法、路由模板、状态码和评测门禁结果。
- 禁止在指标中使用 tenant、user、conversation、message、文档名、动态 UUID、query、prompt 或正文。
- Trace 接受 W3C `traceparent` 并返回 `X-Trace-ID`；日志只记录 request/trace、路由模板、状态和耗时。
- OTel Provider 为应用实例私有，不修改测试进程中的全局 Provider；导出失败不得影响业务请求。
- 进程内 5 分钟、最多 5000 条样本的快照只用于诊断，明确标记 `production_slo_evidence=false`。

## 后果

指标成本和泄露面受控；跨租户排障需要依赖受控日志/Trace 查询，而不能通过高基数指标标签实现。
