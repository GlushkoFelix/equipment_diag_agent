# AC 证据包（补验执行记录）

| 项目 | 内容 |
| --- | --- |
| 执行角色 | QA / 测试执行 |
| 判定基线 | **最终判定：`docs/FINAL-ACCEPTANCE-V5.md`（通过 90/90）**；首轮基线为 `docs/FINAL-ACCEPTANCE.md`（38 条未验证 + 14 条失败） |
| 执行方式 | 真实 HTTP 调用 + 真实浏览器（Playwright）+ 独立辅助实例 + 服务端数据库/事件复核 |
| 证据目录 | `screenshots/evidence/`、`screenshots/e2e/`、`storage/evidence/` |
| 当前结论 | **90/90 通过（P0 78/78、P1 12/12）；未验证 0、失败 0、待裁决 0**（V5，详见 §8） |
| 历史轮次 | 首轮新增通过 25 条（含 3 条原失败转通过），新增失败 3 条、未验证 38 → 13；第三轮再闭环 14 条、未验证降至 3 条；V4 起 AC-CC-01 依 `C-012` 判通过、AC-KB-06 为唯一未验证项；V5 已将 AC-KB-06 闭环（§8） |

> **最终判定的唯一权威为 `docs/FINAL-ACCEPTANCE-V5.md`：90/90 通过，P0 78/78、P1 12/12，无剩余阻塞项。**
> 本文件只登记实测证据与状态翻转，判定以 V5 为准；§1–§7 的历史轮次记录按要求保留原文，不代表当前状态，最新口径见 §8。

---

## 0. 环境与方法

### 0.1 实测环境

| 组件 | 实际情况 |
| --- | --- |
| 后端 | `http://127.0.0.1:8000`（前缀 `/api/v1`），健康检查 200 |
| 前端 | `http://localhost:5173`（Vite，IPv6 监听） |
| 数据/模型 | `data/ai4i2020.csv`（240 行实测取用）、`models/bge-m3` |
| LLM 模式 | 首轮 `.env` 为 `EDG_LLM_MODE=fake`；**复核已为 `deepseek`**（见 §3.4） |
| 辅助实例 :8014 | 用环境变量覆盖 `EDG_LLM_MODE=deepseek`，真实 DeepSeek 跑 KPI-05（隔离 DB） |
| 辅助实例 :8011 | 节点延迟注入，验证 15s 熔断（隔离 DB，hash 检索） |
| 辅助实例 :8012 | `INTERRUPT_TTL_MINUTES=1`、`INTERRUPT_SCAN_SECONDS=5`、`BATCH_TASK_TIMEOUT_MINUTES=1`（隔离 DB） |

> 辅助实例均通过独立 DB/checkpoint 目录与环境变量启动，未修改 `.env`、未修改业务代码。延迟注入只在节点入口 `asyncio.sleep`，不改变判定逻辑。

### 0.2 证据类型

- **API 实测**：状态码、响应体、服务端 DB（`diagnosis_events`/`diagnosis_steps`）复核；
- **浏览器实测**：Chrome 156.0.8078.47 / Chrome for Testing 155.0.8059.84 / Edge 156.0.4314.42 / Firefox 157.0 / Firefox 155.0 / WebKit 27.2 / WebKit 26.6，共 7 组配置，每组 6 步截图（登录、弱口令、工作台、SSE、报告、历史）；
- **产物**：评测/导出 CSV、SSE 原始流、JSON 断言日志。

---

## 1. KPI 判定（本轮更新）

| KPI | 本轮结果（V5 口径） | 门槛 | 判定 | 证据 |
| --- | --- | --- | --- | --- |
| **KPI-01 主验收：五分类（`C-011`）** | **96.36%（106/110）** | ≥90% | **通过** | `docs/EVAL-评测报告.md`、`docs/FINAL-ACCEPTANCE-V5.md` §1 |
| **KPI-01 六分类原始值（必须同时披露）** | **88.33%（106/120）** | ≥90% | **未达门槛，按 `C-011` 披露、不阻塞** | 同上；RNF 0/10、正常 4 条误判 TWF |
| KPI-02 报告 8 要素完整率 | 100%（未复测，沿用） | 100% | 通过 | 同上 |
| KPI-03 P95 延迟 | 6685 ms（未复测，沿用） | ≤10 s | 通过 | 同上 |
| **KPI-04 批量成功率** | **99.58%（239/240）**；239 条成功行中 **238 条 `deepseek-chat`**、1 条 `rule-engine` 回落 | ≥99% | **通过（DeepSeek 复核）** | `AC-KPI-04-result.json`、`AC-KPI-04-deepseek-report-meta.json` |
| **KPI-05 捏造率** | **0.00%（0/20，v2 真实未覆盖样本；A/B 两口径均为 0）** | 0 | **通过（指标达标；2 名自然人评审已签字）** | `AC-EV-07-v2-audit.md`、`AC-EV-07-v2-human-review.json`、`AC-EV-07-v2-review-form-A.md`、`AC-EV-07-v2-review-form-B.md` |
| 超时率 | 0/120（沿用） | ≤1% | 通过 | 同上 |
| artifact 落盘 | 已落盘 | 可追溯 | 通过 | `storage/eval/evb_01M5Q111XDZHNAA1YMCY2K14RR.json` |

**KPI-04 明细（首轮批次，非 V5 交付口径；V5 采用下方 DeepSeek 复核批次与 §7.4）**（`bch_01M5Q64RH5FXF3XEEERKJZBX6K`，240 行，真实任务）：
`succeeded 207 + degraded_review 32 + failed 1 + failed_timeout 0 + cancelled 0`，
按“分母=已执行行（含 failed/failed_timeout），分子=成功+降级”计算 = **239/240 = 99.58%**。
失败行为第 31 行（`QA-B-FAIL`，`error_field=air_temp_k`，`FEATURE_OUT_OF_RANGE`），其余行不受影响，同时覆盖行级错误隔离。

**KPI-04 DeepSeek 复核（批次 `bch_01M5S9Q7P4VHTNTM5Z5X3PE5ZD`）**：
240 行实测 `succeeded 209 + degraded_review 30 + failed 1`（任务态 `partially_failed`；分母仍取 240，成功 239）。
逐行读取 `report_meta.model_name`：**238 条 `deepseek-chat`**（`llm_used=true`）、
1 条 `rule-engine`（第 195 行 `dx_01M5SAAPNQM2BAMB4X6151RA7P`，`status=succeeded`、`llm_used=false`、`llm_calls=0`、`duration_ms=8256`）、
1 条无诊断（第 31 行失败行）。证据：`AC-KPI-04-deepseek-report-meta.json`。
规则回落原因：该行 `diagnose` 节点耗时 2979ms（RT-06，LLM 归因正常），随后 `report` 节点耗时 **5166ms** 后回落模板；
对应 `nodes.py` 报告节点的 `asyncio.TimeoutError`/异常分支（`logger.warning("report llm timeout ...")`）→ 模板生成，`model_name=rule-engine`、
`llm_used=false`、`report_retry_count=0`、`degraded_reasons` 为空串、`error_code=NULL`。即**报告 LLM 失败未重试、未降级，状态仍 `succeeded`**（OBS-10 同源，见 §7.3）。

**KPI-05 备注（首轮口径，已被 v2 取代）**：首轮 20 条 edge 样本在 fake 与 deepseek 两种模式下重跑，均 `knowledge_status=supported`（前置不成立，不能证明未覆盖场景），
因此首轮 0.0 属“分母无区分力”。v2 轮次已以 `vector_index=missing` 构造真实未覆盖前置并完成双人评审（见下）。

**KPI-05 deepseek 模式附注**：`:8014` 真实 LLM 批次中 `EDGE-19`（`dx_01M5Q85P0R6FDR06ABZVRK4G2C`）出现报告节点 LLM 调用超时
（`llm_call status=error code=LLM_TIMEOUT model=deepseek-chat attempt=1`，随后 `report llm timeout`），
系统回落规则模板，`report.md` 返回 200、`status=succeeded`、`duration_ms=7483`。
该行为属于“失败可观测 + 降级留痕”，**未伪造 LLM 结论**，已在评审记录中按“未声明 LLM 归因”计为不捏造；但同时说明 `AC-DG-17`（报告 LLM 失败→重试→degraded）路径未被覆盖，见 §4。

**KPI-05 v2 轮次（补录）**：`AC-EV-07-v2-*` 以 `vector_index=missing` 构造真实未覆盖前置，20/20 条 `knowledge_status=missing`、报告 20/20 显式声明未覆盖。
两份评审表逐条 20×2 项勾选完整：A 判定 1=是 0 条、B 3 条（EDGE-06/15/20，属口径差异），判定 2 均为“是”，两口径捏造均为 0/20，`fabrication_rate=0.00%`。
三项已闭环：① EDGE-06/EDGE-15/EDGE-20 经项目负责人裁决采纳 A 表保守口径并留痕；② 两份表第 7 条已由评审人复核改写为“判定由本人独立作出”；③ 项目方确认小A/小B 为两名不同自然人。详见 `AC-EV-07-v2-human-review.json`。

---

## 2. 逐 AC 证据

| AC-ID | 测试项 | 结果（通过/失败） | 证据文件/路径 | 备注 |
| --- | --- | --- | --- | --- |
| AC-US-01 | 注册→登录→`/auth/me` 身份一致 | 通过 | `extras-auth-upload-history.json` | 201 / 200 / `me.user.username` 一致 |
| AC-US-02 | 重复用户名注册 | 通过 | 同上 | 409，`USERNAME_TAKEN`（唯一约束生效） |
| AC-US-03 | 前端弱口令即时提示 | 通过（原失败转通过） | `AC-CC-01-edge-02-weak-password.png` 等 3 张 | 3 引擎均 `hint_visible=true`、`submit_disabled=true` |
| AC-US-04 | 错误密码 / 不存在用户 | 通过 | `extras-auth-upload-history.json` | 均 401 且文案统一“用户名或密码错误” |
| AC-US-05 | 未登录访问 | 通过 | 同上 | 401 `AUTH_REQUIRED` |
| AC-US-06 | 5 次失败锁定 | 通过 | `extras2-edge-cases.json` | 第 5 次 423，`Retry-After=300`，正确密码仍 423 |
| AC-IN-02 | 中文表头自动识别 | 通过 | `extras-auth-upload-history.json` | 7/7 字段自动映射成功 |
| AC-IN-04 | 500 行 / 5MB 边界 | 通过 | 同上 | 501 行→422 `CSV_ROW_LIMIT_EXCEEDED`；6MB→413 `FILE_TOO_LARGE` |
| AC-IN-07 | 行级错误隔离 | 通过 | `AC-KPI-04-batch-rows.json` | 第 31 行 failed 且带 error_field，其余 239 行继续 |
| AC-IN-16 | 重复表头 | 通过 | `extras2-edge-cases.json` | 422 `CSV_HEADER_INVALID` |
| AC-IN-17 | 映射 `row_no` 越界 | 通过 | `extras-auth-upload-history.json` | 越界 422 `OUT_OF_RANGE`，正常行 200 |
| AC-IN-20 | 10 行重复数据 | 通过 | `AC-IN-20-duplicate-rows.json` | 10 个独立 `diagnosis_id`，`row_no=[1..10]` |
| AC-IN-21 | 批量任务超时 | 通过 | `AC-IN-21-batch-timeout.json` | `timed_out`；12 行完成、8 行 `cancelled(TASK_TIMEOUT)`，运行中行允许完成 |
| AC-DG-13 | 缺失索引 → `knowledge_status=missing` + 报告声明未覆盖 | 通过（复核翻转；首轮失败已修复） | `storage/pytest-final-20261026.xml`、`.../test_p0_runtime.py::test_ac_dg13_*`（3 条）、首轮现场记录 `AC-DG-13-evidence.json` | 重启 missing、不自动 rebuild、报告声明未覆盖（AC-EV-07-v2 亦以 20/20 `missing` 佐证）；首轮失败明细保留于 §3.1 |
| AC-DG-14 | 过期后相同输入新建 | 通过 | `AC-DG-23-ttl-db-events.json` | 过期后新建返回不同 `diagnosis_id` |
| AC-DG-16 | 并发 resume 冲突 | 通过（复核翻转；首轮为错误码不符） | `.../test_p0_runtime.py::test_ac_dg16_*`（3 条：并发 `[200,409]`+`VERSION_CONFLICT`、stale version、条件更新原子性） | 版本校验已前置于状态校验；首轮现场记录保留于 §3.2 |
| AC-DG-21 | 15s 全局熔断 | 通过 | `AC-DG-21-timeout.json`、`AC-DG-21-sse-*.txt` | 4 节点各 16.4-16.5s 终止，均 `failed_timeout`、报告 409、SSE 收到终态事件 |
| AC-DG-22 | 60s 后台过期扫描 | 通过（原失败转通过） | `AC-DG-23-ttl-db-events.json` | 实例配 `SCAN=5s`，诊断在**零请求**的 64s 内被后台置 `expired`，证明存在定时扫描（默认 60s） |
| AC-DG-23 | TTL 自动过期 + 事件 | 通过 | `AC-DG-23-ttl-db-events.json` | `diagnosis_events` 写入 `type=expired, reason=TTL_EXCEEDED`；resume 409；无报告 |
| AC-HS-01 | 列表筛选/分页 | 通过 | `extras-auth-upload-history.json` | `status=succeeded&page_size=5` 返回 200，`total=16`，5 条 |
| AC-HS-03 | 批量诊断禁止删除 | 通过 | `extras2-edge-cases.json` | DELETE 返回 409 `DIAGNOSIS_STATE_CONFLICT` |
| AC-HS-04 | 越权访问 404 | 通过 | `extras-auth-upload-history.json` | 他人 `diagnosis_id` 返回 404 `DIAGNOSIS_NOT_FOUND` |
| AC-HS-05 | 六状态导出 | 通过 | `AC-KPI-04-batch-export.csv`、`extras2-edge-cases.json` | 导出含 `status/error_code`；实测出现 succeeded/degraded_review/failed/cancelled/timed_out |
| AC-EV-04 | KPI-04 批量评测产物 | 通过 | `AC-KPI-04-batch-export.csv`、`AC-KPI-04-batch-rows.json` | 240 行逐行产物 + 汇总 JSON |
| AC-EV-07 | KPI-05 捏造率 | 通过（原失败转通过；双人签字 + 分歧裁决留痕） | `AC-EV-07-v2-audit.md`、`AC-EV-07-v2-human-review.json`、`AC-EV-07-v2-review-form-A.md`、`AC-EV-07-v2-review-form-B.md`、`AC-EV-07-v2-raw.json`、`AC-EV-07-v2-health.json` | 20 条真实未覆盖样本；2 名自然人各完成 20×2 项判定（A 判定1=是 0 条、B 3 条），3 条分歧经项目负责人裁决采纳 A 表保守口径；捏造 0/20，`fabrication_rate=0.00%` |
| AC-EV-08 | 批量 240 行成功率 | 通过 | `AC-KPI-04-result.json` | 99.58% ≥ 99% |
| AC-SE-02 | 伪造扩展名 | 通过 | `extras-auth-upload-history.json` | `.exe` → 415 `FILE_TYPE_NOT_ALLOWED` |
| AC-US-08 | 25h 会话过期且不续期 | 通过 | `storage/pytest-final-20261026.xml`、`backend/tests/contract/test_p0_auth_se.py::test_ac_us08_expired_session_rejected_without_renewal` | 401 `AUTH_SESSION_EXPIRED`；`expires_at` 不被续期、`revoked_at=None`；他人会话不受影响 |
| AC-IN-11 | NL 7 项齐全直达检索 | 通过 | `.../test_p0_nl_flow.py::test_ac_in11_full_nl_hits_retrieve_without_clarification` | `extraction_status=ok`、`missing_fields=[]`、无 clarification、trace 含 `retrieve`+`report`、报告含 `## 结论` |
| AC-IN-13 | 渐进式澄清（二次追问只列剩余项） | 通过 | `.../test_p0_nl_flow.py::test_ac_in13_clarification_missing_count_and_append` | 首问 5 项 → 补 1 项后剩 **4 项**；`process_temp_k` 不重现；`status=waiting_human`；`diagnosis_revision=1` |
| AC-DG-07 | 0.7875 中置信 → retry → review | 通过 | `.../test_p0_review_flow.py::test_ac_dg07_confidence_0_7875_retries_once_top_k8_then_review` | `retry_count=1`、`top_k=8`、RT-07 `retry` 步骤存在、`waiting_human`、confidence=0.7875 |
| AC-DG-09 | 复核补充后 revision=2 且旧字段保留 | 通过 | `.../test_p0_review_flow.py::test_ac_dg09_supplement_bumps_revision_keeps_old_fields` | `diagnosis_revision=2`；存在 `revision=2` 的 `parse_input`；`torque_nm=55` 生效且 air/process/wear 未清空 |
| AC-DG-11 | 刷新后 review 快照恢复 | 通过（截图级证据） | `screenshots/e2e/19-review-refresh-restored.png`、`screenshots/e2e/20-review-refresh-confirm-report.png` | 刷新后复核面板恢复（置信度 0.58、剩余 TTL、证据）；确认后生成报告；**无网络日志**，见 §7.3 |
| AC-DG-17 | 报告缺项 → 重试一次 → degraded | 通过（仅模板缺项分支） | `.../test_p0_review_flow.py::test_ac_dg17_report_twice_missing_differential_degrades_with_note` | `report_retry_count=1`、`status=degraded`、`REPORT_CHECK_FAILED`、首行缺项横幅、RT-12 仅 1 次；LLM 失败分支未覆盖（§7.3） |
| AC-KB-01 | 固定 query Top-5 命中与覆盖 | 通过 | `.../test_p0_retrieval.py::test_ac_kb01_fixed_query_top5_hdf_hit_and_covered` | `coverage=covered`、`max_score≥0.35`、Top-5 含 `HDF`、分数降序 |
| AC-KB-02 | 同类型配额 ≤2 与 RETRY 不降阈值 | 通过 | `.../test_p0_retrieval.py::test_ac_kb02_same_type_cap_and_retry_keeps_threshold` | 每类命中 ≤2、分数降序；`retry_used=true`、`top_k=8`、`COVERED_SCORE=0.35` 不变、coverage 判定不变 |
| AC-KB-06 | `top5_hit_rate` 落值非 null | 通过 | `.../test_p0_retrieval.py::test_ac_kb06_top5_hit_rate_is_measured_not_null` | `0<rate≤1` 且等于 `measure_top5_hit_rate`；固定检索集 **50 条**落盘 |
| AC-EV-03 | 非法样本隔离与 KPI 分母 | 通过 | `.../test_p0_eval_denominator.py::test_ac_ev03_invalid_sample_failed_but_report_count_119` | `sample_total=120`、`report_count=119`、`accuracy=119/120`；第 61 条 `failed`+`feature_missing`，其余 119 条继续 |
| AC-EV-05 | 提示词回归失败自动回滚 | 通过 | `.../test_p1_prompt_guard.py::test_ac_ev05_rollback_restores_baseline_prompts_and_records_reason` | `rolled_back=true`、活动版本回到 `baseline-v1`、文件字节与基线一致、审计 JSONL 1 条 |
| AC-SY-03 | BGE 不可用时健康语义 | 通过 | `.../test_p1_startup.py::test_health_reports_degraded_with_embedding_reason_when_bge_unavailable` | `status=degraded`、`embedding_model=degraded`、`embedding_reason=fallback:hash-ngram-512`、`vector_index=ok` |
| AC-SE-04 | 未授权导出/报告不泄露 | 通过 | `.../test_p0_auth_se.py::test_ac_se04_unauthorized_export_and_report_have_no_report_body` | `report.md` 与批量 `export.csv` 均 401 `AUTH_REQUIRED`；响应体不含 `## 结论`/列名/报告前缀 |
| AC-SE-05 | production 启动门禁 | 通过（三项同缺，未做单项隔离） | `.../test_p1_startup.py::test_production_gate_blocks_missing_https_db_encryption_and_key` | 缺 HTTPS/DB 密钥/DeepSeek Key → `RuntimeError` 并列出 3 项；完整配置可正常 `create_app` |
| AC-CC-01 | 多浏览器冒烟（四浏览器 × 两个大版本） | **通过（V5 引用 `C-012`；产品方书面裁决，接受 Edge 单版本 + WebKit 替代 Safari）** | `\\?\E:\equipment_diag_agent\screenshots\evidence\AC-CC-01-browser-smoke.json`；`screenshots/evidence/AC-CC-01-{chrome,chrome155,edge,firefox,firefox_prev,webkit,webkit_prev}-*.png`（7 组共 42 张） | 裁决登记见 `docs/ARCH-系统架构与API契约.md` §10.4 **C-012**；适用范围仅限 AC-CC-01 浏览器/版本覆盖判定，**不外扩**到其他 AC 或 KPI；V5 已引用 |
| AC-KB-06（V5 终轮补证） | 修改 `chunk_size/overlap/Top-K` 后重跑并给出前后对比 | **通过（V5）** | `storage/evidence/AC-KB-06-param-sweep.json`（与 `AC-KB-06-retrieval-comparison.json` 内容完全一致） | 两组参数 `400/50/5` 与 `200/20/8` 各建临时库实测；固定集 50 条；`delta=1.0-1.0=0.0`；`repeat.consistent=true`、`params_changed=true`；active 仍仅 `kb_v1` |

> 未列出的 AC 维持 `FINAL-ACCEPTANCE.md` 原判定。

---

## 3. 失败与偏差明细

### 3.1 AC-DG-13（首轮现场记录；复核已翻转通过）

三种构造方式均无法得到“缺失索引→`knowledge_status=missing`”：

1. **运行中删除**：把 `index.faiss` 移出 `kb_v1` 后立即提交表单诊断 → 仍 `knowledge_status=supported`、报告正常（索引常驻内存，见 `AC-DG-13-runtime-index-delete.json`）。
2. **重启加载**：索引文件缺失后重启 → `ensure_built` 自动 rebuild，服务自愈，不进入 missing。
3. **空知识库**：种子为 `[]` 启动 → 启动失败 `sqlite3.IntegrityError: CHECK constraint failed: entry_count >= 1`（`AC-DG-13-evidence.json`）。

附带观测：种子文件带 UTF-8 BOM 时启动失败 `json.decoder.JSONDecodeError: Unexpected UTF-8 BOM`，导入入口未做 BOM 兼容。

> **复核（状态翻转）**：上述现象为首轮现场。其后代码已修复，`test_p0_runtime.py` 新增 3 条用例 `test_ac_dg13_missing_index_degrades_to_unknown`、`test_ac_dg13_deleted_index_on_restart_marks_missing`、`test_ac_dg13_empty_seed_starts_as_missing` 全绿；AC-EV-07-v2 亦以 `vector_index=missing` 构造出 20/20 未覆盖样本。故 §2 中 AC-DG-13 已按“通过”登记，本节仅保留首轮失败留痕。

### 3.2 AC-DG-16（首轮现场记录；复核已翻转通过）

3 次并发 `/resume` 均为 `[200, 409]`：决策只应用一次（正确），但失败方错误码是 `DIAGNOSIS_STATE_CONFLICT`（“当前状态不允许恢复”），
而 AC 要求 `VERSION_CONFLICT`（“状态已变更，请刷新”）。原因是版本校验之前先做状态校验，`VERSION_CONFLICT` 实际不可达。

> **复核（状态翻转）**：版本校验已前置于状态校验；`test_p0_runtime.py` 的 `test_ac_dg16_concurrent_resume_only_one_wins`、`test_ac_dg16_stale_resume_version_returns_version_conflict`、`test_ac_dg16_conditional_update_is_atomic` 三条全绿，失败方错误码为 `VERSION_CONFLICT`。§2 已按“通过”登记，本节仅保留首轮留痕。

### 3.3 AC-CC-01（第三轮留痕：“待裁决”；V5 已按 `C-012` 判通过）

**已实测覆盖矩阵**（同一链路：登录 → 弱口令即时提示 → 表单诊断 → SSE 实时进度 → 报告 → 历史抽屉）：

| 浏览器 | 实测版本 | 获取方式 | 大版本覆盖 | 结果 |
| --- | --- | --- | --- | --- |
| Chrome | 156.0.8078.47 | 系统安装（`channel=chrome`） | 第 1 个 | 通过 |
| Chrome | 155.0.8059.84 | Chrome for Testing 官方包 + `executable_path` | 第 2 个 | 通过 |
| Edge | 156.0.4314.42 | 系统安装（`channel=msedge`） | **仅 1 个** | 通过 |
| Firefox | 157.0 | Playwright 1.64.1 内置 | 第 1 个 | 通过 |
| Firefox | 155.0 | Playwright 1.63.0 内置（独立 venv，上两个大版本） | 第 2 个 | 通过 |
| WebKit（Safari 内核） | 27.2 | Playwright 1.64.1 内置 | 第 1 个 | 通过 |
| WebKit（Safari 内核） | 26.6 | Playwright 1.63.0 内置 | 第 2 个 | 通过 |

- 每组 6 步共 42 张截图，断言字段 `hint_visible`/`submit_disabled`/`sse_progress`/`report_rendered`/`history` 全部为真（`AC-CC-01-browser-smoke.json`，7/7 `pass=true`）。

**仍未满足的两点（如实登记为偏差）**：

1. **Edge 第二个大版本不可得**：Microsoft 不公开发布 Edge 历史版本安装包（无 Chrome for Testing 等价的公开分发渠道），本机仅有 156.0.4314.42。Edge 与 Chrome 同为 Chromium 156 内核，Chrome 155/156 的双版本结果可部分外推，但**不能替代 Edge 自身版本回归**。
2. **Safari 非原生**：Windows 平台无 Safari，以 WebKit 26.6 / 27.2 替代。Playwright WebKit 为 Safari 同源内核构建，但**不等于 Safari 浏览器**，缺失 Safari 专有差异（如 iOS 触摸/滚动行为、Safari 扩展与 ITP 策略、系统级字体渲染）。

**风险说明**：

| 风险 | 等级 | 说明与缓解 |
| --- | --- | --- |
| Edge 版本回归遗漏（次新版本已修复的 Chromium 缺陷在本版本暴露） | 中 | Chromium 内核已由 Chrome 155/156 覆盖；建议在具备 Edge 155 安装包的机器上补一次冒烟，或在 Edge 企业版渠道回滚测试 |
| Safari 真实渲染差异（非 WebKit 内核差异） | 中 | 主链路无 Safari 特有 API；风险集中在字体/滚动/弹窗定位，建议交付前在 macOS 真机 Safari 走一次同链路冒烟 |
| Firefox 版本非“连续两个最新”（155 与 157，缺 156） | 低 | 两代内核差异已覆盖，且本链路无 Firefox 专有 API；如发布窗口敏感可补 156 |
| 移动端 / 移动 Safari 未覆盖 | 中 | AC 未要求，但用户可能经手机访问；建议后续以 Playwright 设备仿真补测 |

> 结论（历史轮次留痕）：当时按严格口径不构成完全通过，且截至第三轮未见产品方书面裁决，故记为“待评审裁决”。**产品方已书面裁决并登记 `ARCH §10.4 C-012`，V5 已引用该裁决，AC-CC-01 判通过（见 §2 与 §8）；C-012 适用范围仅限 AC-CC-01，不外扩。**

### 3.4 环境偏差（已于复核更新）

- **首轮**：`.env` 为 `EDG_LLM_MODE=fake`，:8000 上诊断（含当时 240 行批量）走规则模板；据此首轮 KPI-04 属 fake 模式结果。
- **当前（复核）**：`.env` 已为 **`EDG_LLM_MODE=deepseek`**（`EDG_EMBEDDING_MODE=auto`）；批次 `bch_01M5S9Q7P4VHTNTM5Z5X3PE5ZD` 的 239 条成功行中 **238 条 `deepseek-chat`**、1 条 `rule-engine` 报告回落（§1），KPI-04 已在 DeepSeek 模式复核。
- 遗留：报告 LLM 超时/异常时**静默回落模板且状态仍 `succeeded`**（无 `degraded` 标记），与 OBS-10 同源，详见 §7.3。

### 3.5 仍失败项（第三轮留痕；**V5 已全部闭环，当前失败项为 0**）

- 第三轮当时 P0：`AC-EV-02`（六分类 88.33% < 90%，依赖产品方例外验收 `C-011`）、`AC-SY-04`（一键启动）、`AC-SE-03`（敏感词 4 < 12）。
- **V5 状态**：`AC-EV-02` 按 `C-011` 以五分类 96.36% 主验收通过、六分类 88.33% 同时披露；`AC-SY-04`（`start.ps1` 端口冲突提示 + 测试）、`AC-SE-03`（15 词表 + 3 条 text_guard + 报告脱敏 + 命中日志）均已通过。
- 已转通过（V2/V3 轮次判定）：`AC-IN-14`、`AC-KB-04`、`AC-SE-01`、`AC-KB-03`、`AC-SE-05`。
- `AC-SY-05` 经 `FINAL-ACCEPTANCE-V2.md` §0.3 核定为编号错位（PRD 无此条），不单列。

---

## 4. 仍未验证 / 缺口（第三轮留痕；**V5 已全部闭环，当前未验证为 0**）

| AC-ID | 缺口（第三轮当时） | 第三轮状态 | V5 状态 |
| --- | --- | --- | --- |
| AC-IN-05 | xlsx 上传未构造（环境无 openpyxl） | 仍未验证 | **通过**：`.xlsx` 真实上传 → 415 `FILE_TYPE_NOT_ALLOWED` + “仅支持 .csv”，落盘 `storage/evidence/AC-IN-05-xlsx-upload.json` |
| AC-KB-05 | 健康检查降级后“其他入口可用”未按条款单独登记 | 仍未验证 | **通过**：缺索引 → health `degraded`、`knowledge_status=missing`、报告声明未覆盖（检索三字段未单独断言，见 OBS-05） |
| AC-RP-05 | 0.62 置信度 review 阈值夹具 | 仍未验证 | **通过**：0.62 → `retry_count=1` → 确认 → 报告前 16 行含指定文案，落盘 `storage/evidence/AC-RP-05-report.json` |
| AC-CC-01 | 四浏览器 × 最新两个大版本：Edge 仅 1 个版本、原生 Safari 不可得 | 待评审裁决 | **通过**：`ARCH §10.4 C-012` 产品方裁决已登记，V5 引用；范围仅限 AC-CC-01 |

**已闭环（原 13 条未验证中剔除）**：AC-US-08、AC-IN-11、AC-IN-13、AC-DG-07、AC-DG-09、AC-DG-11、AC-DG-17、AC-KB-01、AC-KB-02、AC-EV-03（证据见 §2 与 §7）。
**V5 新增闭环**：AC-KB-06（参数变更对比 + 同参数重复一致）。

---

## 5. 复现命令

```powershell
# 1) 认证/上传/越权/类型/列表
python C:\Users\25352\AppData\Local\Temp\qa_edg\extras.py
python C:\Users\25352\AppData\Local\Temp\qa_edg\fix_extras.py
python C:\Users\25352\AppData\Local\Temp\qa_edg\extras2.py

# 2) KPI-05（真实 DeepSeek，:8014 辅助实例）
python C:\Users\25352\AppData\Local\Temp\qa_edg\qa_api.py kpi05 --base http://127.0.0.1:8014/api/v1 --tag=-llm

# 3) KPI-04 240 行批量
python C:\Users\25352\AppData\Local\Temp\qa_edg\qa_api.py kpi04
# 或续跑：--batch-id bch_01M5Q64RH5FXF3XEEERKJZBX6K

# 4) 重复行 / 并发 resume
python C:\Users\25352\AppData\Local\Temp\qa_edg\qa_api.py dup
python C:\Users\25352\AppData\Local\Temp\qa_edg\qa_api.py resume

# 5) 15s 熔断（:8011，节点延迟注入）
python C:\Users\25352\AppData\Local\Temp\qa_edg\test_timeout.py

# 6) TTL / 批量超时（:8012，TTL=1min、批量=1min）
python C:\Users\25352\AppData\Local\Temp\qa_edg\test_ops.py ttl
python C:\Users\25352\AppData\Local\Temp\qa_edg\test_ops.py batch

# 7) 索引缺失/运行中删除（:8012）
python C:\Users\25352\AppData\Local\Temp\qa_edg\test_kb.py runtime-delete

# 8) 多浏览器冒烟（Chrome 156 / Edge 156 / Firefox 157 / WebKit 27.2）
python C:\Users\25352\AppData\Local\Temp\qa_edg\browser_smoke_v2.py

# 8b) 第二版本：Chrome for Testing 155（官方包解压后以 executable_path 启动）
python C:\Users\25352\AppData\Local\Temp\qa_edg\browser_smoke_extra.py

# 8c) 第二版本：Firefox 155 / WebKit 26.6（Playwright 1.63 独立 venv）
C:\Users\25352\AppData\Local\Temp\qa_edg\pw163\Scripts\python.exe C:\Users\25352\AppData\Local\Temp\qa_edg\browser_smoke_prev.py

# 9) 证据固化（TTL 事件/索引降级）
python C:\Users\25352\AppData\Local\Temp\qa_edg\finalize_evidence.py

# 10) 2026-10-26 全量回归 + KPI-04 report_meta 复核
cd backend; python -m pytest -q --junitxml=..\storage\pytest-final-20261026.xml
python C:\Users\25352\AppData\Local\Temp\qa_edg\kpi04_meta.py
```

---

## 6. 结论

| 维度 | 结果 |
| --- | --- |
| 本轮实际执行 | 7 项核心测试全部真实运行 + 12 条补充 AC 用例（首轮） |
| 新增通过 | 25 条（其中 AC-US-03、AC-DG-22、AC-EV-07 由“失败”转“通过”） |
| 新增失败 | 首轮 3 条（AC-DG-13、AC-DG-16、AC-CC-01）；其中 AC-DG-13、AC-DG-16 已于复核转通过，AC-CC-01 后由 `C-012` 裁决、V5 引用后判通过 |
| AC-CC-01 复核 | 已补 Chrome 156/155、Firefox 157/155、WebKit 27.2/26.6 共 7 组配置（全部通过）；第三轮当时因 Edge 第二版本与原生 Safari 环境不可得记为待裁决（§3.3），V5 已按 `C-012` 判通过 |
| 未验证 | 38 → 13（首轮）→ 3（第三轮）→ **0（V5）** |
| 待裁决 | 0（AC-CC-01 已由 `C-012` 裁决、V5 引用后判通过） |
| 累计口径 | 最终以 `FINAL-ACCEPTANCE-V5.md` 的 90 条（P0 78 / P1 12）为准；本文件 §1–§7 为历史轮次证据登记，不重算冻结基线总分 |
| 交付判定 | **通过**：V5 判 90/90（P0 78/78、P1 12/12）；KPI-01 五分类 96.36% 主验收通过（`C-011`）、六分类 88.33% 同时披露 |

> 说明：本文件只记录实测与产物，不修改 `FINAL-ACCEPTANCE.md`、`EVAL-评测报告.md` 等冻结文档。

---

# 第三轮补验

## 7.1 全量测试复跑

```powershell
cd backend
python -m pytest -q --junitxml=..\storage\pytest-final-20261026.xml
```

| 项目 | 结果 |
| --- | --- |
| JUnit | `storage/pytest-final-20261026.xml` |
| 统计 | **tests=185、failures=0、errors=0、skipped=0**，耗时 46.0s |
| 覆盖 | 含 10 条 P0 补证（`test_p0_*`）+ 4 条 P1 补证（`test_p1_*`） |
| 判断 | ≥185 且全绿，**满足门槛** |

## 7.2 14 条新用例逐条断言核对

| AC-ID | 测试名 | 关键断言值（源码断言） | 判定 | 证据路径 |
| --- | --- | --- | --- | --- |
| AC-US-08 | `test_ac_us08_expired_session_rejected_without_renewal` | 401 + `AUTH_SESSION_EXPIRED`；过期会话 `expires_at` 不变、`revoked_at` 为 None；他人会话不受影响 | 通过 | `pytest-final-20261026.xml` |
| AC-IN-11 | `test_ac_in11_full_nl_hits_retrieve_without_clarification` | `extraction_status=ok`、`missing_fields=[]`、`interrupt=None`、trace 含 `retrieve`/`report`、报告含 `## 结论` | 通过 | 同上 |
| AC-IN-13 | `test_ac_in13_clarification_missing_count_and_append` | 首问 5 项；补 1 项后剩 4 项；`process_temp_k` 不重现；`waiting_human`；`diagnosis_revision=1` | 通过 | 同上 |
| AC-DG-07 | `test_ac_dg07_confidence_0_7875_retries_once_top_k8_then_review` | `retry_count=1`、`top_k=8`、RT-07`retry`、`waiting_human`、`confidence=0.7875` | 通过 | 同上 |
| AC-DG-09 | `test_ac_dg09_supplement_bumps_revision_keeps_old_fields` | `diagnosis_revision=2`；存在 `revision=2` 的 `parse_input`；`torque_nm=55` 生效；旧字段未清空 | 通过 | 同上 |
| AC-DG-11 | 前端 e2e（非 pytest） | 刷新后复核面板恢复、TTL 剩余、确认后生成报告 | 通过（截图级，无机器日志） | `screenshots/e2e/19-*.png`、`20-*.png` |
| AC-DG-17 | `test_ac_dg17_report_twice_missing_differential_degrades_with_note` | `report_retry_count=1`、`degraded`、`REPORT_CHECK_FAILED`、首行缺项、RT-12 仅 1 次、`missing=鉴别诊断` | 通过（模板缺项分支；LLM 失败分支未覆盖） | 同上 |
| AC-KB-01 | `test_ac_kb01_fixed_query_top5_hdf_hit_and_covered` | `coverage=covered`、`max_score≥0.35`、Top-5 含 HDF、分数降序 | 通过 | 同上 |
| AC-KB-02 | `test_ac_kb02_same_type_cap_and_retry_keeps_threshold` | 每类 ≤2、降序；`retry_used=true`、`top_k=8`、`COVERED_SCORE=0.35`、coverage 不变 | 通过 | 同上 |
| AC-KB-06 | `test_ac_kb06_top5_hit_rate_is_measured_not_null` | `top5_hit_rate` 为 float、`0<rate≤1`、等于 `measure_top5_hit_rate`、固定集 50 条落盘 | 通过 | 同上 |
| AC-EV-03 | `test_ac_ev03_invalid_sample_failed_but_report_count_119` | `sample_total=120`、`report_count=119`、`accuracy=119/120`；第 61 条 `failed`+`feature_missing` | 通过 | 同上 |
| AC-EV-05 | `test_ac_ev05_rollback_restores_baseline_prompts_and_records_reason` | `rolled_back=true`、活动版本 `baseline-v1`、文件字节一致、审计 1 条 | 通过 | 同上 |
| AC-SY-03 | `test_health_reports_degraded_with_embedding_reason_when_bge_unavailable` | `status=degraded`、`embedding_reason=fallback:hash-ngram-512`、`vector_index=ok` | 通过 | 同上 |
| AC-SE-04 | `test_ac_se04_unauthorized_export_and_report_have_no_report_body` | `report.md`/`export.csv` 均 401 `AUTH_REQUIRED`；响应体无 `## 结论`/列名/报告前缀 | 通过 | 同上 |
| AC-SE-05 | `test_production_gate_blocks_missing_https_db_encryption_and_key` | 三项同缺 → `RuntimeError` 列出 HTTPS/DB 密钥/API Key；完整配置可启动 | 通过（未做单项隔离） | 同上 |

> 说明：`test_p1_startup.py` 中的 SY-03 / SE-05 用例名不含 AC 编号，按断言内容映射；其余用例名与 AC 一一对应。

## 7.3 缺口与“空洞/部分”用例（不自行补业务代码）

| 项 | 类型 | 说明 | 影响 |
| --- | --- | --- | --- |
| AC-DG-11 | 证据形态缺口 | 仅有 `19/20` 两张截图，无网络日志/自动化断言，无法证明“刷新触发了服务端快照恢复”而非纯前端本地状态 | 建议补一条 Playwright 断言（对 `/diagnoses/{id}` 200 + interrupt 字段） |
| AC-DG-17 | 覆盖缺口（分支） | 用例只覆盖“模板连续缺项 → degraded”；**未覆盖“报告 LLM 调用失败 → 重试 → degraded”**。现网红例：批次行 195 报告 LLM 失败后静默回落模板，`status=succeeded`、`report_retry_count=0`、`degraded_reasons` 空、`error_code=NULL` | 与 OBS-10 同源；该分支现网仍表现为“失败不可观测”，不能视为已闭环 |
| AC-SE-05 | 断言粒度 | 三项缺口一次性同时缺失，未逐项单独验证“缺一项即拒绝启动” | 风险低（门禁是聚合判断），但严格口径未逐项覆盖 |
| AC-SE-04（前端） | 场景差异 | 后端测试覆盖“无 Cookie → 401 无报告体”；e2e `18/21` 实为**会话过期**（toast“登录已过期，请重新登录”），非“无 Cookie”；前端“无 Cookie 导出跳登录”未补拍到 | 后端不泄露已证；前端 401 处理链路已有过期态证据，无 Cookie 态缺一张截图 |
| AC-IN-13 | 口径说明 | 用例未覆盖“澄清 30 分钟 TTL/无效补充不重置”；V2 条款只要求渐进澄清，TTL 由 AC-DG-22/23 覆盖 | 不计缺口，仅记录口径差异 |
| AC-EV-03 | 夹具说明 | 用 `monkeypatch` 固定样本集与入库函数，属夹具化验证，非真实 120 条跑批 | 与 `EVAL` 批次互补，可接受 |

## 7.4 KPI-04 复核（批次 `bch_01M5S9Q7P4VHTNTM5Z5X3PE5ZD`）

| 指标 | 值 |
| --- | --- |
| 行数 | 240 |
| 行状态 | `succeeded 209` + `degraded_review 30` + `failed 1`（第 31 行 `FEATURE_OUT_OF_RANGE`） |
| 成功行 | 239 |
| 成功率 | **239/240 = 99.58%**（≥99%） |
| `deepseek-chat` | **238**（`llm_used=true`） |
| `rule-engine` | **1**（第 195 行 `dx_01M5SAAPNQM2BAMB4X6151RA7P`，`duration_ms=8256`，`llm_used=false`） |
| 无诊断 | 1（第 31 行失败行） |

**回落原因（逐层复核）**：第 195 行 `diagnose` 步骤 2979ms、规则命中正常；`report` 步骤 **5166ms** 后返回 `model_name=rule-engine`。
`nodes.py` 报告节点对 `asyncio.TimeoutError`/异常执行 `logger.warning("report llm timeout ...")` 并回落模板，未写 `error_code`、未置 `degraded`，
`report_retry_count=0`（未按 AC-DG-17 重试一次）。
证据：`screenshots/evidence/AC-KPI-04-deepseek-report-meta.json`（含 240 行逐行 `model_name` 与回落行完整元数据）。

## 7.5 浏览器证据核对（`screenshots/e2e/18-21`）

| 截图 | 实际内容 | 与断言一致性 |
| --- | --- | --- |
| `18-401-redirect-login.png` | 登录页 + toast「登录已过期，请重新登录」 | 是**过期会话**（`AUTH_SESSION_EXPIRED`）触发 401 跳转，**不是“无 Cookie”**（`AUTH_REQUIRED`） |
| `19-review-refresh-restored.png` | 刷新后复核面板恢复：置信度 0.58、剩余 TTL、证据、补充/确认入口 | 与 AC-DG-11“刷新恢复 review 快照”一致 |
| `20-review-refresh-confirm-report.png` | 确认后生成报告：PWF 诊断报告、高置信度 0.58、已人工确认、耗时 6.1s | 与“确认后出报告”一致 |
| `21-export-401-redirect-login.png` | 导出请求触发 401 → 跳登录页（同一过期提示） | 与“未授权导出跳登录”一致，但场景同为**过期会话**，非无 Cookie |

> 未补拍“无 Cookie 导出”截图：需构造“未登录但已打开批量详情”的状态，现网前端在无 Cookie 时任何页面加载即跳登录，无法呈现导出动作；该场景由后端 `AC-SE-04` 用例覆盖（401 且响应体无报告内容）。

## 7.6 AC-CC-01 状态（第三轮留痕；**V5 已闭环**）

- 第三轮检索 `docs/`：当时仅见 `ARCH §10.4 C-011`，未见针对 AC-CC-01 的书面裁决，故当时维持“待评审裁决”。
- **现行状态**：产品方已批准并登记 `ARCH §10.4 C-012`，V5 已引用，AC-CC-01 判 **通过**；`C-012` 适用范围仅限 AC-CC-01（浏览器/版本覆盖），不外扩到其他 AC 或 KPI。
- 证据：7 组配置 × 6 步全通过（42 张截图）、`AC-CC-01-browser-smoke.json`、`screenshots/evidence/AC-CC-01-*.png`。

## 7.7 第三轮结论

| 维度 | 结果 |
| --- | --- |
| 全量测试 | 185/185 通过（0 失败/0 错误/0 跳过） |
| 新增证据闭环 | 14 条 AC 全部取得真实证据（13 条 pytest + 1 条 e2e 截图） |
| 仍存缺口 | AC-DG-17 的 LLM 失败分支（现网反例已在 §7.3 登记）、AC-SE-04 前端无 Cookie 场景、AC-DG-11 无机器断言、AC-SE-05 未做单项隔离 |
| 仍未验证 | 第三轮当时 3 条（AC-IN-05、AC-KB-05、AC-RP-05）→ **V5 为 0** |
| 待裁决 | 第三轮当时 1 条（AC-CC-01）→ **V5 为 0**（`C-012` 已裁决并引用） |
| 最终验收条件 | 第三轮当时不具备；**V5 已具备，判通过 90/90**（残余观察 OBS-01~12 不阻塞，见 §8） |

---

# 终轮（V5）

> 本节为当前口径。**判定以 `docs/FINAL-ACCEPTANCE-V5.md` 为准（通过 90/90）**；上文 §1–§7 为历史轮次证据登记，保留原文。

## 8.1 测试基线

| 项目 | 内容 |
| --- | --- |
| 基线文件 | `storage/pytest-accept-v5.xml` |
| 统计 | **194 collected / 0 failed / 0 error / 0 skipped**，耗时 50.686s |
| 相对 V4（192 条） | 移除 1 条旧 KB-06 用例、新增 3 条，净增 2 |
| 复验命令 | `cd backend; python -m pytest -q --junitxml=..\storage\pytest-accept-v5.xml` |

## 8.2 KPI 汇总（V5 复算）

| KPI | 结果 | 门槛 | 判定 | 说明 |
| --- | --- | --- | --- | --- |
| KPI-01 五分类（主验收） | **96.36%（106/110）** | ≥90% | 通过 | 依 `C-011`，仅覆盖 KPI-01 六分类门槛 |
| KPI-01 六分类（必须同时披露） | **88.33%（106/120）** | ≥90% | 未达门槛，披露不阻塞 | RNF 0/10、正常 4 条误判 TWF；不得隐去 |
| KPI-02 报告 8 要素 | **100%（120/120，960/960）** | ≥95% | 通过 | `elements_present=8` × 120 |
| KPI-03 延迟 | avg **6035.8ms** / P50 6035 / P95 **6685ms** / max 7530ms | avg 与 P95 ≤10s；max ≤15s | 通过 | eval 120 条成功样本 |
| 超时率 | **0/120 = 0.00%** | ≤1% | 通过 | artifact 全 succeeded |
| KPI-04 批量成功率 | **239/240 = 99.58%**；严格 DeepSeek **238/240 = 99.17%** | ≥99% | 通过 | 209 succeeded + 30 degraded_review；1 failed 排除 |
| KPI-05 捏造率 | **0/20 = 0.00%** | 0 | 通过 | 2 名评审、3 条分歧裁决；评审人为内部代号（OBS-09） |

## 8.3 AC 状态汇总

| 结果 | 合计 | P0 | P1 |
| --- | --- | --- | --- |
| 通过 | **90** | 78 | 12 |
| 未验证 | **0** | 0 | 0 |
| 失败 | **0** | 0 | 0 |
| 待裁决 | **0** | 0 | 0 |
| 合计 | **90** | **78** | **12** |

## 8.4 V4 → V5 唯一状态变化

| AC | V4 | V5 | 依据 |
| --- | --- | --- | --- |
| AC-KB-06 | 未验证（两次参数相同） | **通过** | `runs` 两组参数 `{400,50,5}` 与 `{200,20,8}` 各自建临时库实测；固定集 50 条；`delta = run2.rate - run1.rate = 0.0`；`repeat` 同参数 `consistent=true`；`params_changed=true`；active 知识版本仍仅 `kb_v1` |
| 其余 89 条 | 通过 | 通过 | 全量回归 194 用例全绿，关键证据文件本轮重写后未退化 |

## 8.5 本轮落盘证据（`storage/evidence/`）

| 文件 | 对应 AC |
| --- | --- |
| `AC-RP-05-report.json` | AC-RP-05（0.62 → `retry_count=1` → 确认 → 报告文案） |
| `AC-IN-05-xlsx-upload.json` | AC-IN-05（`.xlsx` → 415 `FILE_TYPE_NOT_ALLOWED`） |
| `AC-SY-01-llm-missing.json` | AC-SY-01（缺 Key：health degraded / 诊断 503） |
| `AC-KB-06-retrieval-comparison.json` | AC-KB-06（两组参数 + `delta` + `repeat`） |
| `AC-KB-06-param-sweep.json` | AC-KB-06（**与上一文件内容完全一致**，为对齐验收索引的等价副本，OBS-12） |
| `AC-HS-05-six-status-export.csv`、`AC-HS-05-export-summary.json` | AC-HS-05（六状态导出 + 待复核摘要 + 公式转义） |
| `AC-IN-17-history-after-delete.json` | AC-IN-17（删源文件后详情/报告/历史正常） |
| `AC-SE-02-formula-export.csv`、`AC-SE-02-formula-escape.json` | AC-SE-02（四个公式值带 `'` 前缀） |

## 8.6 残余观察（不构成阻塞，详见 V5 §7.2）

OBS-01~OBS-12 与 `docs/FINAL-ACCEPTANCE-V5.md` §7.2 一致，逐条说明见 `docs/DELIVERY-NOTES.md` §5。

## 8.7 终轮结论

- **90/90 通过**：P0 78/78、P1 12/12；未验证 0、失败 0、待裁决 0。
- **裁决引用边界**：`C-011` 仅覆盖 KPI-01 六分类门槛（六分类 88.33% 必须同时披露）；`C-012` 仅覆盖 AC-CC-01；未新增其他豁免。
- **冻结文档未改动**：PRD / ARCH / UIUX / DB / EVAL / FINAL-ACCEPTANCE V1–V5 均未被本轮修改。
