# S3 风险与开放项

## 1. 风险登记

| ID | 风险 | 等级 | 当前控制 | Owner | 关闭证据 |
|---|---|---:|---|---|---|
| R-S3-001 | 签名测试扫描器不是企业 AV | P0 生产阻断 | prod 强制 ClamAV | Security/Platform | ClamAV HA、签名更新、EICAR/不可用/超时演练 |
| R-S3-002 | 对象复制成功、DB 失败留下 orphan | P1 | DB 不发布即不可见；bucket 分离 | Platform | reconciliation job、lifecycle、告警与清理审计 |
| R-S3-003 | Parser 复杂度/漏洞导致资源耗尽 | P0 | 大小限制、defusedxml、非 root | Security/SRE | sandbox limit、fuzz、恶意语料、依赖 SLA |
| R-S3-004 | group ACL 未接企业 group | P0 真实数据阻断 | fail closed | IAM | group claims/SCIM、撤权时效、矩阵测试 |
| R-S3-005 | JSON vector/词项分数不是生产检索 | P1 | 明示 debug only | AI/Search | pgvector/full-text/hybrid/rerank 评测达门槛 |
| R-S3-006 | 外部 Embedding 数据条款未批准 | P0 | confidential/restricted 拒绝；Fake local | Security/Legal | DPA、区域、保留、加密、分类路由审批 |
| R-S3-007 | 多 Worker 领取/租约未负载验证 | P0 生产阻断 | SKIP LOCKED + lease | Backend/SRE | 并发/崩溃/时钟/长任务压测，必要时续租 |
| R-S3-008 | S3 IAM/KMS/lifecycle 未实证 | P0 | Helm Secret 引用、双 bucket | Platform/Security | 最小权限、KMS、TLS、versioning、删除/保留演练 |
| R-S3-009 | 真实文档解析质量未知 | P1 | 四格式合成测试 | Knowledge Ops | 批准样本 UAT，页码/章节/乱码/表格报告 |
| R-S3-010 | 未实现 OCR/复杂表格 | P2 | 明确拒绝空 PDF | Product | 业务需求、供应商和安全评审后排期 |
| R-S3-011 | quarantine 删除是 best effort | P1 | 不影响可见一致性 | Platform | cleanup queue、age/size 告警、retention policy |
| R-S3-012 | S2 单进程 quota/cancel 仍存在 | P0 生产阻断 | ADR-018；不扩大上线 | Backend | Redis 原子配额/取消，多 Pod 测试 |
| R-S3-013 | K8s/Ingress/Secret/NetworkPolicy 未安装验证 | P0 | Helm 模板基线 | Platform | lint、隔离集群 install、策略/探针/滚动/回滚 |
| R-S3-014 | 依赖/镜像时点风险 | P1 | lock、audit、非 root | DevSecOps | CI SBOM、签名、持续扫描、修复 SLA |
| R-S3-015 | 聊天误用 debug retrieval | P0 | API 标记，聊天 409，UI 警告 | Product/Backend | S4 有引用/拒答/评测后才能连接 |
| R-S3-016 | SQLite/静态配置与目标运行时存在行为差异 | P1 | 隔离 PostgreSQL/MinIO/浏览器直传 smoke 已纳入 Gate | DevSecOps/Backend | CI 每次执行迁移、全栈链路并保存日志，定期验证 Docker/Kubernetes 网络差异 |
| R-S3-017 | S3 预签名 PUT 本身不提供 `content-length-range` 条件，恶意客户端可在 completion 前占用 quarantine 容量 | P0 真实数据阻断 | 创建时限制声明大小；completion HEAD 精确比对；Worker 读取上限；quarantine 与 published 隔离 | Platform/Security | 采用预签名 POST/受控上传网关或对象存储侧容量策略，并配置短生命周期、配额、异常容量告警和清理审计 |

## 2. S4 前可接受的开放项

只要继续使用合成、公开或批准非敏感资料，可以在不关闭 P0 生产项的情况下开发：pgvector/full-text、hybrid retrieval、rerank、context packing、引用和拒答。S4 测试不得把 external Embedding、真实企业文档或生产流量当默认前提。

## 3. 真实数据前置条件

- 数据 Owner 完成 inventory、classification、purpose、retention、ACL source 和删除责任签字。
- 企业 OIDC/group 来源及撤权传播测试完成。
- quarantine/published bucket 的 IAM、KMS、TLS、日志、lifecycle 和恢复完成。
- ClamAV、解析 sandbox、出站 allowlist 和事件响应完成。
- Embedding/模型供应商 DPA、区域、保留/训练政策和密钥轮换获批。
- 获批文档样本 UAT 无 P0/P1 解析/ACL 问题。

## 4. 生产前置条件

除上述真实数据条件外，还必须关闭 S1/S2 遗留生产阻断：共享 Redis 配额/取消、真实 Provider、Kubernetes/Helm/Ingress、容量性能、可观察性告警、备份恢复、供应链签名和 on-call Runbook。

## 5. 变更触发器

新增文件格式、OCR、group ACL、外部连接器、跨区域存储、不同 Embedding、对象下载、删除/法律保全、Worker 队列中间件或将 retrieval 接入 chat，必须先复审数据流/威胁/ADR/API/迁移/测试，不可仅加一个 Adapter 即宣布支持。
