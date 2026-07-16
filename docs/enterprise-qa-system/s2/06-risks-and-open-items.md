# S2 风险与开放项

| ID | 风险/开放项 | 影响 | Owner | 退出条件 | 状态 |
|---|---|---|---|---|---|
| R-S2-001 | 配额和取消为进程内状态 | 多副本配额放大、取消失效 | Platform/API | Redis 原子租约、TTL、取消 pub/sub/stream、崩溃恢复和多 Pod 测试 | 生产阻断 |
| R-S2-002 | 未指定批准 Chat Provider | 无法验证真实协议、质量、数据区域 | Security/Legal/AI Platform | 供应商、模型、区域、DPA、训练使用、保留期和沙箱审批 | 真实模型阻断 |
| R-S2-003 | 价格为 Fake 快照 | 成本预测不可用于预算/对账 | FinOps | 批准价目表、币种、cached token 规则、账单对账 | 开放 |
| R-S2-004 | 未做目标环境流式压测 | TTFT/SLO/连接容量未知 | SRE/QA | 稳态与 2x 峰值，代理/Pod/DB/Provider 指标和报告 | 生产阻断 |
| R-S2-005 | 熔断器为 Pod 本地 | 多 Pod 对故障感知不一致 | SRE/API | 明确是否允许局部熔断；若不允许则共享状态并做恢复测试 | 开放 |
| R-S2-006 | 没有完整模型指标/告警 | 故障和成本异常发现迟 | SRE | TTFT、总时延、错误率、熔断、配额、token/金额 dashboard+alert+runbook | 生产阻断 |
| R-S2-007 | SSE 不支持 token 续传 | 断线丢失部分回答 | Product/API | 产品接受“回读状态+显式重试”，或立项持久事件日志 | 待产品确认 |
| R-S2-008 | migration downgrade 会删账本 | 回滚可能丢审计/成本 | DBA | 生产采用 expand/contract 与前向修复，备份/恢复演练 | 生产阻断 |
| R-S2-009 | Helm 未 lint/安装 | 模板或 Secret 注入可能有误 | Platform | CI Helm lint + 隔离集群 install/upgrade/rollback smoke | 生产阻断 |
| R-S2-010 | 企业 OIDC 仍未接入 | 组映射/禁用传播未知 | IAM/Security | 企业 app registration、claims、禁用和密钥轮换验证 | 生产阻断 |
| R-S2-011 | 真实知识与 ACL 未进入链路 | 尚不是企业知识问答 | Product/Data/Security | S3 摄取与 ACL，S4 检索/引用/拒答门禁 | 阶段性 |
| R-S2-012 | Prompt 正文保存在数据库 | 隐私、保留和访问风险 | Security/Legal/Data | 加密/访问审计/保留期/删除请求流程批准 | 真实数据阻断 |

## 当前安全默认

- Fake Provider 在 staging/production 启动失败。
- 外部 Provider 缺 HTTPS、key 或 model 时启动失败。
- S2 只允许 `general`；任何知识模式或 KB ID 显式拒绝。
- 真实 key 只可由 Secret Manager/Kubernetes Secret 引用注入。
- 多副本生产在 R-S2-001 关闭前禁止。

上述默认不能替代 S0 的业务、安全、数据和法务审批；未命名 Owner 或未提供证据的风险不能仅通过文档勾选关闭。
