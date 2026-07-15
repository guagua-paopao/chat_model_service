# Contracts

S1 继续采用 contract-first。当前唯一规范源是
[`docs/enterprise-qa-system/openapi.yaml`](../../docs/enterprise-qa-system/openapi.yaml)，不得复制一份后独立修改。

后续生成 TypeScript/Python 客户端时，输出到本目录的 `generated/`，并在 CI 中以“重新生成后工作区无差异”作为门禁。

