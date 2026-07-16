# S7 风险登记册

| ID | 风险 | 可能性/影响 | 当前控制 | Owner | 关闭条件 |
|---|---|---|---|---|---|
| S7-R01 | 合成 UAT 被当真实业务验收 | 高/高 | 明确 local/NO-GO | Product/Business | 真实 UAT 签收 |
| S7-R02 | digest 格式正确但制品不存在/未签名 | 高/高 | 清单明确未验证 | DevSecOps | registry attestation 验证 |
| S7-R03 | 开发 persona 被当企业审批 | 高/高 | 角色名/文档声明 | IAM/CAB | 企业 OIDC+变更系统 |
| S7-R04 | 客户端伪造观察值 | 高/高 | 本地限定 | SRE | 控制器可信抓取指标 |
| S7-R05 | 灰度 API 与集群实际状态漂移 | 高/高 | 生产禁用本地编排器 | Platform | 外部控制器 reconciliation |
| S7-R06 | 哈希链被整体重写 | 中/高 | 本地链校验 | Security | WORM/SIEM 锚定 |
| S7-R07 | 错误阈值不适合真实业务 | 中/高 | 阈值标为假设 | Product/SRE | 真实基线与变更批准 |
| S7-R08 | 自动回滚数据库不兼容 | 中/高 | expand/contract 文档 | DBA | staging 前向修复演练 |
| S7-R09 | 迁移 downgrade 破坏 S7 证据 | 中/高 | 生产禁止盲降 | DBA | 备份/PITR/前向修复 |
| S7-R10 | 控制台暴露审批元数据 | 中/中 | tenant scope、safe refs | Security | 隐私/访问审计 |
| S7-R11 | Owner/on-call/供应商联系人缺失 | 高/高 | Gate 阻断 | Service Owner | 具名并验证升级链 |
| S7-R12 | 培训完成但未掌握故障路径 | 中/高 | 要求实操演练 | Enablement/SRE | 签收与复测 |
| S7-R13 | 已知问题摘要遗漏 P1 | 中/高 | 五签和零 P0/P1 条件 | QA/Product | 缺陷台账对账 |
| S7-R14 | S6 阻断项被 S7 流程掩盖 | 高/高 | S7 Gate 继承 S6 阻断 | Steering Committee | S6 阻断逐项关闭 |
