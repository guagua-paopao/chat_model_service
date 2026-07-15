# ADR-024：生产摄取 Adapter 与数据路由 Fail-Fast

- 状态：Accepted
- 日期：2026-07-16

## 背景

Fake Embedding、本地文件存储和简单签名扫描适合可重复开发，但没有生产语义。若配置遗漏时静默回退，会把演示能力误部署为安全控制。

## 决策

staging/production 启动时强制：S3 object store + HTTPS internal/public endpoints、平台预建不同 bucket、非空凭据；批准的 HTTPS Embedding endpoint/key/model；外部 ClamAV；禁用 Fake Embedding、本地存储、签名扫描和应用自动建 bucket。

即使外部 Embedding 已配置，`confidential/restricted` 仍在调用前拒绝。只有未来经数据 Owner、Security/Legal、区域/DPA/保留政策批准的私有路由 ADR 才能改变。

## 后果

错误配置在启动阶段暴露，不产生隐性降级。代价是 Helm 示例必须依赖平台 Secret、S3 和 ClamAV，且没有这些依赖时不能“先跑起来”；这是有意的安全属性。

