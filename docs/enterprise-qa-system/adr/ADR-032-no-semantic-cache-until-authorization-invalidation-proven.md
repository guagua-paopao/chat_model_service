# ADR-032：权限和失效协议证明前不启用语义缓存

- 状态：Accepted
- 日期：2026-07-16

## 背景

RAG 缓存可能跨用户复用无权引用，并在 ACL 撤销、文档换版、配置/Prompt/模型变化后返回旧结果。相似 query 本身也可能形成侧信道。

## 决策

S4 不实现 semantic answer/retrieval cache。未来方案必须把 tenant、可信 subject/ACL fingerprint、KB/current version、RAG config、Prompt、模型和数据等级纳入 key，并证明撤权/删除/发布的原子失效和防侧信道行为。

## 后果

牺牲潜在延迟和成本收益，换取清晰正确性；在生产 SLO/成本证据显示需要缓存且安全证明完成后复审。
