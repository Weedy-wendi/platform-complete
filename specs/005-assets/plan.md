# Implementation Plan: assets（M03）

**Feature**: `005-assets` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- S3 兼容 API；OSS 与 MinIO 两个适配器实现同一 `Storage` 协议。
- 预签名 URL；写入计算 `sha256`；元数据落 `artifact`。
- 配置：`OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY`、`OSS_SECRET_KEY`。

## 2. 数据模型

`artifact(id, tenant_id, asset_type, asset_id, version, s3_key, size_bytes, sha256, mime_type, created_at)`；`s3_key` 唯一。

## 3. 公开接口

`Storage`、`ArtifactService`；`ArtifactRef` DTO。

## 4. 测试策略

- 契约：put/get/presign/delete 双适配器同一套用例。
- 集成：checksum、TTL、超时重试。
- 安全：跨租户 key、public bucket、预签名越权。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 厂商锁定 | Storage SPI + 双适配 |
| 公开 bucket | 配置校验 + 测试 |
| 大文件内存 | 流式上传/下载 |
| 预签名泄露 | TTL/最小权限 |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | sha256/版本 |
| II 五原语 | Asset |
| III API/CLI First | 预签名供 REST/前端 |
| IV Boring Tech | S3 协议 |
| V 控制/执行分离 | 存储不执行任务 |
| VI 证据驱动 | 契约/安全测试 |
| VII 模块化单体 | 独立模块 |
