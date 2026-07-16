# 备份、恢复与灾难恢复

## 1. 保护对象

| 资产 | 生产备份 | 恢复验证 |
|---|---|---|
| PostgreSQL/pgvector | PITR + 日快照 + 跨故障域副本 | 时间点、表计数、FK/索引、关键旅程 |
| 对象存储 | versioning + replication + lifecycle lock | 对象存在、SHA-256、隔离/发布边界 |
| 配置与 IaC | Git tag、签名镜像、Helm values | 重建同版服务 |
| 密钥 | Secret Manager/KMS 备份策略 | 重新注入而非写入备份包 |
| 审计 | DB + WORM/SIEM 外部锚 | 哈希链连续性与保留期 |

## 2. 本地恢复演练

`drill_s6_recovery.py`：创建临时文件 SQLite、会话 sentinel 和对象 sentinel；用 SQLite online backup 和目录副本创建备份；恢复到全新目录；启动 `seed=false/auto_create=false` 的应用；验证 readiness、会话、数据库备份哈希和对象哈希。

本次测量：合成 RPO 0.013 秒、合成 RTO 0.118 秒，4 个不变量全部通过。它只证明恢复脚本路径，不证明 PostgreSQL PITR、对象版本、多区域或 60 分钟生产 RTO。

## 3. 生产演练步骤

1. 冻结变更并记录演练时间点、目标 transaction/object version。
2. 在隔离账户/namespace 恢复数据库，执行 migration head 检查但不自动升级。
3. 恢复指定对象版本；校验 DB 引用、对象哈希和 quarantine/published 边界。
4. 从 Secret Manager 注入新短期凭据，启动 API/Worker，禁止对外流量。
5. 执行身份、ACL、检索、引用、账本、审计完整性和评测 Gate。
6. 灰度切换 DNS/Ingress，监控错误预算；演练环境销毁按审批执行。
7. 记录真实 RPO/RTO、缺口、Owner 和修复期限。

## 4. 停止/回退条件

出现真实数据污染、跨租户可见、备份覆盖源数据、密钥泄露、审计链断裂或 RPO 超目标时立即停止；保持原生产流量不切换，并启动 P0/P1 事件流程。
