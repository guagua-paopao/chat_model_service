# ADR-036：高风险治理操作使用租户级哈希链审计

- 状态：Accepted
- 日期：2026-07-16
- Owner：Security / Audit / DBA

## 背景

普通审计行可以被拥有数据库写权限的人修改且难以发现。配置、身份、配额和事件操作需要顺序、原因、审批号和可验证完整性，同时不得把 Prompt、密钥或敏感正文复制进审计。

## 决策

- 高风险动作写入独立 `governance_audit_logs`；每租户 sequence 连续，事件 hash 覆盖前序 hash、actor、action、resource、result、reason、approval、request/trace、安全详情和时间。
- 写入前锁定 tenant 行，保证同租户链顺序；API 只提供读取和完整性验证，不提供修改/删除。
- `details_safe` 使用白名单，禁止 raw Prompt、Token、Secret、文档正文和完整请求体。
- 普通操作审计表继续存在；哈希链只覆盖 S5 治理动作。

## 后果

无意或事后篡改可以检测，但数据库管理员仍可重写整条链。生产必须把事件持续导出到企业 WORM/SIEM、分离应用与审计写权限并演练留存/法务封存；在此之前不宣称不可抵赖。

