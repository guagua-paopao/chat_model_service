# 开发教学与测试计划

## 教学路径

1. 使用治理管理员创建通过的 S7 评测运行。
2. 使用 Release Manager 冻结候选，比较 API 返回的服务端派生版本和 `artifact_checksum`。
3. 使用 Business persona 写入 UC-01～05，重复同一 case，观察 `UAT_RESULT_IMMUTABLE`。
4. 分别使用 product/business/data/security/sre persona 签署；用错误角色签署，观察 fail-closed。
5. 启动 dark，依次传入健康观察窗口至 100%，验证事件 hash 唯一且链有效。
6. 创建第二候选，把错误率设为 5%，验证 `auto_stop`；再执行人工 rollback。
7. 把安全事件设为 1，验证直接 `auto_rollback`。
8. 禁用 `QA_LOCAL_RELEASE_ORCHESTRATOR_ENABLED`，验证写 API 返回 503。

## 自动测试

- 单元/集成：状态机、角色、租户、不可变、阈值、事件哈希、fail-closed。
- 契约：8 条新增路径与 `ReleaseCandidateCreate` 字段对齐。
- 迁移：0008 `up/down/up`；PostgreSQL Compose upgrade head。
- Web：ESLint、TypeScript、Next production build、BFF allowlist。
- 全栈：`scripts/smoke_s7.py` 完成评测→候选→UAT→五签→dark→100%→auditor readback。
- 回归：S4 门禁、S4/S5/S6 smoke、S6 故障/恢复工具不退化。

## 故障实验

- 质量差异 -5%、错误率 5%、TTFT 4 秒分别应自动停止。
- 任一安全事件或未授权泄漏应自动回滚。
- 跳过 5% 直接到 25% 应 409。
- UAT/签署重复、创建者自签、错误类别角色应拒绝。
- 篡改测试数据库中的任一 rollout event 后，完整性应为 false。
