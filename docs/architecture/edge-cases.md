# Pingce 边界情况分析

**版本**: 1.0.0 | **日期**: 2026-11-05 | **关联**: `maintainability.md`、`module-map.md`、`task-index.md`

边界情况不是“测试补充”，而是**设计输入**。每个边界必须有明确期望行为，不能靠“看情况”。

---

## 1. 分类法

| # | 类别 | 典型场景 | 默认处理 |
|---|---|---|---|
| 1 | 空/零值 | 空数据集、空字符串、null、whitespace | 明确拒绝或标记 empty，禁止静默通过 |
| 2 | 单例/最小 | 1 条样本、1 个字符、1 个租户 | 正常运行，但提示统计不可用 |
| 3 | 上限/溢出 | max+1、超大 payload、深嵌套、整数溢出 | 拒绝并给出边界值 |
| 4 | 重复/幂等 | 重复提交、重复投递、重复样本 | 幂等键 + 唯一约束 |
| 5 | 并发/竞态 | 并发发布、双 Run、丢更新 | 乐观锁/唯一约束/事务 |
| 6 | 部分失败 | 批量一半失败、部分 item 失败 | 明确状态 + 可续传，禁止整批静默丢 |
| 7 | 超时/取消 | 外部超时、用户取消、连接断开 | 超时 + 取消信号 + 保留已完成 |
| 8 | 依赖故障 | DB/Redis/OSS/Qdrant/LLM 挂 | 降级/熔断/重试/明确错误 |
| 9 | 恶意/对抗 | 注入、SSRF、Zip bomb、ReDoS、路径穿越 | 白名单 + 限额 + 隔离 |
| 10 | 生命周期 | 删除、过期、恢复、孤儿 | 软删除 + 引用检查 + GC |
| 11 | 时间/时区 | UTC、DST、时钟偏移、2038 | 统一 UTC + 服务端时间 |
| 12 | 编码/Unicode | Emoji、归一化、GBK、RTL、零宽 | 规范化 + utf8mb4 + 显示清理 |
| 13 | 协议/契约 | 未知字段、版本不匹配、分页边界 | 严格校验 + 明确错误 |
| 14 | 权限/租户 | 跨租户、禁用租户、scope 不足 | 404 不泄露存在性 + 403 |

---

## 2. 通用边界值

| 维度 | 必测值 | 期望 |
|---|---|---|
| 数量 | 0、1、max-1、max、max+1 | 0 拒绝或标记；max+1 拒绝 |
| 字符串 | 空、1 字符、64KB、64KB+1 | 超限截断或拒绝，明确标注 |
| 分页 | limit=0、-1、1、max、max+1 | 非法值报参数错误，不静默修正 |
| JSON 深度 | 1、max、max+1 | 超限拒绝，防栈溢出 |
| 时间 | 过去、现在、未来、DST、闰秒 | 统一 UTC，禁止混用本地时间 |
| 数值 | 0、负数、NaN、Inf、精度边界 | NaN/Inf 拒绝；金额用 decimal |
| 并发 | 1、N、2N | 无丢更新、无重复副作用 |
| 重试 | 0、1、max、max+1 | 超过上限入 DLQ，不无限重试 |

---

## 3. 数据接入与数据集

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-DATA-01 | 数据源 0 行 | 允许创建空版本但标记 `empty=true`；评测拒绝空数据集 | 显式 `allow_empty`；评测前置校验 | 空源→创建→评测拒绝 | P1 |
| EC-DATA-02 | 仅 1 条样本 | 正常创建，统计提示样本量不足 | 统计层 `insufficient_data` | 1 条样本全流程 | P2 |
| EC-DATA-03 | 重复 `sample_key` | 去重并计数，不报错 | 唯一键 + 计数 | 重复样本批量写入 | P1 |
| EC-DATA-04 | 内容完全相同重复发布 | 返回已有版本（`content_hash` 相同） | 内容哈希去重 | 同内容发布两次 | P1 |
| EC-DATA-05 | 单条 payload > 1MB | 存 OSS，DB 只存引用 | artifact 引用 | 大 payload 写入 | P1 |
| EC-DATA-06 | JSON 行格式错误 | 整批回滚，报告行号 | 事务 + 行级错误 | 第 500 行损坏 | P0 |
| EC-DATA-07 | 编码混合（UTF-8/GBK/BOM） | 检测并规范化；无法判定则拒绝 | 编码探测 + 显式配置 | GBK + BOM 文件 | P1 |
| EC-DATA-08 | Schema 漂移（新增/删除/改类型） | 默认阻断，需人工确认 | schema diff + 策略 | 新增字段/改类型 | P0 |
| EC-DATA-09 | 必填字段 null/缺失 | 校验失败，指出字段与行号 | Schema 校验 | 缺字段样本 | P1 |
| EC-DATA-10 | JSON 嵌套深度超限 | 拒绝，防 DoS | 深度上限（如 32） | 深嵌套 payload | P0 |
| EC-DATA-11 | CSV 公式注入 `=cmd` | 导出时转义 | 导出编码规则 | 含公式的单元格 | P1 |
| EC-DATA-12 | 并发发布同一数据集 | 一个成功，另一个返回已有版本 | 唯一约束 `(dataset, version)` | 并发发布 | P0 |
| EC-DATA-13 | 发布中样本写入失败 | 事务回滚，不产生半版本 | 单事务 + 行数校验 | 注入写入失败 | P0 |
| EC-DATA-14 | 删除被 Run 引用的数据集 | 软删除；Run 仍可读；硬删除需归档 | 引用检查 | 删除后读 Run | P1 |
| EC-DATA-15 | 版本保留到期但被 Run 引用 | 延长保留或墓碑，不破坏 Run | 引用保护 | 到期清理任务 | P0 |
| EC-DATA-16 | 源端删除/重命名 | 同步失败并给出明确错误，水位保留 | 连接器错误分类 | 源消失后续传 | P1 |
| EC-DATA-17 | 水位乱序/回退 | 检测并告警，不静默重跑 | 水位单调校验 | 注入旧水位 | P0 |
| EC-DATA-18 | 同步中断后恢复 | 从水位续传，不重复 | 幂等键 + 水位 | 中断再恢复 | P0 |
| EC-DATA-19 | 源端 429/5xx | 退避重试，最终 DLQ | 错误分类 + 重试 | 模拟 429 | P1 |
| EC-DATA-20 | 分页 cursor 循环 | 检测重复 cursor 并中止 | cursor 去重/最大页数 | 源端返回相同 cursor | P1 |

---

## 4. 评测执行

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-EVAL-01 | 空数据集 | 拒绝 `EMPTY_DATASET` | 创建 Run 前校验 | 空数据集启动 | P1 |
| EC-EVAL-02 | 仅 1 条样本 | 成功，标注样本量不足 | 统计提示 | 1 条样本 Run | P2 |
| EC-EVAL-03 | 全部 item 失败 | `failed`；部分失败 `succeeded_with_errors` | 状态机 | 全失败/半失败 | P0 |
| EC-EVAL-04 | 模型返回空字符串 | 记录 raw，按规则评分或 item error | 空值校验 | 空输出 | P1 |
| EC-EVAL-05 | 要求 JSON 但返回非法 JSON | 重试 1 次，仍失败 item error | Schema 校验 | 非法 JSON | P1 |
| EC-EVAL-06 | 输出被 max_tokens 截断 | 标记 `truncated`，评分可算但标注 | finish_reason | 截断输出 | P1 |
| EC-EVAL-07 | 上下文超长 | item error，不重试 | 错误分类 | 超长输入 | P1 |
| EC-EVAL-08 | Provider 429 | 退避 + `Retry-After`，不重复计费 | 限流 + 幂等 | 模拟 429 | P0 |
| EC-EVAL-09 | Provider 超时 | 重试后 error，记录 attempt | 三层超时 | 模拟超时 | P1 |
| EC-EVAL-10 | Judge 分数越界 | item error，不静默 clamp | 范围校验 | 返回 1.5 | P0 |
| EC-EVAL-11 | Judge 拒答/非数字 | item error + 人工队列 | 输出 Schema | 返回文本 | P1 |
| EC-EVAL-12 | Judge 被注入 | 输出作为数据，Schema 校验，不执行 | 数据隔离 | 样本含指令 | P0 |
| EC-EVAL-13 | temperature > 0 / seed 不支持 | Manifest 记录；复现门禁只覆盖规则/temp=0 | Manifest 标注 | 非零温度重放 | P1 |
| EC-EVAL-14 | 重复 `client_request_id` | 同一 `run_id`，不重复计费 | 幂等键 | 重复提交 | P0 |
| EC-EVAL-15 | 取消 mid-run | 停止取新 item，保留已完成 | 取消信号 | 取消 50% | P1 |
| EC-EVAL-16 | Worker 崩溃 mid-item | 幂等重试，不重复 score/billing | 幂等键 + ack | kill worker | P0 |
| EC-EVAL-17 | 超预算 | 暂停 `paused_budget`，可恢复 | 预算校验 | 低预算 Run | P1 |
| EC-EVAL-18 | 基线缺失 | `BASELINE_MISSING`，不通过 | 前置校验 | 无基线对比 | P1 |
| EC-EVAL-19 | 对比不可比 Run | 拒绝（不同 suite/dataset/metric） | 兼容性校验 | 跨 Suite 对比 | P0 |
| EC-EVAL-20 | 样本量不足 | `insufficient_data`，不通过 | 样本量下限 | 10 条样本门禁 | P1 |
| EC-EVAL-21 | 基线全 0 | 用绝对差值或 N/A，禁止除零 | 安全除法 | baseline=0 | P1 |
| EC-EVAL-22 | NaN/Inf 指标 | 拒绝写入 | 数值校验 | 注入 NaN | P0 |
| EC-EVAL-23 | 数据集 hash 不匹配 | Run 标记 invalid | Manifest 校验 | 篡改版本 | P0 |
| EC-EVAL-24 | 模型版本变化 | 对比标记 `not_comparable`，需重冻结 | 版本 pinning | 切换模型 | P0 |

---

## 5. MCP 接入

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-MCP-01 | 缺少 Authorization | 401 | 认证中间件 | 无头请求 | P1 |
| EC-MCP-02 | Bearer 格式错误 | 401 | 解析校验 | `Bearer x` | P1 |
| EC-MCP-03 | Key 过期/吊销 | 401 | 生命周期校验 | 过期/吊销 | P1 |
| EC-MCP-04 | 跨租户资源 | 404（不泄露存在性） | 租户过滤 | 租户 A 查 B | P0 |
| EC-MCP-05 | scope 不足 | 403 + `required_scope` | scope 校验 | 缺 read_content | P1 |
| EC-MCP-06 | 未知工具 | tool not found | allowlist | 调用不存在工具 | P1 |
| EC-MCP-07 | 写工具名 | 不存在（无写工具） | allowlist + CI 快照 | 调用 `start_eval_run` | P0 |
| EC-MCP-08 | 畸形 JSON-RPC | `-32700` | 解析层 | 非法 JSON | P1 |
| EC-MCP-09 | 未知方法 | `-32601` | 路由 | 未知 method | P1 |
| EC-MCP-10 | 参数非法 | `-32602` | Pydantic 校验 | 类型错误 | P1 |
| EC-MCP-11 | 请求 > 256KB | 413 | 请求体上限 | 大请求 | P1 |
| EC-MCP-12 | 结果 > 64KB | 截断 + cursor 或 `RESULT_TOO_LARGE` | 限额 | 大 Schema | P1 |
| EC-MCP-13 | 游标篡改 | `INVALID_CURSOR` | HMAC | 改 cursor | P0 |
| EC-MCP-14 | 游标过期 | `INVALID_CURSOR` | TTL | 15 分钟后 | P1 |
| EC-MCP-15 | 游标跨租户/跨查询 | `INVALID_CURSOR` | tenant + query hash | 复用 cursor | P0 |
| EC-MCP-16 | 最后一页 | 空列表 + 无 `next_cursor`，不是错误 | 分页 | 末页请求 | P2 |
| EC-MCP-17 | 限流 | 429 + `Retry-After` | 令牌桶 | 超阈值 | P1 |
| EC-MCP-18 | Redis 故障 | 本地兜底，更严格 | 降级 | 停 Redis | P1 |
| EC-MCP-19 | 只读副本延迟 | `as_of` 标注 | 读副本 | 延迟注入 | P2 |
| EC-MCP-20 | DB 故障 | 503 + `Retry-After` | 健康检查 | 停 DB | P1 |
| EC-MCP-21 | 协议版本不支持 | 明确错误 | 版本协商 | 旧/新版本 | P1 |
| EC-MCP-22 | SSE 客户端断开 | 清理资源，无泄漏 | 上下文取消 | 中途断开 | P2 |
| EC-MCP-23 | 并发 20 请求 | 独立、无串扰 | 无全局可变状态 | 压测 | P1 |
| EC-MCP-24 | 样本含注入文本 | 作为数据返回 | 内容标记 | 注入样本 | P0 |
| EC-MCP-25 | PII | 脱敏 | PII 规则 | 手机号/邮箱 | P0 |
| EC-MCP-26 | `include_io` 无 scope | 403 | 独立 scope | 缺 read_content | P1 |
| EC-MCP-27 | limit 溢出/负数 | 参数错误 | 边界校验 | 0/-1/max+1 | P1 |
| EC-MCP-28 | 可选字段缺失 | 使用默认值 | Schema default | 省略 limit | P3 |
| EC-MCP-29 | 重复读请求 | 幂等同结果 | 只读 | 重复调用 | P2 |
| EC-MCP-30 | 参数 Unicode 超长 | 长度校验拒绝 | maxLength | 10 万字符 | P1 |

---

## 6. 认证与租户

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-IDN-01 | 租户被禁用 | 403 | 租户状态校验 | 禁用后请求 | P1 |
| EC-IDN-02 | 租户被删除 | 404 | 软删除 + 过滤 | 删除后请求 | P1 |
| EC-IDN-03 | Key 轮换重叠 | 新旧都有效，旧到期吊销 | 双 Key 窗口 | 轮换 | P2 |
| EC-IDN-04 | 吊销缓存 | ≤60 秒生效 | TTL | 吊销后立即请求 | P1 |
| EC-IDN-05 | 通配 scope | 拒绝签发/拒绝认证 | 白名单 | `*` scope | P0 |
| EC-IDN-06 | 跨租户 ID 猜测 | 404 | 强制租户过滤 | 遍历 ID | P0 |
| EC-IDN-07 | JWT audience 不匹配 | 401 | `aud` 校验 | 错误 audience | P0 |
| EC-IDN-08 | Token passthrough | 拒绝 | 受众校验 | 转发他人 token | P0 |
| EC-IDN-09 | 同名 Key 并发创建 | 允许，`key_id` 唯一 | 唯一键 | 并发创建 | P2 |
| EC-IDN-10 | 删除最后一个管理员 | 阻止并提示 | 业务规则 | 删除最后 admin | P1 |

---

## 7. 存储与生命周期

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-AST-01 | OSS 故障 | 重试后 503，不写半条 DB | 重试 + 事务顺序 | 停 OSS | P1 |
| EC-AST-02 | 预签名过期 | 403 | TTL | 过期后访问 | P2 |
| EC-AST-03 | checksum 不匹配 | 拒绝读 + 告警 | sha256 校验 | 篡改对象 | P0 |
| EC-AST-04 | 孤儿 artifact | GC 清理 | 引用扫描 | 删除引用 | P2 |
| EC-AST-05 | DB 引用缺失 artifact | 明确报错，不崩溃 | 存在性检查 | 删对象 | P1 |
| EC-AST-06 | 文件名路径穿越 | 规范化/拒绝 | key 白名单 | `../../x` | P0 |
| EC-AST-07 | 超大上传 | 413 | 大小上限 | > 限制 | P1 |
| EC-AST-08 | 并发覆盖同 key | 版本化或拒绝 | 条件写 | 并发 put | P1 |
| EC-AST-09 | public bucket | 启动检查失败 | 策略校验 | 设 public | P0 |
| EC-AST-10 | MinIO/OSS 切换 | 同一契约测试通过 | Storage SPI | 双适配器 | P1 |
| EC-AST-11 | 生命周期删除 vs 引用 | 先检查引用 | 引用保护 | 到期删除 | P0 |
| EC-AST-12 | 恢复后数据校验 | 全量抽检 checksum | 恢复演练 | PITR 恢复 | P1 |

---

## 8. 检索

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-SRC-01 | Qdrant 故障 | 关键词降级 `degraded=true` | 熔断 + 降级 | 停 Qdrant | P1 |
| EC-SRC-02 | 空 query + 无过滤 | `INVALID_ARGUMENT` | 参数校验 | 空查询 | P2 |
| EC-SRC-03 | 无结果 | 空列表，不是错误 | 正常返回 | 无匹配 | P3 |
| EC-SRC-04 | top-k 超限 | clamp 或参数错误 | 边界校验 | k=1000 | P1 |
| EC-SRC-05 | 跨租户 | 空结果 | payload 过滤 | 跨租户查询 | P0 |
| EC-SRC-06 | Embedding 模型变更 | 阻断检索直到重建完成 | 版本 + 别名 | 切模型 | P0 |
| EC-SRC-07 | payload 含 PII | 写入拒绝 | 最小化 payload | 含手机号 | P0 |
| EC-SRC-08 | 重复 point | upsert 幂等 | 稳定 ID | 重复索引 | P2 |
| EC-SRC-09 | Qdrant 超时 | 降级 | 超时/熔断 | 慢查询 | P1 |
| EC-SRC-10 | 重建中查询 | 别名切换，无停机 | 双写 + alias | 重建 | P1 |

---

## 9. 报告与门禁

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-REP-01 | 无指标 | `no_data` | 空态 | 空 Run | P2 |
| EC-REP-02 | 全部失败 | 失败摘要，不显示 0 分 | 状态优先 | 全失败 Run | P1 |
| EC-GAT-01 | 基线缺失 | `baseline_missing` | 前置校验 | 无基线 | P1 |
| EC-GAT-02 | 样本量不足 | `insufficient_data`，不通过 | 下限 | 小样本 | P1 |
| EC-GAT-03 | 指标方向配置错误 | 启动校验失败 | 配置校验 | 反向配置 | P1 |
| EC-GAT-04 | 除零 | N/A 或绝对差值 | 安全除法 | baseline=0 | P1 |
| EC-GAT-05 | 离群值主导 | 中位数/分位数 + 分布 | 统计选择 | 极端样本 | P1 |
| EC-GAT-06 | 不可比 Run | 拒绝 | 兼容性校验 | 跨 Suite | P0 |
| EC-REP-03 | 运行中生成报告 | `partial` 标注 | 状态检查 | 运行中导出 | P2 |
| EC-REP-04 | 大导出 | 流式导出 | 分页/流式 | 10 万行 | P1 |
| EC-GAT-07 | 门禁误拦 | 可解释 + 人工复核 | 证据 + 阈值 | 边界样本 | P1 |
| EC-GAT-08 | 门禁漏拦 | 告警 + 复盘 | 监控 | 注入劣化 | P1 |

---

## 10. 可视化功能测试

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-FUN-01 | 浏览器崩溃 | 重试一次，仍失败入 DLQ | 沙箱重启 | kill 进程 | P1 |
| EC-FUN-02 | 页面超时 | 强杀并记录证据 | 超时 | 卡死页面 | P1 |
| EC-FUN-03 | 截图过大 | 压缩/限制尺寸 | 后处理 | 4K 截图 | P2 |
| EC-FUN-04 | 视觉差异阈值边界 | 明确 pass/fail，不抖动 | 固定阈值 + 环境 | 阈值±1px | P1 |
| EC-FUN-05 | 字体/渲染差异 | 固定镜像与字体 | 环境 pinning | 跨机器 | P1 |
| EC-FUN-06 | 网络抖动 | 幂等步骤重试 | 重试策略 | 丢包 | P2 |
| EC-FUN-07 | 沙箱逃逸 | 阻止并告警 | 容器隔离 | 逃逸尝试 | P0 |
| EC-FUN-08 | 白名单外请求 | 拒绝 | 网络策略 | 外部域名 | P0 |
| EC-FUN-09 | 录屏超限 | 限制时长/分辨率 | 采集策略 | 长时录制 | P2 |
| EC-FUN-10 | 并发浏览器任务 | 资源隔离 | 独立容器 | 10 并发 | P1 |

---

## 11. 安全与对抗

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-SEC-01 | SQL 注入 | 参数化，拒绝拼接 | ORM/参数化 | 注入样本 | P0 |
| EC-SEC-02 | SSRF | 私网 IP 黑名单 + 域名白名单 | 出口代理 | 内网 URL | P0 |
| EC-SEC-03 | Zip/解压炸弹 | 大小/深度限制 | 流式解压 | 炸弹文件 | P0 |
| EC-SEC-04 | ReDoS | 正则超时/安全引擎 | 超时/预编译 | 恶意正则输入 | P0 |
| EC-SEC-05 | 路径穿越 | 规范化 + 白名单 | key 校验 | `../` | P0 |
| EC-SEC-06 | 日志注入 | 结构化日志 + 转义 | JSON 日志 | 换行/控制字符 | P1 |
| EC-SEC-07 | Header 注入 | 白名单 | 响应头校验 | CRLF | P1 |
| EC-SEC-08 | Prompt 注入 | 数据隔离 + 不执行 | 结构化包裹 | 指令样本 | P0 |
| EC-SEC-09 | CSV 公式注入 | 导出转义 | 导出规则 | `=cmd` | P1 |
| EC-SEC-10 | 资源耗尽 | 配额 + 超时 | 限额 | 大请求/高并发 | P0 |
| EC-SEC-11 | 依赖投毒 | lockfile + 审计 | 供应链审查 | 恶意包 | P0 |
| EC-SEC-12 | 密钥泄露 | 扫描 + 轮换 | secret 管理 | 误提交 | P0 |

---

## 12. 时间 / 数值 / Unicode

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-GEN-01 | 时区/DST | 统一 UTC | `DATETIME(6)` + UTC | 跨时区 | P1 |
| EC-GEN-02 | 客户端时钟偏移 | 服务端时间为准 | 服务端生成时间 | 伪造时间 | P1 |
| EC-GEN-03 | 2038 | 不溢出 | `DATETIME` 非 `TIMESTAMP` | 边界日期 | P1 |
| EC-GEN-04 | 浮点精度 | 金额用 decimal，四舍五入明确 | Decimal | 0.1+0.2 | P1 |
| EC-GEN-05 | NaN/Inf | 拒绝 | 数值校验 | 注入 NaN | P0 |
| EC-GEN-06 | 整数溢出 | 边界校验 | 上限/类型 | max+1 | P1 |
| EC-GEN-07 | Emoji/代理对 | 正常存储 | `utf8mb4` | 四字节字符 | P1 |
| EC-GEN-08 | Unicode 归一化 | 入库 NFC | `unicodedata.normalize` | 组合字符 | P2 |
| EC-GEN-09 | 中文排序/大小写 | 明确 collation | 索引列 `as_cs` | `A` vs `a` | P1 |
| EC-GEN-10 | 零宽/RTL | 显示清理，数据保留 | 展示层过滤 | 零宽字符 | P2 |
| EC-GEN-11 | 超大整数 ID | 用字符串 | ID 类型 | 2^63+ | P2 |

---

## 13. 部署与升级

| ID | 场景 | 期望行为 | 处理策略 | 测试 | 级别 |
|---|---|---|---|---|---|
| EC-OPS-01 | 滚动发布 N-1 schema | 新旧版本都能读写 | expand-contract | 双版本并存 | P0 |
| EC-OPS-02 | 在途任务遇发布 | 优雅停机，任务不丢 | drain + ack | 发布时跑任务 | P1 |
| EC-OPS-03 | 迁移失败 | 回滚 + 告警 | 事务/备份 | 注入失败 | P0 |
| EC-OPS-04 | Feature flag 关闭 | 回到旧行为 | 开关 | 关闭实验 | P1 |
| EC-OPS-05 | 缓存过期 | 版本化 key，避免脏读 | key 版本 | 发布后读 | P2 |
| EC-OPS-06 | 回滚遇新列 | 应用容忍额外列 | 向后兼容 | 回滚 | P0 |
| EC-OPS-07 | PITR 恢复 | 一致性校验 | 恢复演练 | 恢复到时间点 | P1 |
| EC-OPS-08 | 发布后队列积压 | 扩容/告警 | 监控 | 积压 | P1 |

---

## 14. 状态机边界

### Run

```text
queued → dispatching → running → succeeded
                              ├→ succeeded_with_errors
                              ├→ failed
                              ├→ cancelled
                              ├→ timed_out
                              └→ paused_budget → running
```

非法迁移（必须拒绝）：

- `succeeded` → `running`
- `cancelled` → `succeeded`
- `failed` → `succeeded`（不允许人工改状态）
- `timed_out` → `running`（只能新建 Run）

要求：状态迁移必须带乐观锁（`version` 列），并发更新只允许一个成功。

### Job

```text
pending → running → succeeded
                 ├→ failed → retrying → running
                 ├→ cancelled
                 └→ dead_letter
```

要求：`retrying` 次数有上限；`dead_letter` 只能重放，不能原地复活。

---

## 15. 并发与幂等

| 场景 | 风险 | 处理 |
|---|---|---|
| 同一 Run 重复提交 | 双倍成本 | `client_request_id` 幂等键 |
| 同一数据集并发发布 | 版本号冲突 | 唯一约束 + 事务 |
| 同一 item 重复投递 | 重复评分/计费 | `hash(run_id,item_id,attempt)` |
| 删除与读取并发 | 读到半删除状态 | 软删除 + 事务隔离 |
| 两个 Worker 抢同一任务 | 重复执行 | `acks_late` + 幂等 |
| 游标并发翻页 | 重复/漏项 | 稳定排序 + keyset |
| 配额并发扣减 | 超卖 | 原子扣减/Lua |
| 缓存与 DB 并发更新 | 脏读 | 版本号/失效策略 |

---

## 16. 依赖故障矩阵

| 依赖 | 故障 | 系统行为 | 降级 | 恢复 |
|---|---|---|---|---|
| MySQL 主库 | 不可用 | 写失败，返回 503 | 只读功能可用 | 自动重连 + 告警 |
| MySQL 只读副本 | 延迟/不可用 | 读走主库或返回 `as_of` | 降级读 | 恢复后切回 |
| Redis | 不可用 | 限流本地兜底；队列暂停 | 更严格限流 | 重启 + 告警 |
| OSS | 不可用 | 上传/下载 503 | 重试 | 恢复后补传 |
| Qdrant | 不可用 | 语义检索降级关键词 | `degraded=true` | 重建/切回 |
| LLM Provider | 429/5xx/超时 | 重试/熔断/切备用 | 规则指标或暂停 | 恢复后继续 |
| LiteLLM | 不可用 | 所有模型调用失败 | 快速失败 + 明确错误 | 重启 |
| IdP | 不可用 | OAuth 登录失败；API Key 不受影响 | API Key 兜底 | 恢复 |

---

## 17. 边界测试落地

- 每个 **P0/P1** 场景必须有自动化用例；P2/P3 可人工验证。
- 命名：`test_ec_<domain>_<id>_<scenario>`。
- 使用表驱动，避免复制粘贴。
- 禁止依赖真实 LLM/OSS/Qdrant；使用 fake 或 testcontainers。
- 禁止 `sleep`；使用可控时钟与超时注入。
- CI Job：`edge-suite`，目标 < 10 分钟。
- 对应任务：`QUAL-05`（见 `docs/planning/tasks/05-quality.md`）。

---

## 18. 评审问题清单

新增功能/接口时，必须回答：

1. 空输入会怎样？
2. 只有一个元素会怎样？
3. 超过上限 1 会怎样？
4. 重复提交会怎样？
5. 两个请求同时来会怎样？
6. 一半失败会怎样？
7. 超时/取消会怎样？
8. 依赖挂了会怎样？
9. 恶意输入会怎样？
10. 删除/过期会怎样？
11. 时区/编码/浮点会怎样？
12. 升级/回滚会怎样？

答不上来的，不允许进入实现。

---

## 19. 红线

- 边界行为未定义就上线
- 用 catch-all 吞掉异常
- 静默 clamp / 截断 / 修正用户输入
- 测试依赖真实外部服务
- 只测正常路径
- 写操作没有幂等键
- 分页/导出没有上限
- 外部调用没有超时
- 跨租户只靠前端过滤
- 删除不做引用检查
