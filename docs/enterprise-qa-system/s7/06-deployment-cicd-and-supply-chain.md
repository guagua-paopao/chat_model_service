# 部署、CI/CD 与供应链

## 候选流水线合同

1. checkout 固定 SHA；测试、契约、迁移、依赖/secret 扫描通过。
2. 构建一次 API/Web/Worker 镜像并推送不可变 digest。
3. 为实际镜像生成 SPDX/CycloneDX SBOM、provenance 和无密签名。
4. 在隔离 staging 拉取同一 digest，执行迁移、smoke、UAT 和回滚演练。
5. 将 CI run、registry attestation、评测、迁移和 rollback target 组装为候选。
6. 外部控制器按审批和观察窗口逐级放量；应用 API 只保存/展示证据。

## 当前实现

- CI 已执行 Python/Web/供应链基线；S7 新增 API/迁移/契约自动测试。
- Compose 与 Helm 版本更新为 `0.7.0-s7`。
- Helm 显式 `QA_LOCAL_RELEASE_ORCHESTRATOR_ENABLED=false`。
- 本地候选接受 digest 格式并冻结清单，但不声称这些 digest 已由 registry 或签名系统验证。

## 生产缺口

GitHub environment 审批、真实 registry、SBOM/provenance/cosign 验证、Kubernetes staging、流量控制器、ExternalSecret/KMS、NetworkPolicy/Ingress、数据库前向修复演练、灾备和 CAB 记录均待企业环境接入，因此生产 Gate 为 NO-GO。
