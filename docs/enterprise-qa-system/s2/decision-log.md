# S2 决策日志

| ID | 日期 | 状态 | 决策 | 理由 | 证据/ADR | 复审触发器 |
|---|---|---|---|---|---|---|
| S2-DEC-001 | 2026-07-15 | accepted | 领域层只依赖内部 Adapter/Gateway 类型 | 避免厂商 SDK 和字段扩散 | ADR-014 | 新 Provider/协议 |
| S2-DEC-002 | 2026-07-15 | accepted | 公开请求只允许逻辑 model policy | 防止客户端绕过批准路由或注入 endpoint/key | ADR-014 | 路由产品化 |
| S2-DEC-003 | 2026-07-15 | accepted | Fake 仅 local/test/dev，生产 fail-fast | 防止假模型误部署 | ADR-014 | 不可放宽 |
| S2-DEC-004 | 2026-07-15 | accepted | SSE 使用具名事件、sequence 和 15 秒心跳 | 稳定前后端/代理语义 | ADR-015 | 协议/代理变化 |
| S2-DEC-005 | 2026-07-15 | accepted | S2 不做 token 断点续传 | 避免 token 级写放大，先采用回读+重试 | ADR-015 | 产品要求续传 |
| S2-DEC-006 | 2026-07-15 | accepted | 只在可见 delta 前自动 failover | 防止两个模型输出混拼 | ADR-016 | 多模型组合立项 |
| S2-DEC-007 | 2026-07-15 | accepted | 重试新建 assistant，不覆盖旧失败记录 | 保留审计与用户因果关系 | ADR-016 | 消息树设计变化 |
| S2-DEC-008 | 2026-07-15 | accepted | usage 账本追加且保存调用时价格 | 历史成本可解释 | ADR-017 | 正式计费/币种变化 |
| S2-DEC-009 | 2026-07-15 | accepted | 缺 usage 可估算但必须标记 | 保持链路完整且不冒充账单事实 | ADR-017 | Provider usage 稳定 |
| S2-DEC-010 | 2026-07-15 | accepted | S2 仅允许 general，知识模式显式 409 | 不伪装未实现的 RAG/引用能力 | S2 范围 | S4 上线 |
| S2-DEC-011 | 2026-07-15 | accepted | 内存配额/取消禁止多副本生产 | 单 Pod 状态无法提供全局一致性 | ADR-018 | 共享实现完成 |
| S2-DEC-012 | 2026-07-15 | accepted | 迁移 Job 独立执行，生产回滚优先前向修复 | 避免多副本竞态和账本数据丢失 | ADR-013/S2 数据设计 | 部署平台变化 |
| S2-DEC-013 | 2026-07-15 | accepted | Base64URL 游标必须是规范编码 | 尾字符等价编码不能绕过篡改测试语义 | 自动化测试 | Cursor 版本升级 |
| S2-DEC-014 | 2026-07-15 | accepted | 下载完整性异常不关闭校验，串行重新获取 | 供应链异常必须 fail closed | 测试报告/ADR-013 | 构建代理变化 |
| S2-DEC-015 | 2026-07-15 | accepted | Gate 仅允许 S3 合成开发 | 真实 Provider、共享协调、Helm/K8s/性能仍无证据 | S2 Gate | 阻断项关闭 |

更改已接受决策时追加记录或以新 ADR supersede；不得删除历史。S0/S1 的租户、身份、数据、供应链和生产禁止事项继续有效。
