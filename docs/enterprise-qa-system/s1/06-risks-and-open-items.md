# S1 风险与开放项

| ID | 风险/开放项 | 级别 | 影响 | Owner 角色 | 退出条件 | 阻断范围 |
|---|---|---:|---|---|---|---|
| S1-R01 | 企业 OIDC issuer/client/redirect/group mapping 未提供 | 高 | 无法证明真实身份与权限映射 | IAM + Security | dev 企业 IdP 注册；完整正负向测试；配置入 Secret | staging/production |
| S1-R02 | 用户禁用、组撤销与 token 生命周期 SLA 未确认 | 高 | 离职/撤权用户可能继续访问 | IAM + Security | 定义 SLA；测试撤销传播、短 token 与 session 清理 | production |
| S1-R03 | GitHub 仓库、保护规则与 dev environment 未接入 | 高 | “主干自动部署 dev”不可证明 | Platform | 建仓、branch protection、environment approval/secret；成功部署记录 | S1 完整退出条件/production |
| S1-R04 | Helm 未 lint/未在集群安装 | 高 | 模板或平台策略可能在部署时失败 | Platform/SRE | 固定 Helm 版本；lint/template；dev install/smoke/rollback | staging/production |
| S1-R05 | Secret Manager、TLS、WAF、NetworkPolicy 未落地 | 严重 | 密钥或网络边界不满足生产要求 | Security/Platform | 威胁评审；外部 Secret；TLS；默认拒绝网络策略；渗透验证 | production |
| S1-R06 | PostgreSQL RLS 未启用 | 中 | 应用查询缺陷缺少数据库纵深防御 | Backend/DBA/Security | S3 ACL 评审决定启用范围；补连接池清理测试 | 高敏/生产待评审 |
| S1-R07 | BuildKit 本机 metadata cache 异常 | 中 | 本地不能证明标准 CI 构建路径 | Platform | 清洁 runner 标准构建成功；记录 image digest | 远端 CI 证据 |
| S1-R08 | 30 分钟新开发者启动未独立计时 | 低 | 上手体验目标证据不足 | Tech Lead | 新成员按文档计时并提交反馈/日志 | S1 完整退出条件 |
| S1-R09 | 审计日志尚非不可篡改/未导出 SIEM | 高 | 生产调查与合规证据不足 | Security/SRE | 明确保留期、WORM/集中日志、访问审计与告警 | production |
| S1-R10 | 备份恢复、RPO/RTO 未演练 | 高 | 无法承诺 15m/60m | DBA/SRE | dev/staging 恢复演练与报告 | production |
| S1-R11 | 用户 `last_login_at` 尚未更新，登出不通知上游 IdP | 中 | 身份审计与全局登出不完整 | IAM/Backend | 企业 OIDC 联调中实现并测试 | production |
| S1-R12 | BFF 尚未配置完整 CSP/边缘限流 | 中 | XSS/滥用补偿控制不足 | Frontend/Security | CSP report-only→enforce；网关限流测试 | production |
| S1-R13 | S0 业务、真实数据、模型与法务批准仍缺失 | 严重 | 不得接入真实文档/模型或对外承诺 | Product/Data/Legal/Security | 完成 S0 开放项与具名审批 | real data/model/production |

## 当前允许继续的范围

以上风险不阻断 S2 的合成开发：可以实现 Model Gateway 接口、两个适配器（deterministic fake + 经批准的沙箱可选）、SSE、取消/重试、usage/cost 记录与错误归一化。不得加载真实企业文档、使用未批准模型路由或把 Fake IdP 部署为正式身份源。

## 风险管理规则

- 严重/高风险关闭必须附可复现证据，不能只把状态改为 done。
- 改变身份、租户、数据出域或生产密钥边界必须新增 ADR/威胁模型变更。
- 风险接受必须具名、说明补偿控制和到期日；不得永久接受跨租户成功访问。

