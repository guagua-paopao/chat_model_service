# ADR-027：Grounded 输出在引用校验前不可见

- 状态：Accepted
- 日期：2026-07-16

## 背景

模型可能遗漏引用或生成不存在的 Source ID。传统逐 token SSE 一旦向客户端发出内容就无法撤回，之后判定失败也已造成泄漏或错误展示。

## 决策

grounded 模式在服务端缓冲模型 delta，completion 后提取 `[SRC-nnn]`。至少一个且全部属于本次 selected Source 集合时才落 citation 并发送 message delta；否则丢弃模型原文并返回安全拒答。general 模式保持 S2 直接流式。

## 后果

建立清晰的可见性安全边界；代价是 grounded TTFT 增加、实例内存增加。未来只有在使用可验证的结构化增量协议时才复审。
