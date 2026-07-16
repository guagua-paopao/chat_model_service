# ADR-026：RAG 配置不可变发布并保存检索快照

- 状态：Accepted
- 日期：2026-07-16

## 背景

如果在线修改候选数、阈值、Prompt 或模型而不保存版本，就无法解释质量回退、反馈或历史回答。

## 决策

每租户以 `(code,version)` 发布不可变 `rag_configs`。每次知识请求保存 retrieval run；进入 rerank 的每个 chunk 保存 vector/lexical/fusion/rerank/final 分数和 rank，以及知识、ACL、embedding、reranker、Prompt 和配置快照。run 只存 query hash，不存 raw query。

## 后果

回答可以确定性复盘和按版本比较；存储量上升，需要保留/分区/清理策略。S4 自动种子配置不等于生产审批流，后续必须增加双人发布和回滚。
