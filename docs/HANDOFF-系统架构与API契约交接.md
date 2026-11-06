# 交接文档：系统架构与 API 契约

| 项目 | 内容 |
| --- | --- |
| 版本 | **V1.2.2**（V1.2.1 第二轮驳回后返修；第一轮 P1/P2/P3 与第二轮 P1-3/P2-5/P3 均闭环；同步 ARCH V1.2.0 与 UIUX V1.2.0 冻结基线，未修改上游） |
| 交接对象 | 数据库 Agent、后端 Agent、前端 Agent、测试 Agent |
| 上游基线 | `docs/PRD-设备故障诊断智能体-V1.0.0.md` V3.0.0（冻结） |
| 架构契约 | `docs/ARCH-系统架构与API契约.md` V1.2.0（冻结） |
| 交互契约 | `docs/UIUX-设备故障诊断智能体.md` V1.2.0（冻结） |
| 验收依据 | `docs/log/ARCH验收日志.md`（V1.2.0 复审通过）、`docs/log/UIUX验收日志.md`（第三轮通过，残留 3 条 P2）、`docs/log/HANDOFF验收日志.md`（V1.2.0 驳回项，本稿逐条返修） |
| API 版本 | `/api/v1` |
| 原则 | 不重复架构/交互文档内容；本文只给阅读顺序、必须落实的约束与风险 |

---

## 0. 阅读顺序

1. 所有人先读 `docs/ARCH-系统架构与API契约.md` 的 §1（ADR）、§10（治理）与 §11（交接摘要）。
2. 数据库 Agent：§4.1、§4.2、§5.4、§7。
3. 后端 Agent：§2、§3、§4、§5、§6、§7。
4. 前端 Agent：§5、§8 + `docs/UIUX-设备故障诊断智能体.md` §0.5.1（DEV-01~04）、§2（Design Token）、§4、§5、§6、§7、§8、§10（组件规范）、§11（文案规范）、§12、§13（UI 验收清单）。
5. 测试 Agent：§4.10、§10.2、附录 B、附录 E。

**权威顺序**：业务行为 → PRD V3.0.0；接口/报文/SSE/技术选型 → ARCH V1.2.0；界面表现/交互流程/Design Token → UIUX V1.2.0（且 UIUX 自述"接口/SSE 行为以 ARCH 为准"）。物理 DDL → 数据库设计文档，但不得改变 ARCH 语义。三者冲突一律登记到 ARCH §10.4，不得静默择一。

---

## 1. 已冻结的关键决定

- 模块化单体，单进程 Uvicorn `workers=1`；不引入 Redis/Celery/微服务。
- LangGraph + `AsyncSqliteSaver`，检查点独立文件 `storage/checkpoints.sqlite3`；`thread_id = diagnosis_id`。
- FastAPI REST + SSE；SSE 事件持久化，支持 `Last-Event-ID` 回放；快照是最终事实。
- FAISS `IndexFlatIP` + BGE-M3 归一化向量；知识库版本化目录 + 激活指针。
- 批量进程内 `asyncio` 并发 2；批量行不进入人工中断。
- RT-17 用 `input_fingerprint` + `active_fingerprint_key` 部分唯一索引原子去重。
- `auto_review`、`report_title`、`report_meta` 独立持久化；不得由状态反推。
- 置信度分级：`high [0.8,1]`、`medium [0.5,0.8)`、`low [0,0.5)`。
- 15s 全局熔断 → `failed_timeout`、无报告；每次 resume 重置执行窗口。
- 报告缺项优先 `degraded`；`auto_review=true` 仍保留。
- `device_id` 全入口必填；NL 仅允许 `product_type` 与 5 个数值特征缺失后进入 `clarify`；缺 `device_id` → 422，不创建诊断。
- Chat 首条消息只返回抽取确认卡（`diagnosis_id=null`、不建 SSE）；`POST /chat/sessions/{id}/confirm` 后才创建诊断；7 项完整命中 RT-17 时返回 200 + `deduplicated=true`；缺项按 RT-02 进入 `clarification`。
- `/confirm` 的 `features` 不接受 `null` 值（前端剔除 null 键），传 null → 422；仅 `draft` 会话可 confirm。
- 澄清中的自由文本只返回补充卡、不改变状态；确认后统一 `POST /diagnoses/{id}/resume`（`decision=supplement`，携带快照 `version`）。
- 快照顶层包含 `retry_count`、`review_round`、`report_retry_count`、`report_elements_check`、`duration_ms`；`report_meta` 与 SSE 同名。

---

## 2. 数据库 Agent 清单

**必读**：ARCH §4.1、§4.2、§5.4、§7。

### 必须落地

1. `diagnoses` 增加：`auto_review`、`report_title`、`report_meta_json`、`interrupt_expires_at`、`active_fingerprint_key`、`execution_mode`、`batch_task_id`、`row_id`。
2. `active_fingerprint_key` 建**部分唯一索引**（仅非空值，按 `user_id` 作用域）；诊断进入终态或 `expired`（含启动对账置 `failed(PROCESS_RESTART)`）必须在同一事务清空。
3. `diagnosis_events`、`batch_events` 追加写；`(diagnosis_id, seq)`、`(batch_task_id, seq)` 唯一；SSE 回放依赖。
4. `batch_tasks` 八项计数之和必须等于 `total_rows`；`completed_rows` = 所有终态行之和；行状态不含 `waiting_human`/`expired`。
5. `batch_rows.auto_review` 可冗余，但事实源是 `diagnoses.auto_review`；导出可 join。
6. `sessions.token_hash` 唯一；`users` 失败次数/锁定时间；24h 过期。
7. `knowledge_versions` 至多一个 `active`；激活/回滚同事务切换；`manifest_path` 指向版本目录。
8. `chat_sessions` 1:1 诊断：`diagnosis_id` 初始 `null`，`/confirm` 创建或 RT-17 复用时在同一事务写入；至多绑定一个诊断；诊断终态后会话语义 `terminal`。`chat_messages` 追加写，抽取确认卡/补充卡载荷存 `payload_json`。
9. `idempotency_keys` 唯一 `(user_id, endpoint, key)`；10 分钟 TTL；`/messages`、`/confirm` 共用该机制，同 key 返回首次结果。
10. `diagnoses` 索引：`(user_id, started_at DESC)`、`(user_id, status)`、`(user_id, primary_type)`、`(user_id, confidence_level)`、`(batch_task_id)`、`(upload_id)`；TTL 扫描索引 `(status, interrupt_expires_at)`。
11. SQLite：WAL、`busy_timeout=5000`、`foreign_keys=ON`；业务库与检查点库分开；备份成对。
12. 迁移：schema 版本检查；失败拒绝启动并列出修复项。

### 不要做

- 不要改变状态机、枚举、去重语义、`auto_review` 语义、`chat_session.status`（`draft/active/terminal`）语义。
- 不要把 `report_meta` 合并进 `report_md` 或仅存为 JSON 文本而不建列（查询/审计需要）。
- 不要为批量行设置 `waiting_human` 或 `expired`。
- 不要用 `status` 反推 `auto_review`。
- 不要允许单独删除批量来源诊断（会破坏 `batch_tasks.counts` 与导出）；DELETE 契约仅允许非批量终态诊断。
- 不要把 `input_fingerprint` 暴露为对外字段；不要为批量/eval 写入 `active_fingerprint_key`。**批量行仍必须计算并保存 `input_fingerprint`（`fingerprint_scope=trace`）供追溯**；eval 不计算指纹；RT-17 查询排除 `input_type='csv_batch'`（ARCH §4.1.2、§4.1.4）。

### 需要回报的冲突

- 若物理实现无法支持"部分唯一索引 + 清空时机"，立即回报，不得改用"先查后插"蒙混。
- 若 SQLite 版本不支持部分索引，升级 SQLite 或给出等价原子方案。

---

## 3. 后端 Agent 清单

**必读**：ARCH §2、§3、§4、§5、§6、§7。

### 必须落地

1. `backend/app/runtime/state.py`：`DiagnosisState` 与 ARCH §3.1 一致；只放 JSON 可序列化值。
2. `runtime/routing.py`：RT-01~RT-20 纯函数；RT-05 优先，RT-08 优先于 RT-07；批量/eval 不进入人工中断；`clarify` 仅限 `single + nl/chat`。
3. `runtime/graph.py`：节点与边按 §3.2；`clarify`/`human_review` 用 `interrupt()`，副作用不得在 `interrupt()` 前；含 `aborted`、`row_failed`、`sample_failed`、`auto_review_report`、`auto_confirm_report`。
4. `runtime/deadline.py`：每节点 `asyncio.wait_for(remaining)`；超时进 `timeout_finalize`，不写报告；每次 resume 重置 `deadline_at`。
5. `runtime/interrupts.py`：TTL 懒判定 + 60s 扫描；版本条件更新；`Idempotency-Key` 重放；review round 2 禁 supplement。
6. `runtime/events.py`：事件先落库再广播；SSE 回放；心跳 15s；终态关闭；批量事件独立；`expired` 事件落库并与 `status.to=expired` 同步。
7. 创建诊断：API 前置校验 + `input_fingerprint` 创建前计算 + `active_fingerprint_key` 原子插入；命中 RT-17 返回 200 `deduplicated=true`。
8. Chat **`POST /messages` 是非变更操作**：`draft` 只做轻量抽取并返回抽取确认卡（`diagnosis_id=null`、`version=null`、`interrupt=null`、`stream_url=null`、会话仍 `draft`）；`active+clarification` 只返回补充卡（`ChatSupplementResponse`，`version` 取当前快照），**不写状态、不写检查点**；`active+review` → 409 `CHAT_DECISION_REQUIRED`；`active+running` → 409 `DIAGNOSIS_STATE_CONFLICT`；`terminal` → 409 `CHAT_SESSION_CLOSED`。
9. Chat **`POST /chat/sessions/{id}/confirm`**（端点 #35）：仅 `draft` 可确认，`active` → 409 `CHAT_SESSION_ALREADY_ACTIVE`、`terminal` → 409 `CHAT_SESSION_CLOSED`；`features` 必填、`device_id` 必填、**值为 `null` 的键一律 422 `VALIDATION_FAILED`**（不按缺失静默处理）；7 项完整 → 计算指纹并执行 RT-17（命中 200 + 已有 `diagnosis_id/version` + `deduplicated=true`，未命中 202 新建）；`device_id` 齐备但其余缺失 → 202 新建、指纹与 `active_fingerprint_key` 为 null，`parse_input` 后 RT-02 进入 `clarify`；同一 `message_id` 或同一 `Idempotency-Key` 重放返回首次结果（200），不得重复创建。
10. `auto_review`：RT-18 置位；持久化；缺项时 `degraded` 且保留 true；单条恒 false。
11. `resolve_status`：缺项优先；终态不可逆；`failed_timeout` 无报告。
12. 批量：`BatchRunner` 并发 2；行失败隔离；取消/超时只停调度；计数事务更新；启动对账。
13. 报告：8 要素自检 + 引用校验 + 安全过滤；最多修复一次；免责声明不可删。
14. LLM：`response_format=json_object` + Pydantic 校验 + 1 次重试 + 规则兜底；预算取剩余时间。
15. 契约：Pydantic v2 → OpenAPI 3.1 → `docs/openapi.json`；CI diff；禁止手写与 ARCH 不一致的 DTO。**`/messages` 的 `draft` 抽取卡本期强制交付命名 Schema**（`ChatExtractionResponse` 或等价命名模型，纳入 OpenAPI），不得只靠 JSON 示例（交付要求，非契约变更；来源 ARCH 验收日志 §D 第 2 条非阻断观察）。
16. 安全：bcrypt cost 12；Cookie 会话；Origin 校验；上传白名单/限额；Markdown 禁 HTML；日志脱敏。

### 不要做

- 不要在节点里实现特征规则、置信度公式或报告模板；放领域模块。
- 不要在 SSE 里传大段报告；报告走 `/report.md`。
- 不要为单条诊断提供取消端点（PRD 明确不做）。
- 不要自动重跑进程重启时 `running` 的诊断；按对账置 `failed(PROCESS_RESTART)`。
- 不要允许 `DELETE /diagnoses/{id}` 删除批量来源诊断（返回 409），否则批量计数与导出不一致。
- 不要接受 `features` 中的 `null` 值；不要为 `/confirm` 的 RT-17 命中重复执行诊断。
- NL/chat **除 `device_id` 外的**缺失字段进入 clarification，不得 422；`device_id` 缺失仍 422 `DEVICE_ID_INVALID`、不创建诊断。Chat 首条消息不得直接创建诊断，必须走 `/chat/sessions/{id}/confirm`。
- 不得为通用 202 示例固定 `input_type:"form"`（ARCH 验收日志 §D 第 4 条）：创建响应示例应使用占位值，或分别给出 form/nl/chat 示例，避免被误读。

### 测试优先

先写 `tests/unit/test_routing.py` 覆盖 RT-01~20，再写 `tests/orchestration` 注入假 LLM/Skill，并补 chat 端点契约测试（draft 不建诊断、confirm 200/202/409/422、null 键 422、幂等重放）；最后接真实 DeepSeek 跑评测。

---

## 4. 前端 Agent 清单

**必读**：ARCH §5、§8；UIUX V1.2.0 §0.5.1、§2、§4、§5、§6、§7、§8、§10、§11、§12、§13。

### 必须落地

1. 由 `docs/openapi.json` 生成 `frontend/src/api/schema.d.ts`；不手写 DTO。
2. 认证：`GET /auth/me` 启动校验；401 跳登录；423 倒计时；退出清状态。
3. SSE hook：`EventSource` + Cookie；**依赖服务端 `retry: 3000` 原生重连，不手写重复建流**；监听 `snapshot/step/status/interrupt/report/expired/error/heartbeat`；终态 `close()`；连续 3 次失败关闭 SSE 转 **2s** 轮询 `GET /diagnoses/{id}`（批量转 `GET /batches/{batch_task_id}`），恢复后再建流；`seq` 去重。
4. 状态矩阵：**以 UIUX §4.4 为唯一显示口径**（含 17 个显示态：上传中、解析中、预检失败、会话过期、SSE 断线、空态/空历史等纯 UI 态），ARCH §8.4 仅作状态映射；`failed_timeout` 必须有"超时失败"卡片；`degraded + auto_review` 双标注且顺序"缺项降级 → 待人工复核（批量模式）"；`degraded_review` 无确认按钮；批量进度不使用服务端 `progress`，由 `counts` 计算（DEV-02）；上传/解析/预检失败/SSE 断线/会话过期/空态均纳入验收。
5. 中断面板：clarification/review 共用载荷；round 2 隐藏补充；前端按建议为每次决策生成并复用 `Idempotency-Key`（可选头，非硬性契约）；提交带快照 `version`。
6. 错误映射：401/403/409/422/423/502/503/500；字段错误定位；`VERSION_CONFLICT` 自动刷新快照。
7. 报告：`react-markdown` + `remark-gfm`，`skipHtml`；禁用原始 HTML；导出解析 `filename*`。
8. 上传/映射：5MB/500 行前置校验；7 必填项；3 行预览；方案复用。
9. 批量：进度、行状态、取消、导出；批量行不出现 `waiting_human/expired`。
10. **对话入口（UIUX V1.2.0 新增）**：
    - 进入页签即 `POST /chat/sessions` 建 `draft` 会话；**首条消息 `POST /messages` 只渲染抽取确认卡，不创建诊断、`diagnosis_id=null`、不建立 SSE 诊断流**；确认卡内嵌消息流、非模态。
    - 用户修改后点确认 → `POST /chat/sessions/{id}/confirm`（`text` + `features`）。**仅 `device_id` 缺失时禁用确认按钮**；其余 6 特征缺失允许提交，创建后按 RT-02 进入 clarification（DEV-04）。
    - `features` 中值为 `null` 的键必须剔除后再提交；`device_id` 不接受 `null`。
    - 7 项完整且命中 RT-17 → 200 + 已有 `diagnosis_id` + `deduplicated=true`：当前会话即绑定该已有诊断（写入 `diagnosis_id`，会话变 `active`），并直接打开该诊断到右栏，**不新建流、不重复渲染**，Toast"已复用相同输入的诊断"；已有诊断 `running/waiting_human` 按原状态渲染，不重置决策；若该诊断已被其他会话绑定 → 409（见 §7 TBD-I）。未命中 → 202 新建，**此时才建立该诊断的 SSE 流**（`stream_url`）。
    - 自然语言页签与对话页签共用同一抽取确认卡、同一字段校验与"用户修正"留痕；修改提交需在 trace 中体现 `user_correct`。
    - 会话 409 界面动作：`CHAT_DECISION_REQUIRED` → 禁用输入 + 展示 review 面板；`DIAGNOSIS_STATE_CONFLICT` → 提示执行中 + 可刷新；`CHAT_SESSION_CLOSED` → 禁用输入 + "新建对话"；`CHAT_SESSION_ALREADY_ACTIVE` → 直接打开已有诊断。
    - `active + clarification` 下自由文本只返回补充卡、**不直接改状态**；用户确认后走 `POST /diagnoses/{id}/resume`（`decision=supplement`，`version` 取快照）；未确认前不得提交 resume（关闭/切换/刷新均不写入）。
    - 会话 1:1 诊断；诊断终态后会话 `terminal`，输入禁用并提示新建对话。
11. 快照展示 `retry_count`、`review_round`、`report_retry_count`、`duration_ms`；报告元信息用顶层 `report_meta`。
12. 评测：只读；5 指标卡 + 超时率卡；混淆矩阵 6×7；bad case 20/页；空态；"待复核"按 `0 / 120` 或 `N/A` 展示并注明"评测样本不做待复核"（DEV-01）。
13. 可访问性：≥1024px；键盘可达；对比度；`prefers-reduced-motion`。
14. Design Token：颜色、间距、字号一律取自 UIUX §2 令牌（`var(--…)`/AntD 主题映射），组件内禁止写死十六进制值；按 UIUX §10 组件规范、§11 文案规范、§13 验收清单实现与验收。

### 不要做

- 不要用 `innerHTML` 渲染报告。
- 不要在 EventSource 上设置自定义头（浏览器不支持）；靠 Cookie。
- 不要缓存会话令牌到 localStorage。
- 不要把 `degraded_review` 当成"等待人工确认"而轮询 resume。
- 不要手写 SSE 指数退避（1/2/4/8s）；不要使用 3s 轮询；不要为同一诊断重复建流。
- 不要在首条消息阶段创建诊断或渲染"诊断执行中"过程卡片。
- 不要靠"服务端进度字段"渲染批量进度；不要轮询 clarification 期间的状态变更（自由文本不落库）。

---

## 5. 测试 Agent 清单

**必读**：ARCH §4.10、§10.2、附录 B、附录 E；UIUX V1.2.0 §7.6 交互口径。

### 必须覆盖

1. 契约测试：每个端点成功 + 错误；所有 JSON 示例过 Schema；SSE 事件夹具过 `SseEvent`。
2. 路由：RT-01~20 每条至少 1 条；RT-05 优先、RT-08 优先、批量/eval 隔离。
3. 指纹：结构化/NL/chat 时序；并发双开；批量重复行；过期清空；`csv_batch` 不参与 RT-17 去重，但仍计算并保存 `input_fingerprint`（`fingerprint_scope=trace`）供追溯；eval 不计算指纹。
4. 中断：clarification/review、round 2、补充重建 revision、confirm 不重跑、TTL 双机制、并发版本锁。
5. **Chat 入口（新增）**：`draft` 首条消息 200 + `diagnosis_id=null` 且不产生诊断/事件；`/confirm` 7 项完整未命中 → 202 新建并产生 `stream_url`；命中 RT-17 → 200 + `deduplicated=true` 且不重复执行；缺 `device_id`/`features` → 422 不创建；`features` 含 `null` → 422；`active/terminal` confirm → 409；`active+review/running` 发消息 → 409；同一 `message_id`/`Idempotency-Key` 重放 → 200 首次结果；clarification 自由文本只返回补充卡且不改状态，确认后 resume 携带 version。
6. 超时：各执行节点（至少 `parse_input`/`retrieve`/`diagnose`/`report`）分别注入 >15s 延迟（不是恰好 15s）；`failed_timeout` 无报告；resume 重置窗口。**节点覆盖面属测试自定，非契约硬性要求**（ARCH §4.6 只要求“注入 >15s 延迟”）。
7. 状态：`degraded` 优先、`auto_review` 保留、`degraded + auto_review` 双标注、批量计数守恒、取消/超时运行行完成。
8. 报告：8 要素、缺项修复一次、免责声明、低置信标注、导出内容一致。
9. 安全：越权 404、CSV 公式注入、XSS、提示词注入、敏感词。
10. 浏览器：Chrome/Edge/Firefox/Safari 最新两个大版本；SSE+Cookie；对话 `draft → 确认卡 → confirm → 流建立` 全链路。

### 夹具修正

- AC-DG-20：首次 0.62、重试后 0.62；首次 <0.5 时 `retry_count=0`。
- AC-DG-21：注入 >15s，不用恰好 15s。
- AC-IN-21：运行中行允许完成；未开始行 `cancelled(TASK_TIMEOUT)`。
- AC-RP-05：明确首次与重试后均 0.62；`retry_count=1`。
- AC-IN-14：抽取确认卡修改后写 `diagnosis_steps.event=user_correct`，**不改变 `diagnosis_revision`**；前端按 UIUX §7.5 记录"用户修正"。
- 置信度 0.8 归 high。
- KPI-02 分母 = `report_count`。
- AC-IN-12/NL：`device_id` 缺失 422（不创建），其余缺失创建后进入 clarification；`/nl/extract` 的 `partial` → `recommended_action=clarify`。

---

## 6. 跨文档偏差登记（UIUX V1.2.0 §0.5.1）

| 编号 | 偏差/矛盾 | 本文取值（下游按此实现） |
| --- | --- | --- |
| DEV-01 | PRD §4.5.1 `eval_sample.status` 无 `degraded_review`；ARCH §4.2.1 规定 eval 低置信自动确认；PRD §3.10.3.6 要求统计该计数 | 评测样本不产生 `degraded_review`；评测页显示 `0 / 120` 或 `N/A` 并注明"评测样本不做待复核"；不新增 eval 状态 |
| DEV-02 | ARCH §8.7 `completed_rows` 含取消行、`progress=completed_rows/total_rows`；PRD KPI-04 与 UIUX 的"已完成"不含 `cancelled` | 两条口径分开：①**进度条分母 = `total_rows`**，`cancelled` 不计入"已完成"（UIUX §8.2），故进度由 `counts` 计算、不直接渲染服务端 `progress`；②**KPI-04 成功率分母 = `total_rows - cancelled`**（ARCH §5.4.7、§4.6；`failed`/`failed_timeout` 计入分母） |
| DEV-03 | PRD §2.5.8"首次发送消息即创建诊断" vs ARCH §8.8"确认后才创建" | 以 ARCH 为准：`draft` → 首条消息只抽取 → `/confirm` 创建诊断 |
| DEV-04 | PRD §2.5.8"任一必填缺失禁用确认" vs ARCH §5.4.6"仅 `device_id` 必填" | 以 ARCH 为准：仅 `device_id` 缺失时禁用确认；其余 6 特征缺失允许提交并进入 clarification |

> 基线（PRD/ARCH/UIUX）本轮均不修改；如后续修订，需同步本表与 ARCH §10.4。

---

## 7. 风险与待确认

| 编号 | 事项 | 影响 | 建议 |
| --- | --- | --- | --- |
| TBD-A | `degraded_review` 是否需要后续人工复核动作 | 当前是终态标签，无 resume 端点 | 本期按标签交付；如要动作需新增 FR/端点 |
| TBD-B | `auto_review`/`report_meta`/`report_title` 回写 PRD 字典 | DB 文档需承接 | 在 DB 设计文档登记 |
| TBD-C | NL/chat 抽取是否计入 15s | KPI-03 口径 | 当前不计入；评测以结构化样本为主 |
| TBD-D | `Idempotency-Key` 是否强制 | 恢复幂等 | ARCH §5.1.8 标为可选；前端按建议为每次用户决策生成并复用 key（不做硬性 422 校验），后端可选校验；本项不再作为待确认阻塞 |
| TBD-E | 生产数据库加密实现 | FR-SY-05 | DB/部署阶段定 |
| TBD-F | 评测页 `failed_timeout` 明细 | P1-04 | API 已支持，前端按 §8.9 实现 |
| TBD-G | ARCH 附录 F.2 的 P0-01 历史证据仍写"`nl` 仅强制 `input_type`+`text`"，与 F.4/§5.4.6/§5.6.2 的"`device_id` 必填"不一致（ARCH 验收日志 §D 第 1 条） | 读者可能误用旧口径 | 后端/测试以 §5.4.6 与 F.4 为准；待 ARCH 文档勘误（C-008）修正附录 F.2 |
| TBD-H | `/messages` 的 `draft` 抽取卡只有 JSON 示例、无命名 Schema（ARCH 验收日志 §D 第 2 条） | 契约测试与前端类型生成缺少锚点 | 本期强制交付命名 Schema（`ChatExtractionResponse` 或等价），纳入 OpenAPI；前端按 §5.4.5 字段实现，不手写 DTO |
| TBD-I | `/confirm` 命中 RT-17 时，若已有诊断已绑定另一个 chat session，"会话绑定该已有诊断"与"会话 1:1 诊断"边界重叠（ARCH 验收日志 §D 第 3 条） | 一诊断多会话会导致历史/消息归属歧义 | **按 ARCH §5.4.5 落地**：命中 RT-17 返回 200 后，当前会话绑定该已有诊断（写入 `diagnosis_id`，会话变 `active`）；若该诊断已被其他会话绑定，返回 409（暂沿用 `CHAT_SESSION_ALREADY_ACTIVE`）；**该码原语义为"会话已绑定诊断"，此处复用属临时约定；如新增专属错误码，须先登记 ARCH §10.4 C-008 并同步 UIUX §7.6/§8.5 界面动作**；不得静默改为"不绑定"；如未来产品要求共享诊断，需先登记 ARCH §10.4 C-008 后再改语义 |
| TBD-J | §5.4.6 通用 202 示例仍写 `input_type:"form"`（ARCH 验收日志 §D 第 4 条） | 可能被误读为所有入口固定 `form` | 后端生成示例使用占位值或按入口分列；前端/测试不得据此断言 `input_type` |
| TBD-K | `/confirm` 幂等重放与 409 的区分（UIUX 第三轮残留 P2-2） | 网络重试可能被误判为 409 | 同一 `message_id`/`Idempotency-Key` 重放必须返回 200 首次结果；只有"非 draft 的新 confirm"才 409 |
| TBD-L | 评测集冻结口径与旧实现不同：120 条按 `正常30/HDF20/PWF20/OSF20/TWF20/RNF10`、固定种子 `20261024` 生成；多标签按 `OSF>HDF>PWF>TWF>RNF`；edge 20 条为 `EDGE-xx` 独立描述样本、不计入 KPI-01 | 旧实现为“60 故障 + 40 正常”并把 edge 计入 120，历史评测批次不可直接对比 | 后续评测统一以本口径为准；如变更种子/配额需登记 ARCH §10.4 并新建评测批次；本次无排除 UDI，详见 `docs/EVAL-评测报告.md` |
| TBD-M | HDF 规则温度差判定取 `≤ 8.6 K`（PRD 语义 `< 8.6 K`）：AI4I CSV 保留 1 位小数，标注为 HDF 的行存在恰好 8.6 K；LLM 归因与提示词按 `backend/prompts/` 版本化（`reporter-v1`/`diagnostician-v1`） | 若严格按 `< 8.6 K`，HDF 有 7 条样本无法命中；若后续更换数据集粒度需复核该闭区间 | 已登记 ARCH §10.4 C-009；PRD 不修改；更换数据源或标签口径时同步复核 |
| R-05 | AI4I 标签噪声：正常集中存在 `tool_wear ≥ 190 min` 的样本（按 AI4I 标签为正常，按 PRD TWF 规则命中）；RNF 在特征上与正常/边界样本不可分 | 这两类错误无法通过规则或诚实 LLM 归因消除，KPI-01 六分类上限受限 | 评测报告单列 RNF 与剔除 RNF 后的准确率；不得为达标放宽 RNF 或修改 PRD |
| R-01 | DeepSeek Key/额度 | 评测与联调 | 第 0 阶段先验证 |
| R-02 | BGE-M3 内存 | 16GB 建议 | 启动预加载；必要时 ONNX |
| R-03 | SQLite 写锁 | 批量+检查点 | 分库/WAL/busy_timeout/单进程 |
| R-04 | 批量映射旁路存储的位置与重启对账依赖：映射不在 DB（`batch_tasks` 不新增映射列），持久化于 `storage/batches/<batch_task_id>.json`（ARCH §10.4 C-008） | 该目录缺失/未随库迁移时，重启后 `queued` 任务无法还原映射，`pending` 行无法继续调度 | 部署与备份须将 `storage/batches/` 与 `storage/app.db`、`storage/checkpoints.sqlite3` 一并复制；旁路文件与批量任务同生命周期保留 |

**UIUX 第三轮残留 P2（不阻塞冻结，实现阶段处理）**

1. `features` 剔除 `null` 键未在 UIUX 复述：前端必须按 ARCH §5.4.5 剔除，否则 422。
2. `/confirm` 幂等重放与 409 区分（见 TBD-K）。
3. 首条消息阶段不建流、`/confirm` 202 后才建流：UIUX 已写前者，后者需在实现说明中显式落地（见 §4-10）。

---

## 8. 建议调用的 Skill

| 场景 | Skill | 用途 |
| --- | --- | --- |
| 后端/测试实现 | `tdd` | 先写路由/契约测试，再实现 |
| 代码审查 | `TRAE-code-review` | 检查契约一致性、状态机、并发 |
| 安全审查 | `TRAE-security-review` | Cookie/CSRF/上传/注入/越权 |
| 前端验收 | `agent-browser` 或 `TRAE-browseruse` | 四入口、SSE、批量、报告渲染、对话确认链路 |
| 设计再压测 | `grill-me` | 对新增端点/状态变更做压力测试 |
| 下一轮交接 | `handoff` | 生成新的交接文档 |

---

## 9. 完成定义

- [ ] DB DDL 实现 §7 全部不变量，且通过并发/唯一约束测试（含部分唯一索引与终态清空）。
- [ ] 后端 OpenAPI 与 ARCH V1.2.0 一致，CI diff 为空；`/confirm`、`/messages` 端点与 Schema 齐备。
- [ ] 前端类型由 OpenAPI 生成，无手写 DTO；对话 `draft → 确认卡 → confirm → 流` 链路无重复建流。
- [ ] RT-01~20、指纹、TTL、版本锁、超时、批量、报告自检、chat 409/422/幂等均有测试。
- [ ] AC 全集可在 API/图/DB 层构造，不依赖演示话术。
- [ ] 120 条评测集 KPI-01~05 达标。
- [ ] 四浏览器冒烟通过。

---

**交接完成标志**：数据库设计文档、后端 OpenAPI、前端类型三者与 ARCH V1.2.0 对齐；交互实现与 UIUX V1.2.0 对齐；任何偏离均登记到 ARCH §10.4 与本文件 §6/§7。
