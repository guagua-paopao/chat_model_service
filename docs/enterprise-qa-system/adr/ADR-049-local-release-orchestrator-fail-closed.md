# ADR-049：本地发布编排器在正式环境 fail-closed

状态：Accepted（2026-07-16）。

## 决策

内置发布编排器只允许 `local/test/dev`。`staging/production` 若启用则启动失败；禁用时所有发布写操作返回 `EXTERNAL_RELEASE_CONTROLLER_REQUIRED`，只读证据仍可保留。

## 理由与后果

应用数据库不能替代 Argo Rollouts、Flagger 或企业部署平台。目标环境必须由外部控制器执行流量切换、凭据、集群策略和回滚。
