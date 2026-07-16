# S7 需求与范围

## 目标场景

- RC-01：平台工程师从通过的评测运行冻结同一不可变发布候选。
- UAT-01：业务代表对 UC-01～05 逐项记录结果与安全证据引用。
- APR-01：产品、业务、数据、安全、SRE 分别签署或拒绝。
- ROL-01：Release Manager 依次执行 dark、5%、25%、50%、100% 灰度。
- ROL-02：指标退化自动停止；安全事件/越权泄漏自动回滚。
- OPS-01：审计员读取候选、UAT、签署、事件和哈希链完整性。
- HDO-01：产品、知识管理员、开发、SRE、安全/审计完成培训和移交清单。

## 功能需求

1. 候选必须引用 `gate_result=passed` 的完成态评测；服务端从评测快照派生 Prompt/检索版本。
2. `git_sha/image_digest/sbom_digest/db_migration/model routes/dataset/eval/rollback target` 冻结后不可修改。
3. 五个 UAT case ID 固定且每个候选每项只写一次；任一失败拒绝候选。
4. 五类签署必须角色匹配、签署人与类别唯一、创建者不能自签；任一拒绝终止候选。
5. 灰度不得跳级；每个阶段观察至少 60 秒，并记录安全摘要而非问题正文。
6. 事件按候选单独哈希链接；所有动作同步写租户治理审计链。
7. 本地编排器禁用于 staging/production；正式流量由外部发布平台控制。

## 非功能需求

- 租户从可信 Principal 获取；所有查询含 tenant scope。
- 外部 v1 问答契约冻结；S7 仅新增 `/admin/releases` 管理 API。
- 指标证据不得含用户、问题、文档正文或高基数标签。
- P0/P1、安全事件、越权泄漏门槛不可被客户端覆盖。
- Release 数据可审计、可重现、可导出，但本地数据不是生产验收。

## 不在本地范围

真实企业 UAT、生产镜像签名/registry attestation、Kubernetes 流量切分、真实 Pager、企业 CAB、生产数据库迁移、真实 Provider/账单和具名签字。它们保持 Gate 阻断，不能以合成记录替代。
