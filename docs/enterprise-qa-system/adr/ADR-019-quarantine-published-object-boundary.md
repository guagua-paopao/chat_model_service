# ADR-019：隔离区、发布区与服务端对象键

- 状态：Accepted
- 日期：2026-07-16

## 背景

上传内容、文件名、MIME、大小和哈希均来自不可信客户端。若 API 接收正文或直接写发布路径，会扩大内存/带宽、路径遍历和未扫描内容可见风险。

## 决策

正文使用短期预签名 PUT 进入 quarantine。quarantine 与 published 必须是不同 bucket。对象键仅由服务端 tenant/kb/document/version UUID 组成，filename 只存元数据。Worker 完成独立大小、SHA、MIME、恶意扫描、解析和 Embedding 后才复制到 published。

local Adapter 使用规范 Base64URL HMAC token 并做 resolved path scope；S3 Adapter 使用 SigV4 path-style presign。生产 bucket 由平台创建，应用不得 auto-create。

## 后果

优点：大文件数据面隔离、最小权限、未验证内容不可见、路径安全。代价：需要 CORS/IAM/KMS/lifecycle，且跨对象存储/DB 仍需处理 orphan。任何源路径保留或连接器同步必须复审键策略。

