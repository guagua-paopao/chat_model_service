# S0-07. 风险登记册

评分：概率 P 和影响 I 均为 1–5，风险分 `P×I`；15–25 高、8–14 中、1–7 低。

| ID | 风险 | P | I | 分值 | Owner 角色 | 缓解与证据 | 状态 |
|---|---|---:|---:|---:|---|---|---|
| R-001 | 回答流畅但无依据 | 4 | 5 | 20 | AI Lead | 引用、拒答、黄金集、claim 评测 | open |
| R-002 | ACL 在召回后过滤导致越权/召回损失 | 3 | 5 | 15 | Backend/Security | 安全候选召回、SQL 复用、ACL 硬门禁 | mitigated-by-design |
| R-003 | 提示注入诱导泄密 | 4 | 5 | 20 | Security/AI | 无写工具、来源视为数据、输出验证、INJECTION 集 | open |
| R-004 | 旧文档版本进入答案 | 3 | 4 | 12 | Knowledge Owner | 不可变版本、current 原子发布、VERSION 集 | mitigated-by-design |
| R-005 | 文档解析/OCR 质量差 | 4 | 3 | 12 | AI/Knowledge | 质量统计、预览、抽查、失败阻止发布 | open |
| R-006 | 模型供应商故障/限流 | 3 | 4 | 12 | Backend/SRE | 隔舱、退避、熔断、合法 fallback、Fake 故障 | open |
| R-007 | 真实数据未经批准外发 | 3 | 5 | 15 | Data/Security | 分类路由、默认禁止、供应商 Gate | open-blocking-real-model |
| R-008 | 成本失控 | 3 | 4 | 12 | Product/SRE | 容量模型、token/费用配额、预算告警 | open |
| R-009 | 日志/评测泄露密钥或正文 | 3 | 5 | 15 | SRE/Security | 字段白名单、DLP、短保留、受控采样 | open |
| R-010 | 开源许可证不适用商业模式 | 2 | 4 | 8 | Legal/Architect | 固定版本、SBOM、法务复核、优先宽松许可 | open |
| R-011 | 评测集与真实问题脱节 | 4 | 4 | 16 | Product/QA | 真实访谈、生产反馈脱敏回流、切片监控 | open-blocking-quality-claim |
| R-012 | 过早微服务化拖慢交付 | 2 | 3 | 6 | Architect | ADR-001、量化拆分触发器 | accepted |
| R-013 | 身份/组变更传播过慢 | 3 | 5 | 15 | IAM/Security | 短 TTL+事件失效、禁用测试、IdP SLA | open |
| R-014 | 备份存在但无法恢复/ACL 错乱 | 2 | 5 | 10 | SRE/DBA | 隔离恢复、RPO/RTO 与 ACL 校验 | open |
| R-015 | 模型同名版本漂移造成质量回归 | 3 | 4 | 12 | AI/Platform | 固定模型版本、route 版本、持续评测 | open |
| R-016 | 合成假设被误当真实业务决定 | 3 | 4 | 12 | Product/PM | ASSUMPTION 标识、S0 条件 Gate、业务签字 | open |

## 处置规则

- 高风险每个 Sprint 评审；阻断项未关闭前不得接真实数据/模型或作生产承诺。
- 风险接受必须记录接受人、原因、补偿控制和到期日。
- P0 安全风险（跨租户/密钥/受限数据外发）没有可接受的质量或排期豁免。

