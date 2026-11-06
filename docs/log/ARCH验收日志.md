# ARCH 验收日志

## 2026-10-23 系统架构与 API 契约冷启动验收报告（V1.0.0）

| 项 | 内容 |
| --- | --- |
| 审查产物 | `docs/ARCH-系统架构与API契约.md`（V1.0.0，契约冻结候选） |
| PRD 基线 | `docs/PRD-设备故障诊断智能体-V1.0.0.md`（V3.0.0，唯一业务权威） |
| 审查方式 | 冷启动；仅依据 PRD V3.0.0 与 ARCH V1.0.0 正文逐项核对；不读取实现代码，不假设文档未写明的行为 |
| 审查重点 | 契约完整性、RT-01~RT-20 状态机映射、边界一致性、SSE 契约、越权与边界、PRD 验收日志 §4.10 的 8 条 P1 遗留 |
| 最终判定 | **【驳回】** |
| P0 缺陷 | 3 项 |
| P1 缺陷 | 18 项 |

**门禁结论：契约 V1.0.0 不能冻结。存在“字段缺失、状态机分支不可执行、PRD 路由规则被接口实现反向阻断”三类 P0 问题；按本文现状直接开发，AC-IN-12、AC-RP-07、AC-HS-02 及 eval/批量状态隔离无法稳定通过。**

---

## A. 逐维度判定

| 审查维度 | 判定 | 结论摘要 |
| --- | --- | --- |
| 1. 契约完整性 | **不通过** | `auto_review`、`report_title`、`report_meta`、`input_fingerprint`、`interrupt_expires_at`、`execution_mode`、`failed_timeout`、`degraded_review`、`timed_out` 均已进入状态、投影或事件；但 `report_retry_count` 未进入任何 API 响应，`retry_count`/`review_round`/`duration_ms` 未按 PRD §4.5.2 映射；`nl` 创建接口与 RT-02/AC-IN-12 冲突 |
| 2. 状态机映射 | **不通过** | RT-05 优先于 RT-06~08、RT-08 优先于 RT-07 已正确实现；但 `route_after_parse` 返回 `row_failed`、`route_after_diagnose` 返回 `auto_review_report`/`auto_confirm_report`、`route_after_resume` 返回 `invalid`，均不在 route 枚举与图节点中；eval 缺失字段可落入 `clarify`，与 §3.6“eval 禁止 clarification”冲突 |
| 3. 边界一致性 | **部分通过** | 指纹计算时点、`active_fingerprint_key` 部分唯一索引、TTL 双机制、15s 无报告、`degraded`/`degraded_review` 缺项优先、`auto_review` 独立保留均已落文；但 KPI-03 未明确排除超时成功样本，进程重启对账未明确清空 `active_fingerprint_key`，TTL 过期未定义 SSE 事件 |
| 4. SSE 契约 | **通过（带 P1）** | 事件封套、`snapshot/step/status/interrupt/report/error/heartbeat`、批量事件、`Last-Event-ID` 回放、终态关闭、快照为最终事实均已定义；存在 schema 与示例不一致、`seq` 可为空等 P1 |
| 5. 越权与边界 | **通过** | 未写 `CREATE TABLE`/`CREATE INDEX` 等物理 DDL；§7 明确物理 DDL 由《数据库设计文档》承接；未发现把 PRD 规则阈值整体改写为技术实现；新增业务状态见 P1 |
| 6. P1 遗留处置 | **基本通过（部分不完整）** | 验收日志 §4.10 的 8 条均能在 ARCH §4.10 找到对应裁定，但 P1-02 对 KPI-03 仅写“超时单列”，未明确“不计入成功时延样本”；另有 5 条 UI/契约细节仍不完整 |

---

## B. P0 缺陷（阻断冻结）

### P0-01 自然语言入口缺失字段被 422 阻断，RT-02 与 AC-IN-12 无执行路径

**位置**

- ARCH §5.4.6“诊断 / 创建请求 / 变体 C：`nl`”： `nl` 的 6 个特征 + `device_id` 来自用户确认卡；服务端重新校验；**缺失即 422（不使用 clarification，因为已确认提交）**。
- ARCH §3.4 RT-02：关键特征缺失且入口为 NL/chat → `clarify`；§3.5 `route_after_parse` 也保留 `input_type in ("nl","chat") → clarify`。
- PRD §3.2.2 RT-02：关键特征缺失且入口为自然语言/对话 → 挂起 `clarification`，一次列出全部缺失字段、单位与示例。
- PRD 附录 B AC-IN-12：描述“3号机异响，扭矩 55，有点烫”，确认后进入 `clarification`，一次列出缺失的产品类型、空气温度、工艺温度、转速、刀具磨损；状态 `waiting_human`，`interrupt_type=clarification`。
- PRD §2.5.8：抽取确认卡“任一必填缺失时确认按钮禁用并提示”。

**缺陷说明**

1. PRD 内部在“缺失时确认按钮禁用”与 AC-IN-12“确认后进入 clarification”之间存在冲突；ARCH 必须显式裁定并登记，不能单方面选择 422。
2. 按 ARCH 当前实现，`nl` 只有 7 项齐备才能创建，RT-02 的 NL 分支永远不可达；AC-IN-12 无法通过。
3. ARCH §4.10 的 8 条 P1 处置表未列入该冲突，附录 F 也未登记；冻结后前端无法确定自然语言页签缺失时究竟应“阻止提交”还是“进入追问”。

**修复建议**

- 方案 A（推荐，保持 PRD 路由权威）：`POST /diagnoses` 的 `nl` 变体允许部分特征缺失；缺失时创建诊断（`input_fingerprint=null`、`active_fingerprint_key=null`，不参与 RT-17），由 `parse_input` 进入 `clarify`；`/nl/extract` 的 `recommended_action` 对 `partial` 返回 `clarify`。同步修改 `DiagnosisCreateRequest.nl` 的 `required` 与 JSON Schema，并补 AC-IN-12 的接口级断言。
- 方案 B（若产品坚持 422）：提交 PRD 变更申请，修订 RT-02、AC-IN-12 与 §2.5.8，并在 ARCH 附录 F/§10.5 登记该偏差；不得在无 PRD 变更的情况下冻结。
- 无论选择哪种方案，必须在 §4.10 增加一条“NL 缺失字段处置”的裁定记录。

---

### P0-02 `report_retry_count` 未进入 API 响应，AC-RP-07 与 FR-HS-02 不可验收

**位置**

- PRD §4.5.2 诊断记录：`retry_count`（0–1）、`review_round`（0–2）、`report_retry_count`（0–1）均为必填字段。
- PRD FR-HS-02：历史详情必须展示“重试次数、修订号、耗时”。
- PRD AC-HS-02：历史详情显示“重试次数”。
- PRD AC-RP-07：降级报告显示缺项清单与 **`report_retry_count=1`**。
- ARCH §5.4.6 `DiagnosisSnapshot` 字段表：只有 `version`、`diagnosis_revision`、`retrieval.retry_used`、`report.elements_check`；没有 `report_retry_count`、`retry_count`、`review_round`、`duration_ms`。
- ARCH §5.6.4 `DiagnosisSnapshot` JSON Schema：同样未定义上述字段；`report.elements_check` 只要求为 object，未定义缺项与 `report_retry_count`。

**缺陷说明**

`retrieval.retry_used` 只能表达“是否重试”，不能表达 `report_retry_count`；`report.elements_check` 没有被约束为包含重试次数。前端按本文实现时无法在降级报告或历史详情中展示 `report_retry_count=1`，AC-RP-07/AC-HS-02 只能靠读数据库或猜测字段，不能作为 API 验收。

**修复建议**

- 在 `DiagnosisSnapshot` 顶层增加：`retry_count`、`review_round`、`report_retry_count`、`duration_ms`；`duration_ms` 与 `timings.total_ms` 二选一或明确“同值别名”。
- 在 §5.6.4 Schema 中加入对应字段及类型；在示例中补齐；在 `DiagnosisSummary` 中也至少提供 `retry_count` 与 `duration_ms`。
- 明确 `report_elements_check` 的对象结构（`passed`、`present[]`、`missing[]`、`report_retry_count`），不要只写 `object`。
- 增加契约测试：AC-RP-07 断言 API 返回 `report_retry_count=1`；AC-HS-02 断言 `retry_count`、`duration_ms`、`diagnosis_revision` 可见。

---

### P0-03 状态机路由返回未定义节点/分支，eval 可进入 `clarify`，RT-03 图内兜底未实现

**位置**

- ARCH §3.5 `route_after_parse`：批量缺失返回 `"row_failed"`；§3.5 `route_after_diagnose` 返回 `"auto_review_report"`、`"auto_confirm_report"`；§3.5 `route_after_resume` 返回 `"invalid"`。
- ARCH §3.4“route 枚举映射”：只列出 `parse/retrieve/diagnose/report/report_check/report_fix/clarify/human_review/finalize/degraded_finalize/degraded_review_finalize/timeout_finalize/error/expired`，没有 `row_failed`、`auto_review_report`、`auto_confirm_report`、`invalid`。
- ARCH §3.2 图拓扑：没有上述四个节点或复合边；仅有一句“`auto_review_report` 只是‘置标志后走 report’的复合边”，但没有在路由枚举或条件边映射中给出落点。
- ARCH §3.6 执行模式矩阵：`eval` 的 clarification“禁止”；但 `route_after_parse` 未判断 `execution_mode=="eval"`。当 eval 样本的 `input_type` 为 `nl/chat` 且 `missing_fields` 非空时，先过批量判断（false），再命中 `missing_fields and input_type in ("nl","chat")`，返回 `clarify`，与矩阵及“评测不创建人工中断”冲突。
- ARCH §3.4 RT-03：表单/CSV 单条缺失或非法由 API 前置校验；图内仅在竞态时进 `error`。但 `route_after_parse` 对 `form/csv_single` 的 `missing_fields` 没有分支，`hard_error` 之后直接返回 `retrieve`，会把缺失特征的输入推进到检索。

**缺陷说明**

这不是“命名美观”问题，而是 LangGraph 条件边无法执行：返回字符串必须对应已注册节点或条件边映射。当前实现会出现三类后果：

1. 批量行走到图内兜底时，`row_failed` 无节点，图执行报错或静默走错边；
2. eval 缺失字段进入 `clarify`，与 PRD“评测不适用人工中断”及 §3.6 矩阵冲突；
3. 表单/CSV 竞态缺失进入 `retrieve`，违反 RT-03 的“阻断/进 error”语义，可能产出基于缺失特征的结论。

**修复建议**

- 在 §3.4 route 枚举与 §3.2 图拓扑中补齐：`row_failed`、`auto_review_report`、`auto_confirm_report`、`invalid`（或改为返回已有的 `report`/`error`，由 supervisor 置标志，不再创造新 route 名）。
- 在 `route_after_parse` 增加：
  - `if execution_mode == "eval" and missing_fields: return "sample_failed"`（新增 eval 终态，映射样本 `failed`）；
  - `if execution_mode in ("single",) and input_type in ("csv_single","form") and missing_fields: return "error"`（RT-03 图内兜底）；
  - `clarify` 条件显式限定为 `execution_mode == "single" and input_type in ("nl","chat")`。
- 为四条 route 分支各补至少 1 条编排测试，并在 §3.4 RT 表中登记落库点/终态。
- `invalid` 不应由路由函数返回；恢复请求的非法决策应在 API 前置拒绝（409 `DECISION_NOT_ALLOWED`），图中不保留该分支。

---

## C. P1 缺陷（不阻断判定，但需在冻结前一并修正或登记）

| 编号 | 位置 | 问题 | 修复建议 |
| --- | --- | --- | --- |
| P1-ARCH-01 | ARCH §5.4.6 + §5.6.4 | `DiagnosisSnapshot.interrupt` 的字段表没有 `version`，但 Schema 的 `required` 含 `version`；快照示例的 `interrupt` 也没有 `version`。示例无法通过自身 Schema，违反 §10.1 “示例必须通过 Schema”。 | 将 `version` 补入字段表与示例，或从 Schema required 移除；`interrupt` 的版本建议直接复用快照顶层 `version`，避免双版本源。 |
| P1-ARCH-02 | ARCH §5.6.4 | `report.meta` 是可选字段，但 PRD §4.5.2 要求 `report_meta` 与报告同时存在；§7.3 不变量 5 也要求 `report_md` 非空时 `report_meta_json` 非空。Schema 允许缺 meta，与不变量冲突。 | 当 `report` 非 null 时将 `meta` 设为 required，或明确“报告无 meta 即违约”的契约测试。 |
| P1-ARCH-03 | ARCH §5.6.4 | `input_summary` 在字段表中是必需业务字段，但 Schema 的 `required` 未包含它；`timings`、`error` 也未约束。 | 将 `input_summary` 加入 required；对 `timings` 至少定义 `total_ms`、`nodes`。 |
| P1-ARCH-04 | ARCH §5.6.7 | `BatchTaskSummary` 使用 `additionalProperties: false`，与 §5.1.9“响应对象允许新增字段，客户端忽略未知字段”的兼容策略冲突。 | 改为 `true`，或明确将 BatchTaskSummary 列为封闭响应并说明破坏性变更流程。 |
| P1-ARCH-05 | ARCH §5.6.5 | `SseEvent.seq` 对所有事件都允许 `null`，只有 heartbeat 的 `then` 强制 null；非 heartbeat 的 `step/status/report` 也可为 null，破坏 `Last-Event-ID` 回放前提。 | 增加条件：`type != heartbeat` 时 `seq` 必须为 integer；仅 snapshot 允许 seq=当前最大序号（0 合法）。 |
| P1-ARCH-06 | ARCH §5.4.6 | `input_fingerprint` 不返回前端是安全考虑，但 PRD §4.5.2 将单条入口的 `input_fingerprint` 列为必填字段；附录 F 未登记该差异。 | 在附录 F 明确“仅内部持久化，不暴露客户端”，并说明 AC-DG-15 只依赖 `diagnosis_id`；或提供只读 `fingerprint_hash` 字段。 |
| P1-ARCH-07 | ARCH §5.4.6 | 快照缺少 `retry_count`、`review_round`、`duration_ms` 的顶层映射；`report_retry_count` 已在 P0-02 单列。`retrieval.retry_used` 不能替代“重试次数”字段。 | 与 P0-02 一并补齐；至少给出字段映射表：`retry_count ↔ retrieval.retry_used`、`duration_ms ↔ timings.total_ms`，并明确 machine-readable 字段名。 |
| P1-ARCH-08 | ARCH §5.4.7 | PRD §4.5.4 的 `success_rows`、`degraded_rows`、`degraded_review_rows`、`failed_rows`、`failed_timeout_rows`、`cancelled_rows` 未按原名暴露，只给 `counts` 聚合。语义可映射，但“100% 覆盖数据字典”审计不通过。 | 在 §5.4.7 增加映射表：`success_rows=counts.succeeded` 等；或同时保留 PRD 命名别名（响应新增字段不破坏兼容）。 |
| P1-ARCH-09 | ARCH §5.4.6 / §5.5.3 | `report_meta` 在状态/DB 为 `report_meta`、快照为 `report.meta`、SSE report 事件为 `report_meta`，三处命名不一致；前端类型生成后会分裂。 | 统一为 `report_meta`，或在 Schema 中把 `report.meta` 明确 alias 到 `report_meta`；SSE 与快照使用同一字段名。 |
| P1-ARCH-10 | ARCH §5.5.3 / §3.5 | PRD §3.5 的中断载荷要求 `interrupt_payload` 含 `created_at`，clarification 载荷要求 `partial_features`、`device_id`；ARCH 只给通用 `payload: object`，clarification 无字段定义/示例。 | 为 `interrupt.payload` 分别定义 `clarification` 与 `review` 的 JSON Schema（含 `created_at`、`partial_features`、`device_id`、`missing_fields`、`evidence_refs`、`review_round`），并补示例。 |
| P1-ARCH-11 | ARCH §3.1 读写白名单 | PRD §3.5 白名单中 `auto_review` 只有总控 W、报告 R，诊断推理为 `-`；ARCH §3.1 给诊断推理增加了 R。 | 删除诊断推理对 `auto_review` 的 R，或提交白名单变更并说明诊断推理为何需要读取该标志。 |
| P1-ARCH-12 | ARCH §4.9 / §7.3 | 启动对账把 `running` 置 `failed(PROCESS_RESTART)`，但未明确清空 `active_fingerprint_key`；若不清空，同指纹后续创建会持续命中唯一约束冲突并最终 409，RT-17 不可恢复。 | 在 §4.9 与 §7.3 不变量 3 中明确：进程重启置终态时必须在同一事务清空 `active_fingerprint_key`；增加集成测试。 |
| P1-ARCH-13 | ARCH §4.4.1 / §5.5.3 | PRD §3.7 要求“连接存活时推送 `expired` 事件”；ARCH SSE 事件类型没有 `expired`，只靠 `status.to=expired`。必须明确懒判定与扫描器都会写事件并推 `status`，否则在线客户端只能等轮询。 | 明确 `expire` 事务同时写 `diagnosis_events(type=status, to=expired)` 并广播；前端 §8.3 终态集合已含 `expired`，补契约测试。 |
| P1-ARCH-14 | ARCH §5.4.5 | 对话首条消息“完整则直接创建诊断”，没有 PRD §2.5.8 的抽取确认卡/用户修正环节；对话补充 `POST /messages` 不携带 `version`，与 PRD §3.7“恢复前置 version 一致”不一致。 | 对话首条完整消息先返回抽取卡（或增加 `confirm` 标志），用户确认后创建；`/messages` 补充时接受 `version`，或明确“服务端当前版本 + 会话锁”替代规则并登记差异。 |
| P1-ARCH-15 | ARCH §5.4.8 / §4.6 | KPI-03 只写 `timeout_rate`，未明确 `failed_timeout` 不计入成功时延样本；KPI-04 无 `success_rate` 字段或公式。 | 在 `EvalBatchSummary` 与 §4.6 中明确：`latency_avg/p50/p95` 分母 = 成功报告样本（排除 `failed_timeout`/`failed`），`timeout_rate = failed_timeout_count/120`；批量成功率由 `counts` 计算并补公式。 |
| P1-ARCH-16 | ARCH 附录 C / §5.4.6 | AC-IN-14 要求 trace 记录“用户修正”，但 `step.event` 枚举没有 `user_correct`/`correction`。 | 增加 `user_correct`（或 `correction`）事件并在 `diagnosis_steps`/trace 示例中体现；同步 PRD §4.5.3 枚举变更登记。 |
| P1-ARCH-17 | ARCH §4.5.2 / §5.4.5 | 新增 `chat_session.status`（`draft/active/terminal`）在 PRD §4.5 数据字典中没有定义；属于新增业务状态。 | 在附录 F 登记为架构补充状态，说明仅用于会话生命周期，不进入诊断状态机；或回写 PRD 数据字典。 |
| P1-ARCH-18 | ARCH §5.4.6 DELETE | 禁止删除 `input_type=csv_batch` 的诊断，PRD FR-HS-03/US-31 只写“单条删除、二次确认”，未明确批量行不可删。 | 在附录 F 登记该限制及理由（批量计数/导出一致性）；若产品要求可删除，需补批量删除语义与计数重算。 |

---

## D. 已核对通过的关键契约（防止误判）

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| RT-05 优先于 RT-06~08 | 通过 | ARCH §3.5 `route_after_diagnose` 先判 `knowledge_status=missing`，再判 `confidence>=0.8`；§3.4 RT-05 |
| RT-08 优先于 RT-07 | 通过 | §3.5 先判 `retry_count<1 && 0.5<=c<0.8`，否则单条进入 `human_review`；首次 `<0.5` 不重试 |
| 批量不进入 clarification/review/expired | 通过（图内兜底见 P0-03） | §3.4 RT-18/RT-19、§3.6 矩阵、§4.8、§7.3 不变量 10；批量行枚举无 `waiting_human/expired` |
| eval 不进入人工中断 | 路由矩阵通过，代码分支不通过 | §3.6 矩阵“eval review 禁止”；`route_after_diagnose` 对 eval 返回 `auto_confirm_report`；但 `route_after_parse` 缺少 eval 缺失分支（P0-03） |
| `input_fingerprint` 计算时点 | 通过 | §4.1.2：结构化/NL 创建前；chat 轻量抽取后创建前；batch 仅追溯；eval 不计算 |
| `active_fingerprint_key` 部分唯一索引 + 终态清空 | 通过（重启清空见 P1-ARCH-12） | §4.1.3、§7.2、§7.3 不变量 3 |
| TTL 双机制 + `interrupt_expires_at` 持久化 | 通过 | §4.4.1：懒判定 + 每 60s 扫描；状态/投影字段；§3.7 |
| 15s 熔断无报告、`failed_timeout` | 通过（KPI 口径见 P1-ARCH-15） | §4.6、§4.3.2 报告可用性矩阵、§3.3 `timeout_finalize` |
| `degraded` / `degraded_review` 缺项优先 | 通过 | §4.3.2 `resolve_status`、§4.2.1、§4.2.2 |
| `auto_review` 独立保留 | 通过 | §4.2、§4.3.2、§7.3 不变量 6 |
| SSE 事件封套与类型 | 通过（schema 细节见 P1） | §5.5.2~§5.5.6；7 类诊断事件 + 批量事件 |
| `Last-Event-ID` 回放 | 通过 | §4.7、§5.5.5、§6.5 |
| 终态关闭 / 快照为最终事实 | 通过 | §1.2 原则 5、§5.5.1、§6.1、§8.3 |
| 物理 DDL 越权 | 未发现 | §1.1 非目标、ADR-015、§7 开头；§7.2 仅有逻辑约束/索引说明，无 SQL DDL |

---

## E. PRD 验收日志 §4.10 的 8 条 P1 处置核对

| 验收日志条目 | ARCH §4.10 对应 | 判定 | 说明 |
| --- | --- | --- | --- |
| 1. AC-DG-20 夹具“首次 0.42、重试后 0.42”与 RT-07 冲突 | P1-01 | 已裁定 | 改为首次 0.62、重试后 0.62，或删除“重试后”；首次 <0.5 时 `retry_count=0` |
| 2. KPI-01/KPI-02 与 `failed_timeout` 分母 | P1-02 | 部分裁定 | KPI-01 分母 120、超时计错；KPI-02 分母 `report_count` 已明确；KPI-03 仅写“超时单列”，未明确排除成功时延样本（P1-ARCH-15） |
| 3. `report_meta`/`report_title` 状态与白名单 | P1-03 | 已裁定 | 状态新增两字段；报告服务 W、总控 R；投影新增两列 |
| 4. UI 状态条缺 `failed_timeout`、评测页缺超时率 | P1-04 | 已裁定 | §8.4 补“超时失败”；§8.9 补超时率卡与明细 |
| 5. `auto_review` 未入数据字典 | P1-05 | 已裁定 | 独立列 + `report_meta` + API 字段；不得由 status 反推 |
| 6. `input_fingerprint` 计算时序二义 | P1-06 | 已裁定 | §4.1.2 按入口明确；chat 轻量抽取后创建前；不完整不参与 |
| 7. US-10 与“缺项优先” | P1-07 | 已裁定 | §4.3.2 缺项优先；前端双标注 |
| 8. 0.8 重叠、15s 竞态、批量超时运行行去向、D-04/D-06 摘要 | P1-08 | 已裁定 | 0.8 归 high、medium 左闭右开；测试注入 >15s；运行中行允许完成；D-04/D-06 留在 PRD 文档措辞 |

**结论：8 条均有明确落点，但第 2 条的 KPI-03 口径需要补齐；其余为表述/契约细节，不影响“已裁定”性质。**

---

## F. 修复优先级与复审门槛

**必须先修（P0）**

1. P0-01：NL 缺失字段路径与 RT-02/AC-IN-12 对齐，或完成 PRD 变更并登记。
2. P0-02：在 `DiagnosisSnapshot`/Schema/示例中补齐 `report_retry_count`、`retry_count`、`review_round`、`duration_ms`。
3. P0-03：补齐 route 枚举与图节点，增加 eval 缺失分支、RT-03 图内兜底，删除无法执行的 route 返回值。

**冻结前应修（P1）**

- 至少修 P1-ARCH-01~05（Schema/示例/兼容性）、P1-ARCH-09（`report_meta` 命名）、P1-ARCH-10（中断载荷）、P1-ARCH-12（重启清 active 指纹）、P1-ARCH-15（KPI 口径）。
- 其余 P1 可在 DB/前端/测试阶段承接，但必须在 ARCH 附录 F 或 §10.5 登记，不得静默保留。

**复审门槛**

- P0 清零；
- `docs/ARCH验收日志.md` 中列出的 P0/P1 均有“已修复/已登记”证据；
- `DiagnosisSnapshot` 与 `SseEvent` 的所有示例通过 §5.6 Schema（`tests/contract/test_examples.py`）；
- 路由测试覆盖 RT-01~RT-20，特别是 RT-02 的 NL 分支、RT-03 图内兜底、RT-19 批量兜底、eval 缺失分支；
- AC-IN-12、AC-RP-07、AC-HS-02 能在 API 层构造并通过。

---

## G. 复审判定

**本次判定：【驳回】。ARCH V1.0.0 不得冻结为契约基线。**

主要阻断点不是“文风”或“可优化项”，而是：

1. **NL 入口的契约与 PRD 路由/验收用例直接冲突**，导致 RT-02 的 NL 分支不可执行；
2. **`report_retry_count` 等验收所需字段缺失**，AC-RP-07/AC-HS-02 无法通过 API 验证；
3. **状态机路由函数返回未注册节点/分支**，且 eval 缺失字段可进入 `clarify`，图无法按文档执行。

修复后重新提交冷启动验收；在 P0 清零前，不建议 DB/前端进入契约冻结开发。

---

## 2026-10-23 系统架构与 API 契约 V1.1.0 冷启动复审报告

| 项 | 内容 |
| --- | --- |
| 审查产物 | `docs/ARCH-系统架构与API契约.md`（V1.1.0） |
| PRD 基线 | `docs/PRD-设备故障诊断智能体-V1.0.0.md`（V3.0.0） |
| 上次驳回日志 | `docs/log/ARCH验收日志.md`（2026-10-23 第一轮） |
| 复审方式 | 冷启动；仅依据 PRD V3.0.0 与 ARCH V1.1.0 正文；逐项验证 P0、端点 #35、§10.4/附录 F 的 P1 落点 |
| 最终判定 | **【驳回】** |
| 原 P0-01~P0-03 | 已闭环 |
| 新增 P0 | 1 项（P0-04：`device_id` 可缺失与实体/快照必填冲突） |
| P1 残留 | 8 项 |

**门禁结论：V1.1.0 已实质修复上一轮三项 P0，但 P0-01 的“NL 部分输入”修复边界过宽，把 `device_id` 也列为可缺失；这与 PRD FR-IN-09、诊断实体、`DiagnosisState` 与 `DiagnosisSnapshot` 的非空约束冲突。该路径会创建无法合法落库/序列化的诊断，故 P0 未清零，不能冻结。**

---

### A. 原 P0 闭环核对

| P0 | 上次问题 | 本次验证 | 判定 |
| --- | --- | --- | --- |
| P0-01 | NL 缺失字段被 422 阻断，RT-02/AC-IN-12 不可执行 | §5.4.4 `partial → recommended_action=clarify`；§5.4.6 新增“变体 C′ nl（部分，允许创建）”；§5.6.2 `nl` 仅 required `input_type`+`text`；§5.4.6 补 AC-IN-12 接口级 5 条断言；附录 F 登记“以 RT-02/AC-IN-12 为准” | **已闭环**（但见 P0-04） |
| P0-02 | `report_retry_count` 等字段缺失，AC-RP-07/AC-HS-02 不可验收 | §5.4.6 快照顶层补 `retry_count`、`review_round`、`report_retry_count`、`duration_ms`、`report_elements_check`、`report_meta`；§5.6.4 对应 required 与 `$defs.elementsCheck`；§5.4.6 补结构化示例；`DiagnosisSummary` 补 `retry_count`/`duration_ms` | **已闭环** |
| P0-03 | 路由返回未注册节点；eval 可进 clarify；RT-03 图内兜底缺失 | §3.2 注册 `row_failed`、`sample_failed`、`auto_review_report`、`auto_confirm_report`；§3.4 route 枚举补齐这四个节点；§3.5 `route_after_parse` 增加 eval/single 分支，`clarify` 限定 `single + nl/chat`；删除 `invalid` 返回值，第 2 轮 supplement 由 API 前置 409 | **已闭环**（`aborted` 未入 route 表，属 P1） |

---

### B. 新增 P0

#### P0-04 `nl`/chat 部分输入允许缺失 `device_id`，与实体/快照必填冲突

**位置**

- ARCH §5.4.6：`nl` 仅强制 `input_type` 与 `text`；“`device_id`、`product_type` 与 5 个数值特征均可缺失”；“任一项缺失：创建诊断……一次列出全部缺失字段（**含 `device_id`**）”。
- ARCH §5.4.6 字段校验表：`device_id` “`nl` 可缺失并进入 `clarify`”。
- ARCH §5.4.5 `POST /chat/sessions/{id}/confirm`：`features` 可部分缺失，未要求 `device_id`。
- ARCH §5.6.2 `nl` Schema：`device_id` 不在 required；§5.6.9 `ChatConfirmRequest.features` 也未 required `device_id`。
- 冲突证据：ARCH §3.1 `DiagnosisState.device_id: str`（非 nullable）；§5.4.6/§5.6.4 `DiagnosisSnapshot.device_id` 为 required 且 `minLength:1`；PRD §4.5.2 诊断记录 `device_id` 必填；PRD FR-IN-09 与 §3.3.1 明确“所有入口必填；缺失/非法/超长阻断并提示”。

**影响**

`nl` 部分输入（或 chat confirm 不传 `device_id`）会创建一条 `waiting_human` 诊断，但其 `device_id` 为空；随后 `GET /diagnoses/{id}` 返回的快照无法通过 §5.6.4 Schema，`diagnoses` 投影也无法满足 PRD §4.5.2 的必填约束。该路径与 AC-IN-12 也不同：AC-IN-12 的输入本身包含 `device_id=3号机`，并不要求 `device_id` 可缺失。

**修复建议**

- 将 `device_id` 从“NL 可缺失”中移除：`nl` 创建与 chat confirm 均要求 `device_id`，缺失返回 422 字段错误（符合 FR-IN-09“阻断并提示”）；仅允许 `product_type` 与 5 个数值特征缺失后进入 `clarify`。这样 AC-IN-12 仍可通过。
- 若产品坚持 `device_id` 也通过追问补齐，则不能在 `diagnoses` 实体上创建记录：应先建 `chat_session`/独立输入草稿，补齐 `device_id` 后再创建诊断；不得引入默认值或空字符串占位（违反 PRD“禁止默认值填充”）。
- 同步修改 §5.6.2 `nl`、§5.6.9 `ChatConfirmRequest.features` 的 required/约束，并补一条“缺 device_id → 422 / 不创建诊断”的契约测试。

---

### C. 新增接口 #35 闭环审查

| 检查项 | 结论 | 说明 |
| --- | --- | --- |
| 端点注册 | 通过 | §5.3 #35 `POST /chat/sessions/{session_id}/confirm`，202，错误 404/409/422/503 |
| 请求 Schema | 基本合理 | `ChatConfirmRequest` required `text`；`features` 可部分缺失；与 `/messages` 抽取卡字段一致 |
| 响应 Schema | 基本合理 | `ChatConfirmResponse` required `session_id/diagnosis_id/diagnosis_status/version/stream_url` |
| 首条消息闭环 | 通过 | `/messages` 在 `draft` 只返回抽取卡、不建诊断；确认后 `/confirm` 创建；`active + clarification` 只返回补充卡，状态变更统一走 `/diagnoses/{id}/resume` 并带 `version` |
| RT-17 闭环 | **不完整** | §5.4.5 写“7 项齐备时计算 fingerprint 并参与 RT-17”，但 `/confirm` 只定义 202，响应无 `deduplicated`，未定义命中 RT-17 时返回 200 + 已有 `diagnosis_id` 的行为 |
| `features` 空值 | **不完整** | `/messages` 抽取卡的 features 对缺失项返回 `null`；`ChatConfirmRequest.features` 各字段仅允许 string/number，不允许 `null`，前端不能原样回传 |
| 会话状态 | **不完整** | `/confirm` 只写“会话从 draft 变为 active”；未定义 session 为 `active`/`terminal` 时的 409 行为与错误码映射 |
| 补充卡 Schema | **不完整** | `/messages` 的 `active + clarification` 分支只写“返回补充卡”，未给出响应示例/字段（interrupt、extraction、version 来源） |
| 会话迁移矩阵 | **不一致** | 附录 B 仍写 `draft → active | 首条消息创建诊断`；V1.1.0 已改为 `/confirm` 创建诊断，迁移触发点未同步 |

---

### D. P1-ARCH-01~18 落点复核

| 编号 | §10.4/附录 F 落点 | 实际复核 |
| --- | --- | --- |
| P1-ARCH-01 | F.3 已修复 | `interrupt.version` 已入字段表、示例与 Schema required |
| P1-ARCH-02 | F.3 已修复 | 快照改为顶层 `report_meta`；`allOf` 在 report 非 null 时要求 object |
| P1-ARCH-03 | F.3 已修复 | `input_summary` 已 required；`timings` 有 `total_ms/nodes` |
| P1-ARCH-04 | F.3 已修复 | `BatchTaskSummary.additionalProperties=true` |
| P1-ARCH-05 | F.3 已修复 | 非 heartbeat 强制 integer `seq` |
| P1-ARCH-06 | 附录 F 已登记 | `input_fingerprint` 仅内部持久化；AC-DG-15 依赖 `diagnosis_id` |
| P1-ARCH-07 | F.3 已修复 | 快照顶层补 `retry_count/review_round/duration_ms` |
| P1-ARCH-08 | F.3 已修复 | §5.4.7 给出 `success_rows=counts.succeeded` 等别名与 `success_rate` 公式；属“别名映射”而非新增响应字段，可接受 |
| P1-ARCH-09 | F.3 已修复 | 快照顶层 `report_meta` 与 SSE `report` 事件同名；`report` 对象不再含 `meta` |
| P1-ARCH-10 | F.3 已修复（部分） | §5.6.8 已定义 InterruptPayload；但 §5.6.4 `interrupt.payload` 仍是 `type: object`，未 `$ref`，Schema 只靠文字注释约束（残留 P1） |
| P1-ARCH-11 | F.3 已修复 | §3.1 `auto_review` 已删除诊断推理 R，仅总控 W、报告 R |
| P1-ARCH-12 | F.3 已修复 | §3.8/§4.9 明确同一事务清空 `active_fingerprint_key`；§7.3 不变量 3 与集成测试要求已落文（已实测文本） |
| P1-ARCH-13 | F.3 已修复 | §4.4.1 明确懒判定/扫描共用 expire 事务并写 `diagnosis_events(type=expired)`；§5.5.3 增加 `expired` 事件；§8.3 终态集合含 expired |
| P1-ARCH-14 | F.3 已修复（部分） | 新增 `/confirm`；但 RT-17 200/dedup、features null、active/terminal 行为仍缺（见 C） |
| P1-ARCH-15 | F.3 已修复 | §4.6/§5.4.7/§5.4.8 明确 `latency_sample_count`、`timeout_rate`、`success_rate` 公式（已实测文本） |
| P1-ARCH-16 | F.3 已修复 | 附录 C `step.event` 含 `user_correct`；快照示例含 trace |
| P1-ARCH-17 | 附录 F 已登记 | `chat_session.status` 登记为会话生命周期，不进诊断状态机 |
| P1-ARCH-18 | 附录 F/§5.4.6 已登记 | `csv_batch` 诊断禁止单独删除，理由为计数/导出一致性 |

**结论：18 条均有“已修复/已登记”落点；P1-ARCH-10、P1-ARCH-14 为部分落点，其余经正文复核成立。§10.4 的 C-006 为总括变更记录，逐条证据以附录 F.2/F.3 为准。**

---

### E. P1 残留（不阻断本次 P0 判定，但冻结前应修）

1. **P1-R1（#35 RT-17）**：`/chat/sessions/{id}/confirm` 只定义 202；7 项完整且命中 RT-17 时应返回 200 + 已有 `diagnosis_id`，响应补 `deduplicated`，并同步 §5.3 #35、§5.4.5、§6.2。
2. **P1-R2（#35 features）**：`ChatConfirmRequest.features` 对缺失字段不接受 `null`，而 `/messages` 抽取卡返回 null；明确“前端须剔除 null”或 Schema 允许 null。
3. **P1-R3（#35 会话状态）**：补 `/confirm` 在 `active`/`terminal` 会话的 409 行为与错误码；补“确认卡对应的 message_id/重复 confirm 幂等”规则。
4. **P1-R4（补充卡）**：`/messages` 的 `active + clarification` 分支补响应 Schema/示例（补充卡、extraction、version 来源）；避免前端自行拼字段。
5. **P1-R5（示例校验）**：§5.5.4 的 `snapshot` 事件示例不是“完整 DiagnosisSnapshot”，缺 `input_summary`、`retry_count`、`review_round`、`report_retry_count`、`report_elements_check`、`duration_ms`，违反 §10.1“示例必须通过 Schema”。
6. **P1-R6（InterruptPayload）**：§5.6.4 `interrupt.payload` 改为 `{"$ref": ".../interrupt-payload.schema.json"}`，否则 §5.6.8 的 Schema 只停留在文档层。
7. **P1-R7（route 枚举）**：`route_after_resume` 返回 `aborted`，图有 `aborted` 节点，但 §3.4 route 枚举映射未列 `aborted`；补映射，避免与 P0-03 同类问题回归。
8. **P1-R8（时序/迁移一致性）**：§6.2 的 NL 时序仍只画“nl + 7 项 + 原文”，未画部分 NL → clarification；chat 时序未画 RT-17 200 复用；附录 B 仍写“首条消息创建诊断”，应改为“confirm 创建诊断”。

---

### F. 复审结论

- **原 P0-01~P0-03：已闭环。**
- **新增 P0-04：未闭环。** `nl`/chat 部分输入允许 `device_id` 缺失，与 `DiagnosisState`、`DiagnosisSnapshot`、PRD §4.5.2/FR-IN-09 的非空约束冲突；该路径会产出无法合法序列化/落库的诊断。
- **P1-ARCH-01~18：形式上均有落点；P1-ARCH-10、P1-ARCH-14 为部分落点，另有 8 条新增/残留 P1。**

**本次判定：【驳回】。ARCH V1.1.0 不得冻结。** 修复 P0-04（`device_id` 必填或改为诊断前草稿实体）并处理 P1-R1~R8 后，重新执行冷启动复审。

---

## 2026-10-23 系统架构与 API 契约 V1.2.0 冷启动复审报告

| 项 | 内容 |
| --- | --- |
| 审查产物 | `docs/ARCH-系统架构与API契约.md`（V1.2.0） |
| PRD 基线 | `docs/PRD-设备故障诊断智能体-V1.0.0.md`（V3.0.0） |
| 上次驳回日志 | `docs/log/ARCH验收日志.md`（V1.1.0 复审报告） |
| 复审方式 | 冷启动；仅依据 PRD V3.0.0 与 ARCH V1.2.0 正文；逐项验证 P0-04、原 P0 回归、P1-R1~R8、Schema/示例自洽与 §10.4/附录 F 落点 |
| 最终判定 | **【通过，准予冻结 V1.2.0】** |
| P0 残留 | 0 项 |
| P1-R1~R8 | 全部闭环 |
| P1-ARCH-01~18 | 无回退 |

**门禁结论：P0 清零。`device_id` 已全入口必填；chat confirm 的 RT-17 200/200 复用、null 规则、会话 409、补充卡 Schema、完整 SSE snapshot、InterruptPayload `$ref`、route `aborted`、时序与附录 B 迁移均已同步。API/SSE/状态机/边界逻辑可直接指导前后端开发，未发现越权物理 DDL。**

---

### A. P0-04 闭环核对

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| `nl` 强制 `input_type`+`text`+`device_id` | 通过 | §5.4.6 变体 C′：`nl` 强制三项；§5.6.2 `nl` required `["input_type","text","device_id"]` |
| `device_id` 缺失 → 422、不创建诊断 | 通过 | §5.4.6 “缺失/为空/超长/非法 → 422 `DEVICE_ID_INVALID`，不创建诊断”；§5.2 错误码存在；§6.2 时序补 422 分支 |
| `ChatConfirmRequest.features` required `device_id` | 通过 | §5.6.9 `features.required=["device_id"]`；§5.4.5 `/confirm` 缺 `features`/`device_id` → 422 |
| AC-IN-12 增加“缺 device_id → 422”断言 | 通过 | §5.4.6 AC-IN-12 第 6 条：提交无 `device_id` 的 NL → 422 `DEVICE_ID_INVALID`，诊断记录数不增加 |
| 附录 F 登记“全入口必填，NL 仅产品类型与数值特征可缺失” | 通过 | 附录 F 首行与 F.4 P0-04 均明确；`/nl/extract` partial 仍为 `clarify` |
| 原 P0-01 部分 NL 仍可创建并进入 clarify | 通过 | §5.4.6 `device_id` 齐备但 product_type/数值缺失 → 202，`input_fingerprint=null`，进入 `clarify`；AC-IN-12 第 1~5 条 |
| 原 P0-02 快照字段仍完整 | 通过 | §5.4.6/§5.6.4 `retry_count`、`review_round`、`report_retry_count`、`duration_ms`、结构化 `report_elements_check`、顶层 `report_meta` 仍在 |
| 原 P0-03 路由/eval 隔离仍成立 | 通过 | §3.2 `row_failed`、`sample_failed`、`auto_review_report`、`auto_confirm_report`；§3.5 `route_after_parse` eval/single 分支与 `clarify` 限定仍在 |

**结论：P0-04 及其对原 P0-01~P0-03 的影响均已闭环。**

---

### B. P1-R1~R8 闭环核对

| 编号 | 检查点 | 结论 | 证据（状态/Schema/时序/迁移四处同步） |
| --- | --- | --- | --- |
| P1-R1 | `/confirm` 7 项完整且命中 RT-17 → 200 + 已有 `diagnosis_id` + `deduplicated=true` | 通过 | §5.3 #35 成功 `202/200`；§5.4.5 明确 200/202 两分支；§5.6.9 `ChatConfirmResponse.deduplicated` required；§6.2 时序 200 分支 |
| P1-R2 | `features` 的 null 规则 | 通过 | §5.4.5 明确“前端必须剔除 null；传 null → 422 `VALIDATION_FAILED`”；§5.6.9 `features` 字段均不接受 null；§5.4.5 抽取卡示例保留 null 以提示前端清洗 |
| P1-R3 | `/confirm` 的 active/terminal 409 与重复 confirm 幂等 | 通过 | §5.4.5 `active → 409 CHAT_SESSION_ALREADY_ACTIVE`、`terminal → 409 CHAT_SESSION_CLOSED`；§5.2 错误码；同 `message_id`/`Idempotency-Key` 返回首次结果 |
| P1-R4 | `/messages` 的 `active + clarification` 补充卡 Schema/示例 | 通过 | §5.4.5 补 200 补充卡完整示例；§5.6.10 `ChatSupplementResponse`；`interrupt.payload` 使用 InterruptPayload `$ref`；`version` 来自快照 |
| P1-R5 | §5.5.4 `snapshot` 示例完整、可通过 §5.6.4 | 通过 | §5.5.4 示例补齐 `input_summary`、`retry_count`、`review_round`、`report_retry_count`、`report_elements_check`、`duration_ms`、`timings` 等 required；与 §5.6.4 required 对照一致 |
| P1-R6 | `interrupt.payload` `$ref` InterruptPayload | 通过 | §5.6.4 `payload` 为 `$ref: .../interrupt-payload.schema.json`；§5.6.10 补充卡同样 `$ref` |
| P1-R7 | route 枚举补 `aborted`、图节点注册 | 通过 | §3.3 `aborted` 终态节点；§3.4 route 枚举列 `aborted`；§3.2 图 `ABORT([\"aborted\"])`；§3.5 `route_after_resume` 返回 `aborted` |
| P1-R8 | §6.2 时序与附录 B 迁移改为 confirm 创建诊断，并画 RT-17 200 | 通过 | §6.2 补 `缺 device_id → 422`、部分 NL → clarify、`/confirm` 200/202/partial 分支；附录 B `draft → active` 触发为 `POST /chat/sessions/{id}/confirm`（或 RT-17 复用） |

**结论：R1~R8 在正文、Schema、时序图、附录 B/状态迁移四处均有同步，不存在“只改文字、未改 Schema/时序”的未闭环项。**

---

### C. 示例与 Schema 自洽

| 示例 | 对应 Schema | 结论 |
| --- | --- | --- |
| §5.4.5 `/confirm` 202/200 示例 | §5.6.9 `ChatConfirmResponse` | 通过；均含 `session_id/diagnosis_id/diagnosis_status/version/deduplicated/stream_url` |
| §5.4.5 `/messages` active clarification 补充卡示例 | §5.6.10 `ChatSupplementResponse` | 通过；`interrupt`、`extraction`、`version` 与 Schema required 一致 |
| §5.5.4 `snapshot` 事件示例 | §5.6.4 `DiagnosisSnapshot` | 通过；required 字段齐全；`report_elements_check:null` 与 `report:null` 合法 |
| §5.4.6 诊断快照示例 | §5.6.4 | 通过；`interrupt.version`、`report_elements_check`、`timings.total_ms/nodes` 均齐备 |
| §5.6.8 InterruptPayload 示例 | §5.6.8 | 通过；clarification/review 的 `created_at`、`missing_fields`、`partial_features`、`device_id`、`review_round` 均齐备 |

**结论：抽查的示例与 Schema 自洽；未发现 `interrupt.version`、`report_elements_check`、`timings` 的字段缺口。**

---

### D. 非阻断 P1 观察（不影响本次冻结）

以下为文档一致性/边界补充，不构成 P0，建议在冻结后首个文档勘误或 C-008 变更中处理：

1. **附录 F.2 的 P0-01 历史证据仍写“`nl` 仅强制 `input_type`+`text`”**，与 F.4、§5.4.6、§5.6.2 的“`device_id` 必填”不一致。建议改为“`input_type`+`text`+`device_id`”，避免读者误用旧口径。
2. **`/messages` 的 `draft` 抽取卡只有 JSON 示例，没有命名 Schema**（`ChatSupplementResponse` 仅覆盖补充卡）。建议补 `ChatExtractionResponse` 或在 §5.6.9 增加抽取卡 Schema，便于契约测试。
3. **`/confirm` 命中 RT-17 时若已有诊断已绑定另一个 chat session**，当前只写“会话绑定该已有诊断”；与“会话 1:1 诊断”存在边界重叠。建议明确“若已有诊断已绑定其他会话，返回 409 或仅返回 `diagnosis_id` 不二次绑定”，并补状态表/测试。
4. **§5.4.6 通用 202 示例仍写 `input_type: \"form\"`**；作为“通用创建响应”示例可接受，但建议改为占位值或补 NL/chat 示例，避免被误读为所有入口固定 `form`。

---

### E. 复审结论

**本次判定：【通过，准予冻结 V1.2.0】。**

- P0-04 已闭环，原 P0-01~P0-03 无回退；
- P1-R1~R8 已在正文、Schema、时序图、附录 B 同步闭环；
- P1-ARCH-01~18 落点仍在，未发现回退；
- 示例与 Schema 抽查自洽；
- 未发现物理 DDL 越权或新增 PRD 未定义诊断状态。

上述 D 节 4 条为非阻断 P1 文档/边界补充，可在冻结后按变更登记处理，不影响 V1.2.0 作为契约基线。
