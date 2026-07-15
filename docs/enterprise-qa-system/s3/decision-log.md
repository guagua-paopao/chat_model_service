# S3 决策日志

| ID | 日期 | 状态 | 决策 | 理由 | 证据/ADR | 复审触发器 |
|---|---|---|---|---|---|---|
| S3-DEC-001 | 2026-07-16 | accepted | 文件正文走预签名 PUT，不经业务 JSON/API 代理 | 隔离大文件数据面，减少 API 内存/带宽和密钥暴露 | ADR-019 | 上传网关/内容检查架构变化 |
| S3-DEC-002 | 2026-07-16 | accepted | quarantine 与 published 强制不同 bucket | 未验证对象不能与已发布对象共享写路径 | ADR-019 | 对象平台/跨区域变化 |
| S3-DEC-003 | 2026-07-16 | accepted | filename 仅元数据，物理 key 只用服务端 UUID | 防路径遍历、碰撞和敏感文件名泄露 | ADR-019 | 新连接器保留源路径 |
| S3-DEC-004 | 2026-07-16 | accepted | 文档版本不可变，新版本追加 | 保持引用、审计、回滚和重建可解释 | ADR-006/020 | 在线编辑需求 |
| S3-DEC-005 | 2026-07-16 | accepted | chunk 先 staged，对象复制后 DB 单事务切 active | 不出现半索引；旧版本在新版本成功前可用 | ADR-020 | 跨系统事务/索引服务变化 |
| S3-DEC-006 | 2026-07-16 | accepted | 复制后 DB 失败的 orphan 允许存在但不可见 | 对象存储与 DB 无原子事务；优先保证安全可见性 | ADR-020 | reconciliation/lifecycle 实现 |
| S3-DEC-007 | 2026-07-16 | accepted | S3 用 DB lease polling 作为任务真相源，outbox 保存事件 | 避免引入未需要的 broker 双写；保留未来集成边界 | ADR-021 | 吞吐超过 DB 队列能力/事件总线接入 |
| S3-DEC-008 | 2026-07-16 | accepted | completion 隐式幂等，手工 retry 强制 Idempotency-Key | 浏览器重发安全；操作员动作可追踪 | ADR-021 | API 幂等标准统一 |
| S3-DEC-009 | 2026-07-16 | accepted | ACL 在数据库候选集合中先于评分/top-k | 防越权泄露和有权召回损失 | ADR-022 | 引入 ANN/缓存/rerank |
| S3-DEC-010 | 2026-07-16 | accepted | 当前 group ACL fail closed | Principal 没有可信 group，不猜测权限 | ADR-022 | OIDC group/SCIM 接入 |
| S3-DEC-011 | 2026-07-16 | accepted | parser/chunker/embedding model/version/dim 写入版本 | 可重建、比较、回滚和解释 | ADR-023 | 算法/库主版本变化 |
| S3-DEC-012 | 2026-07-16 | accepted | embedding hash reuse 只限同 tenant/model/dim | 避免跨租户侧信道和不兼容向量 | ADR-023 | 中央缓存立项 |
| S3-DEC-013 | 2026-07-16 | accepted | Fake Embedding 和签名 scanner 只允许 local/test/dev | 防演示替身误部署生产 | ADR-024 | 不可放宽；替换为批准实现 |
| S3-DEC-014 | 2026-07-16 | accepted | 外部 Embedding 禁止 confidential/restricted | 继承数据分类默认拒绝原则 | ADR-024 | 数据 Owner/DPA/私有路由审批 |
| S3-DEC-015 | 2026-07-16 | accepted | S3 retrieval 明示 debug only，聊天知识模式继续 409 | 不冒充未完成的引用/拒答/RAG 能力 | S3 范围/Gate | S4 全门禁通过 |
| S3-DEC-016 | 2026-07-16 | accepted | JSON 保存 S3 Fake vectors，S4 再迁移 pgvector | 简化确定性教学，不提前宣称生产向量索引 | ADR-002/S3 范围 | S4 hybrid retrieval |
| S3-DEC-017 | 2026-07-16 | accepted | Compose 的 API/MinIO 同时接入 frontend 与 internal backend；宿主端口只绑定 `127.0.0.1` | 浏览器必须访问预签名 public endpoint；当前 Docker Desktop 不会为仅 internal 网络建立宿主转发，同时不能暴露 Postgres/Redis | S3 全栈 smoke/部署设计 | 使用 Ingress、反向代理或不同容器运行时 |
| S3-DEC-018 | 2026-07-16 | accepted | S3 Gate 强制保留真实 PostgreSQL/MinIO 隔离 smoke，SQLite 仅作快速测试 | SQLite 未暴露外键 flush 顺序，静态 Compose 也未暴露 public endpoint 不可达；两项均由全栈测试发现 | S3 测试报告 | CI 集成环境等价性变化 |

已接受决策只追加或由新 ADR supersede，不删除历史。S0-S2 的身份、tenant、供应链、模型和生产阻断继续有效。
