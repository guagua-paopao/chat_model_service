# ADR-013：可复现依赖与零已知高风险漏洞门禁

- Status：Accepted
- Decision date：2026-07-15
- Owners：Platform / Security / All Engineers
- Review date：每季度或供应链平台变更时

## Context

企业应用的构建结果必须可追溯。仅声明宽松版本范围会导致开发机、CI 和镜像使用不同依赖；没有自动化审计会把已知漏洞带入发布物。

## Decision

Python 运行依赖使用精确版本 `requirements.lock`，Node 使用 `package-lock.json` 与 `npm ci`；容器基础镜像和基础设施镜像使用明确版本标签。CI 执行 Ruff、Mypy、测试覆盖率门槛、迁移往返、`pip-audit`、`npm audit`、Gitleaks 和四个镜像构建。

S1 门槛为运行依赖和 Web 依赖在审计时无已知漏洞；无法立即修复的漏洞必须有具名风险接受、影响分析、补偿控制和到期日。锁文件变化必须与代码一起评审。

## Alternatives

- 每次安装最新兼容版本：不可复现且可能意外破坏构建。
- 只依赖人工季度扫描：反馈过慢。
- 忽略开发依赖：开发工具也可能执行不可信输入，仍需跟踪；发布阻断优先评估运行路径。

## Consequences

需要持续升级和处理生态误报。版本标签仍可能被上游重写；生产阶段应进一步生成 SBOM、签名镜像并使用 digest 固定基础镜像。

