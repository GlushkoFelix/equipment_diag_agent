# HANDOFF 冷启动验收日志（V1.2.0）

| 项目 | 内容 |
| --- | --- |
| 待审查文档 | `docs/HANDOFF-系统架构与API契约交接.md`（V1.2.0） |
| 上游基线 | `docs/ARCH-系统架构与API契约.md` V1.2.0（冻结）、`docs/UIUX-设备故障诊断智能体.md` V1.2.0（冻结）、PRD V3.0.0（冻结） |
| 验收依据 | 上述三份正文 + `docs/log/ARCH验收日志.md`（V1.2.0 复审通过）+ `docs/log/UIUX验收日志.md`（第三轮通过，残留 3 条 P2） |
| 审查方式 | 冷启动；仅依据正文与验收日志逐条比对审查重点 1~5，不采信交接文档自述 |
| **最终判定** | **【驳回】**（P1 × 2，P2 × 4，P3 × 2） |

---

## 一、阻塞缺陷（P1）

### P1-1 §6 DEV-02 的 KPI-04 分母写反，与 ARCH V1.2.0 直接冲突

| 项 | 内容 |
| --- | --- |
| 位置 | HANDOFF §6 表格 DEV-02 行（"本文取值（下游按此实现）"列） |
| 原文 | "批量进度由 `counts` 按'终态行、不含 `cancelled`'计算，服务端 `progress` 不直接渲染；**KPI-04 分母含取消行（`total_rows`）**" |
| 冲突证据 | ARCH §5.4.7："`success_rate = (succeeded + degraded + degraded_review) / (total_rows - cancelled)`；分母含 `failed`/`failed_timeout`，**不含 `cancelled`**"；ARCH §4.6："`cancelled` 不进分母"；UIUX §8.2："`cancelled` 不计入已完成，与 KPI-04 对 `cancelled` 的处理一致；进度分母为总行数" |
| 危害 | 同一行前半句写"PRD KPI-04 与 UIUX 的'已完成'不含 `cancelled`"，后半句却要求 KPI-04 分母含取消行，自相矛盾；后端/测试按此实现将导致 KPI-04 断言错误、批量成功率偏低。 |
| 修复 | 拆成两条口径分别表述：①**进度条分母** = `total_rows`（UIUX §8.2，`cancelled` 不计入"已完成"）；②**KPI-04 成功率分母** = `total_rows - cancelled`（ARCH §5.4.7）。删除"KPI-04 分母含取消行（`total_rows`）"。 |

### P1-2 §7 TBD-I 的取值与 ARCH §5.4.5 字面冲突，且未登记到 ARCH §10.4

| 项 | 内容 |
| --- | --- |
| 位置 | HANDOFF §7 表格 TBD-I 行 |
| 原文 | "本期按'仅打开已有诊断、**不再二次绑定另一会话**'实现，并在 DB 约束上保证会话至多一个 `diagnosis_id`" |
| 冲突证据 | ARCH §5.4.5："命中 RT-17：200，返回已有 `diagnosis_id`…**会话绑定该已有诊断**，不重复执行"；"会话从 `draft` 变为 `active`，并 **1:1 绑定该诊断**（新建或 RT-17 复用的已有诊断）"；ARCH §7.3 不变量 11 仅约束"一个 `chat_session` 至多绑定一个 `diagnosis_id`"，未定义"不绑定"分支 |
| 危害 | 下游若照此实现，`/confirm` 命中 RT-17 返回 200 后 `chat_sessions.diagnosis_id` 可能为空，`GET /chat/sessions/{id}` 与 ARCH §5.4.5 响应示例不一致；DB、后端、前端三方将出现两套绑定语义。HANDOFF 自述"三者冲突一律登记到 ARCH §10.4，不得静默择一"，此处属静默择一。 |
| 修复 | 二选一并留痕：①按 ARCH §5.4.5 绑定当前会话；若该诊断已被其他会话绑定，按 ARCH 验收日志 §D 第 3 条的建议返回 409（或明确允许共享并在 `chat_sessions` 增加约束）。②确需"仅打开、不绑定"，须同步修改 ARCH §5.4.5 响应语义与 §7.3 不变量，并在 ARCH §10.4 新增 C-008 登记后，本行落地。修复前不得作为"本期取值"下发。 |

---

## 二、非阻塞观察（P2）

### P2-1 §4-5 / §7 TBD-D 把"建议"写成"强制"

- 位置：HANDOFF §4-5"中断面板…提交带 `version` 和 `Idempotency-Key`"；§7 TBD-D"前端强制；后端可选"。
- 依据：ARCH §5.1.8 将 `Idempotency-Key` 标为"**否**（可选）"；§4.4.2 为"**建议**前端为每次用户点击生成一个 key"；§10.5 TBD-D 原文"**前端建议强制**；后端可选兼容"。HANDOFF 同时又在 §7 标注该事项"待确认"，形成"必须落地"与"待确认"并存。
- 建议：改为"前端按建议为每次决策生成并复用 key；后端可选校验"，或明确裁定为强制并同步登记 ARCH §10.4；二者择一，避免下游把可选头当硬性契约做 422。

### P2-2 §4-4 状态矩阵引用错位，漏掉 UIUX §4.4 的纯 UI 显示态

- 位置：HANDOFF §4 必须落地第 4 条"状态矩阵：§8.4 全状态"。
- 依据：ARCH §8.4 只覆盖 11 个诊断状态；UIUX §4.4 明确为"**唯一显示口径**"，含 17 个显示态（上传中、解析中、预检失败、会话过期、SSE 断线、空态/空历史等 6 个纯 UI 态不在 ARCH §8.4）。
- 建议：改为"以 UIUX §4.4 为唯一显示口径，ARCH §8.4 仅作状态映射"，并把上传/解析/预检失败/SSE 断线/会话过期/空态纳入验收。

### P2-3 §0 阅读顺序与前端清单缺 Design Token、组件与文案规范

- 位置：HANDOFF §0 第 4 条（前端阅读顺序）与 §4 必须落地清单。
- 缺口：未列 UIUX §2（Design Tokens）、§10（组件规范）、§11（文案规范）、§13（UI 验收清单）；§4 亦无 Ant Design 5 主题映射、`prefers-reduced-motion` 之外的动效令牌要求。UIUX §13.1 是前端验收依据，遗漏会导致验收口径缺锚点。
- 建议：阅读顺序补 `UIUX §2、§10、§11、§13`；§4 增加"颜色/间距/字号一律取自 Design Token，组件内禁止写死十六进制".

### P2-4 §5 夹具修正漏两条 ARCH 附录 E 条目

- 位置：HANDOFF §5"夹具修正"。
- 缺口：①未列 **AC-IN-14**（抽取确认卡修改须写 `diagnosis_steps.event=user_correct`，不改 `diagnosis_revision`）；②**AC-RP-05** 只写"首次与重试后均 0.62"，漏附录 E 原文的"`retry_count=1`"。
- 依据：ARCH 附录 E 第 5、6 行；ARCH §4.5.2、附录 F。
- 建议：补齐两条，并在前端/测试清单中对应 `user_correct` 留痕断言。

---

## 三、可回溯性问题（P3）

1. **§7 TBD-G~J 的引用编号不可回溯**：原文多处引"ARCH 验收日志 D-1/D-2/D-3/D-4"，但 `docs/log/ARCH验收日志.md` 实际章节为"### D. 非阻断 P1 观察"下的编号 1~4，不存在 D-1~D-4 标识。内容虽与四条观察一一对应，建议改为"ARCH 验收日志 §D 第 1~4 条"。
2. **§4-1 类型生成路径缩写**：写作 `src/api/schema.d.ts`，ARCH §5.7/§8.1 与 §10.1 均为 `frontend/src/api/schema.d.ts`；建议写全路径，避免与工作台根目录混淆。
3. **§5-6 "四节点注入 >15s" 无出处**：ARCH §4.6/附录 E 只要求"注入 >15s 延迟"，未限定四个节点；建议改为"各执行节点（至少 `parse_input`/`retrieve`/`diagnose`/`report`）分别注入 >15s"并注明为测试自定覆盖面，而非契约要求。另 §3-15 在"必须落地"条目内使用"建议补 `ChatExtractionResponse`"，建议统一为"本期强制交付命名 Schema"或"可延后至 C-008"，避免强弱不清。

---

## 四、已核查通过（摘要，不再展开）

- 版本与基线：ARCH V1.2.0、UIUX V1.2.0、PRD V3.0.0 引用正确；权威顺序与"接口/SSE 以 ARCH 为准、界面以 UIUX 为准"声明正确。
- 对话入口：`draft` 首条只出卡且 `diagnosis_id=null`、不建流；`/confirm` 建诊断、RT-17 200 + `deduplicated`、缺项 RT-02、仅 `device_id` 禁用确认、`features` 剔 null/传 null 422、四类 409 与动作、澄清补充卡 + `resume(version)`、202 后建流，均与 ARCH §5.4.5/§8.8 与 UIUX §7.6 一致。
- 偏差登记：DEV-01/03/04 取值正确；TBD-G/H/J 内容正确（仅编号见 P3）。
- DB/后端/测试主体：`active_fingerprint_key` 部分唯一索引 + 终态清空、事件 seq 唯一、`report_meta_json`/`report_title`/`auto_review` 独立列、`chat_sessions` 1:1；RT-01~20、deadline、interrupts、events、`auto_review`、`resolve_status`、批量对账、OpenAPI CI、`/messages` 非变更、`/confirm` 规则均一致。
- 防伪：未残留 SSE 1/2/4/8s 退避、3s 轮询、首条消息建诊断；未复制 ARCH/UIUX 全文；未发现旧参数回潮。

---

## 五、返修后复验口径

1. 修正 P1-1、P1-2 后，DEV-02 与 TBD-I 两行须能被 ARCH §5.4.7、§4.6、§5.4.5、§7.3 逐字支撑；如涉及契约语义变化，须先登记 ARCH §10.4 再更新 HANDOFF。
2. P2/P3 可在同一轮修订，不单独阻塞；但 P2-1 若保留"强制"表述，须在 TBD-D 去"待确认"并登记。
3. 复验仍采用冷启动：只读三份正文 + 两份验收日志 + 修订后的 HANDOFF，不复用本轮结论。

**留痕**：本日志为 HANDOFF V1.2.0 首次冷启动验收记录；修订稿复验后追加新章节，不覆盖本记录。

---

# 第二轮：HANDOFF V1.2.1 冷启动复审

| 项目 | 内容 |
| --- | --- |
| 复审对象 | `docs/HANDOFF-系统架构与API契约交接.md` V1.2.1 |
| 上游基线 | ARCH V1.2.0（冻结）、UIUX V1.2.0（冻结）、PRD V3.0.0（冻结） |
| 复审依据 | 三份正文 + `docs/log/ARCH验收日志.md`、`docs/log/UIUX验收日志.md` + 本日志第一轮记录 |
| 复审方式 | 冷启动；逐条复核第一轮驳回项，并独立全量比对 ARCH/UIUX，不复用第一轮结论 |
| **本轮判定** | **【驳回】**（P1 × 1，P2 × 1；第一轮 P1/P2/P3 全部闭环） |

## 一、第一轮驳回项闭环复核（全部通过）

| 项 | 状态 | 取证 |
| --- | --- | --- |
| P1-1 DEV-02 | 通过 | §6 已拆为"进度条分母 = `total_rows`"与"KPI-04 分母 = `total_rows - cancelled`"，删除了"KPI-04 分母含取消行"；与 ARCH §5.4.7、§4.6 及 UIUX §8.2 一致 |
| P1-2 TBD-I | 通过 | §7 TBD-I 已改为"按 ARCH §5.4.5 落地、当前会话绑定该已有诊断、已被其他会话绑定返回 409"，删除"不再二次绑定另一会话"，并注明共享诊断须先登记 ARCH §10.4；§4-10 前端行为同步 |
| P2-1 Idempotency-Key | 通过 | §4-5 改为"按建议生成、可选头、非硬性契约"；§7 TBD-D 注明"本项不再作为待确认阻塞" |
| P2-2 状态矩阵 | 通过 | §4-4 改为"以 UIUX §4.4 为唯一显示口径，ARCH §8.4 仅作映射"，补 17 个显示态及上传/解析/预检失败/SSE 断线/会话过期/空态 |
| P2-3 阅读顺序/Design Token | 通过 | §0 前端阅读顺序补 UIUX §2、§10、§11、§13；§4-14 补 Design Token 与禁止写死十六进制 |
| P2-4 夹具修正 | 通过 | §5 已补 AC-IN-14（`user_correct`、不改 `diagnosis_revision`）与 AC-RP-05 的 `retry_count=1` |
| P3 引用/路径/节点 | 通过 | TBD-G~J 及 §3-15/§3-16 均改为"ARCH 验收日志 §D 第 1~4 条"；路径为 `frontend/src/api/schema.d.ts`；§5-6 改为"各执行节点分别注入 >15s，属测试自定覆盖面" |

**残留旧错误复查**：全文无"KPI-04 分母含 cancelled"、无"仅打开不绑定"（仅保留"不得静默改为不绑定"的禁止句）、无"Idempotency-Key 强制"、无 D-1~D-4 编号。

**上游未改核查**：`ARCH`、`UIUX` 均早于第一轮驳回日志与 HANDOFF V1.2.1 的修订；两份文档版本头仍为 V1.2.0，未发现正文被改动。

## 二、本轮阻塞项（P1）

### P1-3 §2"不要做"第 6 条与 §5-3 指纹测试口径，和 ARCH §4.1.2/§4.1.4 冲突

| 项 | 内容 |
| --- | --- |
| 位置 | HANDOFF §2"不要做"第 6 条；§5"必须覆盖"第 3 条 |
| 原文 | §2："不要把 `input_fingerprint` 暴露为对外字段**或写入批量/eval 诊断**"；§5-3："指纹：…；`csv_batch` 不参与。" |
| 冲突证据 | ARCH §4.1.2："`csv_batch` 每行**仍计算并保存指纹**，供追溯与排查；数据库查询 RT-17 时必须排除 `input_type='csv_batch'`"；ARCH §4.1.4："批量行不写入 `active_fingerprint_key`，**只写 `input_fingerprint` 供追溯**"；ARCH §3.1 状态含 `fingerprint_scope: "trace"` |
| 危害 | DB Agent 若按此条执行，会跳过批量行 `input_fingerprint` 的落库，直接违反 ARCH §4.1.2/§4.1.4 的追溯要求；测试条目的"`csv_batch` 不参与"也可能被误读为"不计算指纹"，导致追溯与 RT-17 排除两条断言混淆。 |
| 修复 | 改为："不要把 `input_fingerprint` 暴露为对外字段；不要为批量/eval 写入 `active_fingerprint_key`。**批量行仍必须计算并保存 `input_fingerprint`（`fingerprint_scope=trace`）供追溯**；eval 不计算指纹；RT-17 查询排除 `input_type='csv_batch'`。"§5-3 改为"`csv_batch` 不参与 RT-17 去重，但仍计算并保存指纹供追溯"。 |

> 说明：本条为 V1.2.0 遗留、第一轮未覆盖，按冷启动独立比对发现，不属于 V1.2.1 返修回退。

## 三、本轮非阻塞项（P2）

### P2-5 §3"不要做"第 7 条的 device_id 例外未写明

- 位置：HANDOFF §3"不要做"第 7 条"NL/chat 缺失字段必须进入 clarification，**不得 422**"。
- 冲突：ARCH §5.4.6 与附录 F.4 规定 `device_id` 缺失 → 422 `DEVICE_ID_INVALID`、不创建诊断；只有 `product_type` 与 5 个数值特征可缺失后进入 clarification。本条与同文件 §1、§3-9 的表述不一致。
- 建议：改为"NL/chat **除 `device_id` 外的**缺失字段进入 clarification，不得 422；`device_id` 缺失仍 422 `DEVICE_ID_INVALID`"。

## 四、P3 提示（不阻塞）

1. **§7 TBD-I 的 409 复用了 `CHAT_SESSION_ALREADY_ACTIVE`**：ARCH §5.2 将该码定义为"会话已绑定诊断，不能再次 confirm"，与"诊断已被其他会话绑定"语义不同。当前"暂沿用"可运行，但建议在 C-008 中新增专属错误码或明确该码适用边界，并同步 UIUX §7.6/§8.5 的界面动作。
2. **§3-15 "本期强制交付命名 Schema"**：来源是 ARCH 验收日志 §D 第 2 条的非阻断观察。建议标注"交付要求，非契约变更"，避免下游误认为 ARCH 已强制。

## 五、第二轮结论

- 第一轮 P1-1、P1-2、P2-1~P2-4、P3 全部闭环，且未修改上游基线。
- 本轮新发现 P1-3（批量指纹落库口径与 ARCH §4.1.2/§4.1.4 冲突）属阻塞项；P2-5 为同轮应修的表述缺口。
- **判定：驳回。** 修复 P1-3（并顺手修 P2-5）后，按冷启动口径复验；P1-3 未闭环前不得交付下游。

**留痕**：本日志第二轮记录独立于第一轮，保留第一轮结论，不覆盖。

---

# 第三轮：HANDOFF V1.2.2 冷启动复审

| 项目 | 内容 |
| --- | --- |
| 复审对象 | `docs/HANDOFF-系统架构与API契约交接.md` V1.2.2 |
| 上游基线 | ARCH V1.2.0（冻结）、UIUX V1.2.0（冻结）、PRD V3.0.0（冻结） |
| 复审依据 | 三份正文 + `docs/log/ARCH验收日志.md`、`docs/log/UIUX验收日志.md` + 本日志第一、二轮记录 |
| 复审方式 | 冷启动；逐条复核第二轮 P1-3/P2-5/P3，并独立全量比对 ARCH/UIUX、回归第一轮全部结论 |
| **本轮判定** | **【通过，准予交付给下游】** |

## 一、第二轮驳回项闭环复核（全部通过）

| 项 | 状态 | 取证 |
| --- | --- | --- |
| P1-3 §2"不要做"第 6 条 | 通过 | 已改为"不暴露 `input_fingerprint`；不为批量/eval 写 `active_fingerprint_key`；**批量行仍计算并保存 `input_fingerprint`（`fingerprint_scope=trace`）供追溯**；eval 不计算；RT-17 排除 `input_type='csv_batch'`"，并引 ARCH §4.1.2、§4.1.4 |
| P1-3 §5"必须覆盖"第 3 条 | 通过 | 已同步为"`csv_batch` 不参与 RT-17 去重，但仍计算并保存 `input_fingerprint`（`fingerprint_scope=trace`）供追溯；eval 不计算指纹" |
| P2-5 §3"不要做"第 7 条 | 通过 | 已改为"NL/chat **除 `device_id` 外的**缺失字段进入 clarification，不得 422；`device_id` 缺失仍 422 `DEVICE_ID_INVALID`、不创建诊断" |
| P3 TBD-I 错误码 | 通过 | 已注明 `CHAT_SESSION_ALREADY_ACTIVE` 复用属临时约定，新增专属码须先登记 ARCH §10.4 C-008 并同步 UIUX §7.6/§8.5 |
| P3 §3-15 强弱标注 | 通过 | 已注明"交付要求，非契约变更；来源 ARCH 验收日志 §D 第 2 条非阻断观察" |

**与 ARCH 一致性核对**：批量指纹保存口径与 ARCH §4.1.2（"`csv_batch` 每行仍计算并保存指纹"）、§4.1.4（"只写 `input_fingerprint` 供追溯"）、§3.1（`fingerprint_scope: "trace"`）一致；`device_id` 例外与 ARCH §5.4.6、附录 F.4 一致。

## 二、旧错误与回退复查（全部清零）

- 无"写入批量/eval 诊断"表述；无未限定的"NL/chat 缺失不得 422"；无"KPI-04 分母含 cancelled"；无"不再二次绑定/仅打开不绑定"（仅保留"不得静默改为不绑定"的禁止句）；无"Idempotency-Key 强制"；无 D-1~D-4 编号。
- 第一轮 P1-1（DEV-02 两条分母）、P1-2（TBD-I 绑定 + 409）、P2-1~P2-4、P3 均无回退：DEV-02 仍为"进度分母 `total_rows` / KPI-04 分母 `total_rows - cancelled`"；TBD-I 仍为"当前会话绑定 + 已被其他会话绑定 409"。

## 三、防伪与越权核查

- **仅改 HANDOFF**：ARCH、UIUX 均早于第二轮日志与 HANDOFF V1.2.2 的修订；两份文件大小与版本头（V1.2.0）均未变化。
- 未复制 ARCH/UIUX 全文；未残留 SSE 1/2/4/8s 退避、3s 轮询、首条消息建诊断。
- 建议/强制：`Idempotency-Key` 保持"可选/按建议"；§3-15 已标注为交付要求；TBD-H 的"本期强制交付命名 Schema"属交付要求（非契约变更），与 §3-15 口径一致，不构成阻塞。

## 四、结论

- 第二轮 P1-3、P2-5、两项 P3 全部真实闭环，第一轮结论无回退，上游冻结基线未被修改。
- **判定：通过，准予交付给下游。** 后续若 ARCH C-008 更新（附录 F.2 勘误、TBD-I 专属错误码、RT-17 绑定语义），需同步 HANDOFF §6/§7 与相关测试。

**留痕**：本日志第三轮记录独立于前两轮，保留历史结论，不覆盖。
