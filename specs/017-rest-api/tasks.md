# Tasks: REST / OpenAPI 接入层（P0d）

**Source of truth**: `docs/planning/task-index.md`（API-01 ~ API-10）。

- [X] API-01 FastAPI 骨架、`/v1` 路由、错误 envelope、`trace_id`、健康端点
- [X] API-02 认证/租户/RBAC/scope/限流中间件（API Key；JWT 预留）
- [X] API-03 项目/数据源/数据集/版本/样本接口（写操作 201/202）
- [X] API-04 评分器/Suite/Target 接口
- [X] API-05 Run 创建（202 + run_id）/查询/明细/对比/取消
- [X] API-06 Gate/报告/导出/功能测试接口
- [X] API-07 Badcase 检索接口（委托 SRC-05；`degraded`）
- [X] API-08 管理面：租户/用户/角色/API Key/Provider
- [X] API-09 OpenAPI 快照 + `openapi-typescript` 前端类型生成校验
- [X] API-10 契约/安全/性能测试（401/403/404、跨租户、分页、P95）

## 交付检查

- [X] `contracts/openapi.yaml` 与实现一致
- [X] 前端类型由 OpenAPI 生成，无手写镜像
- [X] 长任务 202 + 查询/SSE
- [X] 跨租户统一 404
- [X] 写操作审计

## Phase 2: Convergence

- [X] API-11 ????? actor/action/resource/trace_id?FR-015?missing?
- [X] API-12 datasources CRUD ???FR-006?partial?
- [X] API-13 suites/targets ?????FR-008?partial?
- [X] API-14 ?????????TTL/??????FR-009?partial?
