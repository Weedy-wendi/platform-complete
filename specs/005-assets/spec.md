# Feature Specification: assets（M03）

**Feature**: `005-assets` | **Phase**: P0a | **Status**: Implemented

**任务**: AST-01 ~ AST-05（`docs/planning/tasks/00-foundation.md`）

---

## 1. 模块职责

统一对象存储抽象（云 OSS / MinIO），负责预签名、校验、生命周期。业务模块不直接依赖厂商 SDK。

## 2. 为什么做

数据集大文件、评测原始响应、报告快照、功能测试截图/录屏都需要对象存储；MySQL 不存二进制。

## 3. 功能需求

- **FR-001** `Storage` SPI：put/get/delete/presign；可替换。
- **FR-002** OSS 与 MinIO 适配器行为一致；禁止 public bucket；读取一律预签名。
- **FR-003** 预签名 TTL ≤15 分钟；读取校验 `sha256`。
- **FR-004** `artifact` 元数据：`s3_key`、大小、`sha256`、`mime`、租户隔离。
- **FR-005** Key 规范：`tenant/{tenant_id}/{asset_type}/{asset_id}/{version}/{filename}`。
- **FR-006** 4xx 不重试；网络/5xx 可重试。
- **FR-007** 业务代码只 import `Storage`，不得 import `oss2`/`boto3`。

## 4. 验收场景

1. **Given** 一个 artifact，**When** put→get，**Then** checksum 一致。
2. **Given** 预签名 URL 过期，**When** 访问，**Then** 403。
3. **Given** 租户 A 的 key 前缀，**When** 租户 B 访问，**Then** 拒绝。
4. **Given** OSS 超时，**When** 写入，**Then** 返回可重试错误；4xx 不重试。

## 5. 关键实体

`artifact`。

## 6. 边界与异常

- 大文件、网络超时、checksum 不匹配、预签名过期、public bucket、跨租户 key。

## 7. 不在范围

- CDN、图片处理、生命周期归档策略的具体实现。

## 8. 依赖

`002-core`（配置/租户）、`004-audit`（可选审计）。
