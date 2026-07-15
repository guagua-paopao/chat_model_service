# ADR-006：不可变文档版本与原子发布

- Status：Accepted
- Decision date：2026-07-15
- Owners：Knowledge / Backend / Data
- Review date：S3 摄取实现后

## Context

企业制度会更新，解析/切分/Embedding 也会变化。直接覆盖 chunk 会导致构建过程中部分可见、历史回答无法复现、旧新事实混用和回滚困难。

## Decision

`documents` 表示逻辑文档，`document_versions` 与 chunks 不可变。新版本在 staged 状态完成扫描、解析、切分、Embedding、索引和评测后，在事务中切换 `current_version_id` 并递增知识版本。旧版本保留为 superseded/archived，默认不参与新问答。

下线/删除先令在线过滤不可见，再异步清理缓存、向量和对象；历史消息保存当时版本引用，但访问正文时重新鉴权。

## Alternatives

- 原地覆盖：实现短，但不可审计/回滚且构建中不一致。
- 删除后重建：会产生不可用窗口和历史断链。
- 所有历史版本同时检索：容易返回过期/冲突事实，不作为默认。

## Consequences

需要额外存储和生命周期任务；换来原子发布、可回滚和历史可追踪。显式历史查询若以后支持，需独立权限和 UX。

## Security and Cost

旧版本仍继承分类/ACL，不能因 archived 放宽权限。存储按保留策略清理；重建 Embedding 成本进入发布预算。

