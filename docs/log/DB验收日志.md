# DB 冷启动验收日志（V1.0.0）

| 项目 | 内容 |
| --- | --- |
| 待审查文档 | `docs/DB-数据库设计文档.md`（V1.0.0） |
| 上游基线 | PRD V3.0.0（冻结）、ARCH V1.2.0（冻结）、UIUX V1.2.0（冻结）、HANDOFF V1.2.2 |
| 验收依据 | 四份正文 + `docs/log/ARCH验收日志.md`、`docs/log/UIUX验收日志.md`、`docs/log/HANDOFF验收日志.md` |
| 审查方式 | 冷启动；不采信文档自述。除逐条比对正文外，抽取 §6 全量 DDL 与 §7 关键 SQL，在 **SQLite 3.50.4（Python sqlite3）** 实际执行；对拒绝路径构造数据实测 |
| 审查日期 | 2026-10-23 |
| **最终判定** | **【驳回】**（P0 × 2，P1 × 5，P2 × 9） |

---

## 一、阻塞缺陷（P0，必须修复后方可冻结）

### P0-1 §7.2 终态清指纹示例未清中断三字段，与 §5.5/§6 的 CHECK 直接冲突（实测必失败）

| 项 | 内容 |
| --- | --- |
| 位置 | DB §7.2“终态清空 active 指纹（同一条 UPDATE）”；关联 DB §5.5 关键 CHECK 第 4 条、§6 `diagnoses` 中断一致性 CHECK |
| 原文 | `UPDATE diagnoses SET status=:terminal_status, version=version+1, … , active_fingerprint_key=NULL WHERE … status IN ('running','waiting_human')` |
| 冲突证据 | §6 DDL：`status NOT IN ('waiting_human','expired')` 时 `interrupt_type`/`interrupt_payload_json`/`interrupt_expires_at` 必须全部为 NULL。§7.2 明确允许 WHERE 命中 `waiting_human`，但 SET 未清空三字段 |
| 实测 | 构造 `waiting_human`（三字段非空、active 键非空）行后原样执行 §7.2，报 `CHECK constraint failed: (status IN ('waiting_human','expired') AND … ) OR (status NOT IN (…) AND … IS NULL)`；补清三字段后同一语句通过 |
| 危害 | `review` 的 `confirm`/`abort` 若按示例直接终结（示例自述覆盖 `waiting_human`），或任何未先经 `resume` 置 `running` 的终态落库路径，全部被 CHECK 拒绝；与 §10“§7 语句均可执行”的自述矛盾；与 ARCH §4.4.2“进入终态 `version+1`”主链路冲突 |
| 修复 | ①§7.2 的 SET 增加 `interrupt_type=NULL, interrupt_payload_json=NULL, interrupt_expires_at=NULL`（`expired` 由 §7.1/§7.3 单独处理，保留三字段）；②§7 增加 `resume` 示例：`waiting_human → running`、清三字段、`version+1`（执行窗口重置由检查点承担，DB 不落 `deadline_at`），避免下游再次漏清 |

### P0-2 §5.11/§8.4 的会话删除语义静默改写 ARCH §5.4.6，且现有约束使上游语义无法实现

| 项 | 内容 |
| --- | --- |
| 位置 | DB §5.11“诊断删除时该会话及其消息级联删除”、§8.4；§6 DDL `chat_sessions.diagnosis_id … ON DELETE CASCADE`、`trg_chat_sessions_no_rebind`、`chat_sessions` CHECK |
| 上游原文 | ARCH §5.4.6 `DELETE /diagnoses/{diagnosis_id}`：“非批量诊断级联删除 `diagnosis_steps`、`diagnosis_events`；…**对话会话保留但 `diagnosis_id` 置空**” |
| 冲突证据 | 实测删除非批量诊断后 `chat_sessions` 行数 = 0（级联删除）；执行 `UPDATE chat_sessions SET diagnosis_id=NULL` 被 `CHAT_SESSION_REBIND_FORBIDDEN` 拒绝；且 CHECK 要求 `active/terminal` 时 `diagnosis_id` 必非空，即使去掉触发器也无法置空 |
| 危害 | HANDOFF §0 明确“物理 DDL → 数据库设计文档，但不得改变 ARCH 语义”。当前实现删除诊断即丢失会话与消息，与“保留会话”相反；§9 未登记，属静默改契约，DB/后端/前端会出现两套删除语义 |
| 修复 | 二选一并留痕：①按 ARCH 实现：`ON DELETE SET NULL`、放宽 CHECK 允许 `terminal + diagnosis_id IS NULL`、调整 `no_rebind` 仅禁止“改绑到另一诊断”、消息保留；②若坚持级联删除，须在 §9 新增登记（建议 D-10）并同步 ARCH §10.4，同时更新 §8.4/§5.11 与前端删除提示；不得静默择一 |

---

## 二、返修项（P1）

### P1-1 §7.1 懒判定过期不写 `expired` 事件，与 ARCH §4.4.1 及 §7.3 自述冲突

- 位置：DB §7.1 步骤 1；对照 DB §7.3 末注“扫描器与懒判定必须调用同一仓储方法（置状态 + 清键 + 写事件），不得只改状态不写事件”。
- 依据：ARCH §4.4.1：“懒判定与扫描器共用同一 `expire` 事务：置 `status=expired`、`version+1`、清 `active_fingerprint_key`、**写 `diagnosis_events(type=expired)` 并广播**；不得只改状态不发事件。”
- 现象：§7.1 的 UPDATE 只置状态、加版本、清 active、写 `finished_at`，未写事件；§7.3 扫描器写了事件。两条路径行为分叉。
- 修复：§7.1 改为调用 §7.3 同一 `expire` 事务（含 `diagnosis_events(type=expired)`），或在步骤 1 后显式写出事件插入语句；并注明懒判定同样需要广播。

### P1-2 §5.12 声称 `chat_messages` 禁止 UPDATE，但 §6 未创建对应触发器

- 位置：DB §5.12“追加写：禁止 UPDATE”；§6 DDL 触发器清单（仅 `diagnosis_steps`/`diagnosis_events`/`batch_events` 有 no-update 触发器）。
- 实测：`UPDATE chat_messages SET text=…` 执行成功，无任何拒绝。
- 危害：声明的不可变约束未落地，审计/回放可被改写；属“约束未落地 + 文档与 DDL 自相矛盾”。
- 修复：补 `trg_chat_messages_no_update`；或删除该声明（ARCH §7.3 只要求事件与轨迹只增，未要求 `chat_messages` 只增），二者必须一致。

### P1-3 PRD §4.5.2 与 DDL 的 `input_fingerprint` 必填性冲突未登记

- 位置：DB §5.5（`input_fingerprint` 可空；“完整单条/批量有值，部分 nl/chat 为空”）；§9 偏差表。
- 冲突：PRD §4.5.2 写 `input_fingerprint`“必填（单条入口）”；ARCH §4.1.2 允许 `nl/chat` 部分特征缺失时为空。DB 采 ARCH，但 §9 未登记该项。
- 危害：§9 自述“未登记即视为本文擅自改契约”；测试若按 PRD 断言“单条必填”将与 DDL 冲突。
- 修复：§9 新增登记（可并入 D-08），明确“完整单条/批量有值；`nl/chat` 部分缺失为空；eval 不计算”，引用 ARCH §4.1.2，并注明 PRD 字典下版需同步。

### P1-4 §7.5 派生 `progress` 分子含 `cancelled`，与 DEV-02/UIUX D-UI-05 口径冲突

- 位置：DB §7.5“派生展示值（不落库）”：`completed_rows = total_rows - pending_rows - running_rows`、`progress = completed_rows / total_rows`。
- 冲突：HANDOFF §6 DEV-02 ① 与 UIUX D-UI-05/§8.2 明确“进度=已完成（终态行，**不含 `cancelled`**）”；DB §2 声称 DEV-02 已处置。
- 危害：取消行被计入进度分子，前端/验收按 counts 计算时与本文公式不一致。
- 修复：拆为两个派生值：`terminal_rows = total_rows - pending_rows - running_rows`（ARCH §8.7 终态行数，含取消）；进度分子用 `succeeded_rows + degraded_rows + degraded_review_rows + failed_rows + failed_timeout_rows`（不含取消）。或删除 `progress` 公式，只保留 `counts` 并注明按 UIUX 计算。

### P1-5 §5.13 声称 `manifest_path` 由 DB 唯一约束防重复登记，但 §6 无该唯一索引

- 位置：DB §5.13“约束：…（应用校验；**DB 唯一约束防重复登记**）”；§6 `knowledge_versions` DDL。
- 实测：两个版本登记同一 `manifest_path` 成功（未触发唯一冲突）。
- 修复：补 `CREATE UNIQUE INDEX ux_knowledge_manifest ON knowledge_versions(manifest_path);`，或删除“唯一”表述，改为“应用层校验”。

---

## 三、非阻塞残留（P2，建议同轮修订）

| 编号 | 位置 | 残留项 | 修复建议 |
| --- | --- | --- | --- |
| P2-1 | §5.5 CHECK 第 5 条 vs §6 | 置信度联动是单向的：`confidence IS NULL` 时 `confidence_level` 仍可为 `high/medium/low`，与“当且仅当”不符（实测可通过） | 增加 `CHECK ((confidence IS NULL) = (confidence_level IS NULL))`，再保留 CASE 联动 |
| P2-2 | §5.5 CHECK 第 3 条 | 仅保证“失败态无报告”；`succeeded`/`degraded_review` 可无 `report_md`（实测可通过），与 ARCH §4.3.2 裁决函数不一致 | 如需固化，补 `status IN ('succeeded','degraded','degraded_review') ⇒ report_md IS NOT NULL`；否则在文中注明由应用保证 |
| P2-3 | §6 `diagnoses` 指纹 CHECK | `input_type='csv_batch'` + `execution_mode='single'` + 无指纹可通过（实测），入口与执行模式不一致未受约束 | 补 `CHECK (input_type <> 'csv_batch' OR execution_mode = 'batch')` 等一致性约束 |
| P2-4 | §4.1/§5.3 vs §6 | `upload_id` 的 GLOB 允许后缀含下划线，ARCH §7.7 为 `^up_[0-9A-Za-z]{10,40}$`；§4.1 却写“DDL 强制”，两者不符 | 改为 `substr` 校验或 `upload_id NOT GLOB '*[^0-9A-Za-z]*'` 的分段校验 |
| P2-5 | §5.9/§2 | `batch_rows` 无 `input_fingerprint` 列；批量指纹只能经 1:1 诊断追溯，失败行无指纹，未登记该物理承载位置 | 在 §2/§9 显式登记“批量指纹落在 1:1 诊断（trace）”及“失败行不产生指纹”；或给 `batch_rows` 补 trace 列 |
| P2-6 | §5.8/§6/§7.5 | `batch_tasks` 创建必须显式写 `pending_rows=total_rows`，仅写 `total_rows` 会被守恒 CHECK 拒绝（实测）；§5.8/§4.8.1 未给创建示例，§10 清单未覆盖 | 在 §5.8/§7 增加创建示例并注明默认值不满足守恒 |
| P2-7 | §7.8 | “随后同步 `batch_rows` 并计数重算”与同节“该 UPDATE 与行状态/计数在同一事务内”措辞冲突 | 统一为“同一事务内完成诊断置 failed、行置 failed、计数重算” |
| P2-8 | §5.6 | 写“DELETE 仅随诊断级联删除”，但无 DELETE 触发器，直接 DELETE `diagnosis_steps` 可执行 | 删除该声明，或补 BEFORE DELETE 触发器（仅允许级联场景需另行设计） |
| P2-9 | §9 | `diagnoses.interrupt_type` 不在 PRD §4.5.2 字段表，D-06 只登记了 `interrupt_payload_json` | 将 `interrupt_type` 一并并入 D-06 登记，避免遗漏 |

**P3（仅边界提示）**：§7.1/§7.2/§7.7 的 SQL 注释出现 `409 IDEMPOTENCY_CONFLICT`、`VERSION_CONFLICT`、`CHAT_SESSION_ALREADY_ACTIVE` 等 API 错误码。未写路径/报文/SSE 字段，未构成越权；建议改为“按 ARCH §5.2 错误码映射”，保持“本文不复述 API 明细”的边界。

---

## 四、已核查通过（不展开）

除上述残留项外，ARCH §7.2 的 16 张逻辑表均有物理表且字段逐项覆盖；`diagnoses` 八项架构补充字段、事件 `seq` 唯一、`(user_id, active_fingerprint_key)` 部分唯一索引及终态清空 CHECK、`batch_tasks` 守恒 CHECK、行状态封闭集、`chat_sessions` 1:1、`knowledge_versions` 单 active、TTL 部分索引（`EXPLAIN` 命中）、`eval_samples` 4 值、`progress` 不持久化、`device_id` 全入口 NOT NULL + 1–64 均落地；§6 DDL 在 SQLite 3.50.4 一次性执行成功；§7.1/§7.3/§7.5/§7.7/§7.9/§7.10 示例可执行（§7.2 除外，见 P0-1）；未发现 API 路径/报文/SSE 字段明细越权、未新增业务枚举、未改变状态机。

---

## 五、返修后复验口径

1. P0-1、P0-2 必须修复；P0-2 若选择登记偏差，须先登记 ARCH §10.4 再改 §9/§5.11/§8.4。
2. P1-1~P1-5 逐条闭环，并在 §10 自查清单中增加对应实测项（终态清中断字段、懒判定事件、`chat_messages` 不可变、`manifest_path` 唯一、进度口径）。
3. 复验仍采用冷启动：只读四份正文 + 本日志 + 修订稿，重新抽取 DDL 执行，不复用本轮结论。

**留痕**：本日志为 DB V1.0.0 首次冷启动验收记录；后续修订稿复验追加新章节，不覆盖本记录。

---

# 第二轮：DB V1.1.0 冷启动复审

| 项目 | 内容 |
| --- | --- |
| 复审对象 | `docs/DB-数据库设计文档.md` V1.1.0 |
| 上游基线 | PRD V3.0.0（冻结）、ARCH V1.2.0（冻结）、UIUX V1.2.0（冻结）、HANDOFF V1.2.2 |
| 复审依据 | 四份正文 + 本日志第一轮记录 + 修订稿 |
| 复审方式 | 冷启动；重新抽取 §6 全量 DDL，在 **SQLite 3.50.4（Python 3.13.12 sqlite3）** 执行；逐条执行 §7.1~§7.14 关键 SQL，并构造拒绝路径实测；不复用第一轮结论 |
| 上游未改核查 | 文件大小/修改时间与第一轮一致：ARCH 219900 / 20:33:45、PRD 141990 / 16:20:32、UIUX 127087 / 21:17:27、HANDOFF 25322 / 21:54:19；DB 90049 / 22:49:03。未发现上游被改动 |
| **本轮判定** | **【通过，准予冻结 DB V1.1.0】**（第一轮 P0×2、P1×5、P2×9 全部闭环；新增 1 条非阻塞 P2 建议） |

## 一、第一轮驳回项闭环复核

| 项 | 状态 | 取证 |
| --- | --- | --- |
| P0-1 终态清中断三字段 | **通过** | §7.2 的 SET 已增加 `interrupt_type=NULL, interrupt_payload_json=NULL, interrupt_expires_at=NULL`；§7 新增 §7.12 `waiting_human → running`（清三字段、`version+1`、校验 `interrupt_expires_at > now`）。实测：修正后的 §7.2 对 `waiting_human` 行执行成功；删除三字段清空的同语句被中断一致性 CHECK 拒绝；§7.12 执行成功 |
| P0-2 会话删除保持 ARCH §5.4.6 | **通过** | DDL 改为 `chat_sessions.diagnosis_id … ON DELETE SET NULL`；CHECK 改为 `draft⇒NULL`、`active⇒NOT NULL`、`terminal⇒可空可非空`；`trg_chat_sessions_no_rebind` 仅在 `OLD.diagnosis_id IS NOT NULL AND NEW.diagnosis_id IS NOT NULL AND NEW <> OLD` 时拒绝，允许置空；§5.11/§8.4/§7.13 均明确“步骤/事件级联删除、会话与消息保留、`diagnosis_id` 置空、会话仍 `terminal`”。实测删除非批量终态诊断后：会话 `('terminal', None)`、消息保留 1 条、`diagnosis_steps`/`diagnosis_events` 为 0；未登记为“改写 ARCH” |
| P1-1 懒判定写 `expired` 事件 | **通过** | §7.1 第 1 步改为 `UPDATE … RETURNING diagnosis_id, diagnosis_revision`，第 1.1 步写 `diagnosis_events(type='expired')`；§7.3 明确两条路径共用 `expire` 事务。实测懒判定路径写入 1 条 `expired` 事件，且 `expired` 保留中断三字段 |
| P1-2 `chat_messages` 不可变 | **通过** | §6 新增 `trg_chat_messages_no_update`；实测 `UPDATE chat_messages` 被 `CHAT_MESSAGES_APPEND_ONLY` 拒绝 |
| P1-3 `input_fingerprint` 必填性登记 | **通过** | §9 D-08 已登记 PRD §4.5.2“单条必填”与 ARCH §4.1.2“部分 nl/chat 可空”的差异及取值；§5.5 同步引用 D-08 |
| P1-4 进度口径拆分 | **通过** | §7.5 已拆为 `terminal_rows = total - pending - running`（含 `cancelled`）与 `progress_made = succeeded+degraded+degraded_review+failed+failed_timeout`（不含 `cancelled`），`progress = progress_made / total_rows`。实测 1 成功 + 1 失败 + 1 取消：`terminal_rows=3`、`progress_made=2` |
| P1-5 `manifest_path` 唯一 | **通过** | §6 新增 `CREATE UNIQUE INDEX ux_knowledge_manifest ON knowledge_versions(manifest_path)`；实测同一路径登记第二版本被 `UNIQUE constraint failed` 拒绝 |
| P2-1 置信度空值联动 | **通过** | §6 新增 `CHECK ((confidence IS NULL) = (confidence_level IS NULL))`；实测“confidence 空 + level 非空”被拒绝 |
| P2-2 报告态必须有报告 | **通过** | §6 新增 `CHECK (status NOT IN ('succeeded','degraded','degraded_review') OR report_md IS NOT NULL)`；实测 `succeeded` 无报告被拒绝；`aborted` 无报告可执行 |
| P2-3 输入模式一致性 | **通过** | §6 新增 `csv_batch ⇒ batch`、`csv_single/form ⇒ single/eval`、`nl/chat ⇒ single` 三条 CHECK；实测 `csv_batch + single`、`nl + batch` 均被拒绝 |
| P2-4 `upload_id` 严格 GLOB | **通过** | §6 改为 `substr(upload_id, 4) NOT GLOB '*[^0-9A-Za-z]*'`；实测前缀后含下划线的 ID 被拒绝 |
| P2-5 批量指纹承载登记 | **通过** | §2、§5.9、§9 D-10 已登记“指纹落在 1:1 `diagnoses`（`trace`），失败行无指纹” |
| P2-6 批量创建初值 | **通过** | §5.8 增加创建不变量，§7.14 给出 `pending_rows=total_rows` 创建示例；实测仅写 `total_rows` 被守恒 CHECK 拒绝，按 §7.14 创建成功 |
| P2-7 对账事务措辞 | **通过** | §7.8 统一为“同一事务内完成诊断 `failed`、行 `failed`、计数重算与任务裁决”，删除“随后同步” |
| P2-8 `diagnosis_steps` 删除声明 | **通过** | §5.6 已改为“仓储层不提供单条删除入口”，不再声称 DB 触发器强制 |
| P2-9 `interrupt_type` 登记 | **通过** | §9 D-06 已同时覆盖 `interrupt_type` 与 `interrupt_payload_json` |

## 二、DDL 与关键 SQL 实测记录

| 编号 | 场景 | 结果 |
| --- | --- | --- |
| T-A | §6 全量 DDL 一次性执行（含部分索引、触发器、`RETURNING`） | 成功 |
| T-B | §7.2 终态 UPDATE（`waiting_human → succeeded`，清 active + 中断三字段） | 成功 |
| T-C | §7.2 同语句漏清中断三字段 | `CHECK constraint failed` 拒绝（符合预期） |
| T-D | §7.12 `waiting_human → running`（清三字段、`version+1`） | 成功；漏清三字段同样被 CHECK 拒绝 |
| T-E | §7.1/§7.3 `expire`：置 `expired`、清 active 键、写 `diagnosis_events(type='expired')` | 成功；事件 1 条；中断三字段保留 |
| T-F | §7.13 删除非批量终态诊断 | 会话保留为 `terminal` 且 `diagnosis_id=NULL`；`chat_messages` 保留；`diagnosis_steps`/`diagnosis_events` 级联删除 |
| T-G | §7.1 RT-17 防重插入（并发同指纹） | 活记录数 = 1；终态清键后同指纹可再次创建（活记录仍 = 1） |
| T-H | §7.14 批量任务创建（`pending_rows=total_rows` + pending 行） | 成功；仅写 `total_rows` 被守恒 CHECK 拒绝 |
| T-I | §7.5 批量计数重算（1 成功、1 失败、1 取消） | 守恒；`terminal_rows=3`、`progress_made=2` |
| T-J | 批量来源诊断 DELETE | `BATCH_DIAGNOSIS_DELETE_FORBIDDEN` 拒绝 |
| T-K | `chat_messages` UPDATE / `manifest_path` 重复 / 置信度一空一非空 / `succeeded` 无报告 / `upload_id` 含下划线 | 均被 CHECK/触发器/唯一索引拒绝 |
| T-L | TTL 查询计划 | 命中部分索引 `ix_diagnoses_ttl` |

## 三、新增非阻塞残留（P2，不阻塞冻结）

**P2-N1 §5.11/§6 `trg_chat_sessions_no_rebind` 允许 `terminal + diagnosis_id IS NULL` 的会话再次绑定新诊断**

- 实测：删除非批量诊断后会话为 `('terminal', None)`；随后执行 `UPDATE chat_sessions SET diagnosis_id=:new_id` 成功，可指向另一诊断。
- 影响：`/confirm` 的绑定语句要求 `status='draft'`（§7.7），API 路径不可达，故不影响本轮冻结；但 DB 层未封闭“会话生命周期内至多绑定一个诊断”的边界，属 P0-2 修复引入的窄边界。
- 建议：在 `trg_chat_sessions_no_rebind` 的 WHEN 增加 `OR (OLD.status='terminal' AND OLD.diagnosis_id IS NULL AND NEW.diagnosis_id IS NOT NULL)` 直接拒绝；或在 §5.11 明确“terminal 会话不可再绑定”并接受该边界。二者择一，下一轮修订处理即可。

## 四、结论

- 第一轮 P0×2、P1×5、P2×9 均以物理约束、触发器或登记方式真实闭环，非文字敷衍；§6 DDL 在 SQLite 3.50.4 可一次性执行，§7.1~§7.14 关键 SQL 可执行，拒绝路径均被约束拦截。
- 未发现新增业务枚举、状态机变更、API 路径/报文/SSE 字段明细越权；上游三份文档（ARCH/UIUX/HANDOFF）与 PRD 均未被修改。
- 本轮判定：**【通过，准予冻结 DB V1.1.0】**；P2-N1 作为实现阶段加固项，不阻塞冻结。

**留痕**：本节为 DB V1.1.0 第二轮冷启动复审记录，追加于第一轮记录之后，不覆盖原记录。
