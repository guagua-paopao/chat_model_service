# ADR-030：检索文档始终是不可信数据

- 状态：Accepted
- 日期：2026-07-16

## 背景

知识库文件可能被误上传、污染或故意植入“忽略规则、泄露 Prompt”等命令。仅在 Prompt 中声明规则不能构成完整控制。

## 决策

Prompt 将 SOURCE 放入显式 JSON 数据边界并声明不可执行；服务端在 context packing 时移除命中明确注入模式的句子，保留原 chunk 和移除计数；模型输出仍经过 Source ID 验证。direct injection 在检索前拒绝。

## 后果

形成分层控制并可审计；启发式可误报/漏报，不能替代 parser sandbox、content firewall、供应商安全能力和持续 red-team。
