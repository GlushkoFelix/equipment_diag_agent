# 最终验收判定 V2（二次冷启动重判）

| 项目 | 内容 |
| --- | --- |
| 判定角色 | 最终验收审查员（冷启动，不采信窗口自述，不沿用上轮统计口径） |
| 判定依据 | PRD V3.0.0 附录 B（91→实为 **90** 条 AC，见 §1.2）、ARCH V1.2.0、UIUX V1.2.0、HANDOFF V1.2.2、DB V1.1.0、`docs/EVAL-评测报告.md`、`docs/AC-EVIDENCE-PACK.md`、`docs/DELIVERY-NOTES.md`、`docs/E2E-UI-测试记录.md`、`screenshots/evidence/`、后端 `pytest` 实测、现网 DB 复核 |
| 上一轮 | `docs/FINAL-ACCEPTANCE.md`（不通过：39 通过 / 14 失败 / 38 未验证） |
| 最终裁决 | **【不通过】**（P0 失败已清零，但 12 项 P0 证据缺口 + AC-CC-01 未裁决，仍属交付阻塞） |

---

## 0. 冷启动证据基线（本轮亲自执行）

### 0.1 实测环境与命令

| 项目 | 实测结果 | 命令/位置 |
| --- | --- | --- |
| 后端测试 | **169 收集 / 169 通过 / 0 失败 / 0 跳过 / 38.8s** | `cd backend && python -m pytest --junitxml=…`，逐文件：routing 34、features 19、diagnosis 12、p0_runtime 12、evaluation 11、chat 10、mapping 9、text_guard 7、reasoning 7、batch 6、db 6、llm_client 6、p0_intake 6、eval 5、sse 5、p0_knowledge 4、openapi 3、nodes_llm 3、p0_batch 2、batch_reconcile 1、start_script 1 |
| `.env` | `EDG_LLM_MODE=deepseek`，Key 存在（未回显） | 仓库根 `.env` |
| 冻结文档 | PRD 142KB / ARCH 224KB / UIUX 127KB / DB 90KB，均可读，本轮未修改 | `docs/` |
| 现网库 | `storage/app.db`，1082 条诊断；`knowledge_versions` 仅 `kb_v1` 为 `active`（14 条） | sqlite 只读查询 |
| KPI-01 产物 | `storage/eval/evb_01M5Q111XDZHNAA1YMCY2K14RR.json`，140 条（eval 120 + edge 20） | 逐条重算 |
| 浏览器证据 | `AC-CC-01-browser-smoke.json`：7 组配置 `pass=true`，42 张截图存在 | `screenshots/evidence/` |
| 敏感词表 | `config/sensitive_words.txt` 实际 **15** 词（≥12），由 `text_guard.load_sensitive_words()` 加载 | 文件实测 |

### 0.2 判定口径（本轮统一适用，不因窗口自述放宽）

- **通过**：该 AC 的可观测结果由可执行测试、真实 HTTP/浏览器产物或落盘 artifact 直接证明；纯静态实现仅在“无时序/集成/并发依赖且行为无歧义”时以“通过（静态）”计入，并在备注标明。
- **未验证**：实现存在，但该 AC 依赖运行时、集成、时序或特定夹具，缺少针对性证据，静态阅读无法排除偏差。
- **失败**：实现缺失、行为与 AC 冲突，或权威产物给出不达标结果。
- **待评审裁决**：存在环境不可得的客观偏差，须产品方书面裁决，审查员不得自行判过。

### 0.3 上一轮 AC 清单存在编号错位（本轮已纠正）

冷启动比对 PRD 附录 B 后发现上一轮判定表存在编号映射错误，直接导致“91 条”这一口径不成立。本轮以 PRD 附录 B 为唯一权威重建清单，**共 90 条**：

| 上轮写法 | PRD 实际 | 影响 |
| --- | --- | --- |
| AC-SY-05「生产环境自检」 | **PRD 无 AC-SY-05**（SY 仅 01–04），生产自检实为 **AC-SE-05** | 上轮凭空多出 1 条，导致 91 条 |
| AC-SE-04「CSV 公式注入」 | **AC-SE-04 = 无有效会话请求导出 → 未授权**（P0） | 真正的 P0 安全项被漏判为“通过” |
| AC-SE-05「登录失败锁定」 | **AC-SE-05 = `APP_ENV=production` 自检拒绝启动** | 登录锁定实为 AC-US-06 |
| AC-IN-19「映射方案」/ AC-IN-20「批量重复行」 | **AC-IN-19 = 批量重复行（P0）/ AC-IN-20 = 映射方案（P1）** | 优先级互换 |
| AC-IN-15「完整输入推进」 | **AC-IN-15 = `device_id` 必填与字符校验**（P0） | 描述错位 |
| AC-IN-16「重复表头」/ AC-IN-17「row_no 越界」 | **AC-IN-16 = 500/501 行边界 / AC-IN-17 = 删除源文件后历史详情（P1）** | 描述错位 |
| AC-RP-05 记为 P1 | **AC-RP-05 为 P0** | 优先级低估 |

> 结论：上轮的 64/14/13 不能沿用；本轮重新逐条判定。

---

## 1. 裁决摘要

### 1.1 计数（90 条，P0 78 / P1 12）

| 结果 | 合计 | P0 | P1 |
| --- | --- | --- | --- |
| 通过 | **69** | 63 | 6 |
| 未验证 | **16** | 14 | 2 |
| 失败 | **4** | **0** | 4 |
| 待评审裁决 | **1** | 1 | 0 |
| 合计 | 90 | 78 | 12 |

> P1 共 12 条：US-07、IN-17、IN-20、KB-03、KB-06、HS-03、HS-05、EV-05、EV-06、SY-03、SE-02、SE-05；其余 78 条为 P0。表中计数由脚本对 §5 全部 90 行回读校验，无重号无缺项。

对比上一轮（39 通过 / 14 失败 / 38 未验证）：
- **P0 失败从 9 条降至 0 条**，5 项原 P0 失败（AC-IN-14、AC-KB-04、AC-SY-04、AC-SE-01、AC-SE-03）经逐条复核确认真实落地并有测试；AC-DG-22、AC-EV-07、AC-US-03 的“通过”结论中，**只有 AC-DG-22、AC-US-03 站得住**（AC-EV-07 见 §3）。
- 未验证由 38 降至 16，但其中 **14 条为 P0**——不是“通过”，仍是交付阻塞证据缺口。

### 1.2 裁决理由（为何仍是不通过）

1. **KPI-04 与 KPI-05 两项 P0 指标证据无效**：KPI-04 的 240 行批次实测 `report_meta.model_name=rule-engine`（非 DeepSeek）；KPI-05 的 20 条“未覆盖边界样本”实测 `knowledge_missing_samples=0`（20/20 `supported`），前置条件根本未成立。
2. **12 项 P0 证据缺口未关闭**（见 §6），含检索质量（KB-01/02）、置信度/修订号/报告失败链路（DG-07/09/17）、NL 全链路（IN-11/13）、未授权导出（SE-04）、会话过期（US-08）。
3. **4 项 P1 缺陷仍在**：KB-06、EV-05、SY-03、SE-05。
4. **AC-CC-01 客观偏差未裁决**：Edge 仅 1 个大版本、Safari 以 WebKit 替代，审查员不得自行判过。

> C-011 只豁免 KPI-01 的六分类门槛，**不得**被扩大解释为放行 P0 证据缺口或其他 KPI。

---

## 2. KPI 判定（按 C-011，不扩大例外）

| KPI | 本轮复核值 | 门槛 | 判定 | 证据 |
| --- | --- | --- | --- | --- |
| KPI-01 主验收：五分类 | **96.36%（106/110）** | ≥90% | **通过（C-011）** | artifact 逐条重算：`HDF 20/20、PWF 20/20、OSF 20/20、TWF 20/20、正常 26/30` |
| KPI-01 六分类（必须披露） | **88.33%（106/120）** | ≥90% | 未达标（不阻塞，C-011） | 同上；差额 = 正常集 4 条 `wear≥190` + RNF 10 条 |
| KPI-02 报告 8 要素 | **100.00%（960/960）** | 100%（AC 门槛 ≥95%） | 通过 | artifact + `elements_present=8` 120/120 |
| KPI-03 延迟 | avg **6035ms**、P95 **6685ms**、max 7530ms | 平均 ≤10s 且 P95 ≤10s | 通过 | artifact `latency_ms` 140 条重算 |
| 超时率 | **0/120 = 0.00%** | ≤1% | 通过 | artifact `status=succeeded` 140/140 |
| KPI-04 批量成功率 | 99.58%（239/240）**但为 rule-engine 模式** | ≥99% | **未验证** | `bch_01M5Q64RH5FXF3XEEERKJZBX6K` 239 条诊断 `report_meta={"model_name":"rule-engine","llm_used":null}` |
| KPI-05 捏造率 | 0.00%（0/20）**但前置不成立** | 0 | **未验证** | `AC-EV-07-kpi05-review-llm.json`：`knowledge_missing_samples=0` |

**KPI-01 数据可用性**：可用（见 §4）。**KPI-04 / KPI-05 数据不可用于验收结论**，不得以“已达标”表述交付。

---

## 3. 重点复核项逐条结论

| 复核项 | 上轮结论 | 本轮结论 | 冷启动证据 |
| --- | --- | --- | --- |
| AC-DG-13 | 失败（运行中删索引仍 supported；重启自动 rebuild；空库启动崩） | **通过** | `test_ac_dg13_deleted_index_on_restart_marks_missing`：删 `index.faiss` 重启后 `/health` `vector_index=missing`、`status=degraded`、诊断 `knowledge_status=missing`、`primary_type=未覆盖`、报告含“知识库未覆盖”，且断言**索引文件不存在（不自动 rebuild）**；另两条测试覆盖内存缺失与空种子（不再触发 `entry_count>=1` 崩溃） |
| AC-DG-16 | 失败（3/3 次均为 `DIAGNOSIS_STATE_CONFLICT`） | **通过** | `test_ac_dg16_concurrent_resume_only_one_wins`：并发 2 次 resume → `[200, 409]`，失败方 `error.code=VERSION_CONFLICT`；另有 stale version 与 `records.set_running(expected_version)` 原子性测试；版本校验已前置于状态校验 |
| AC-US-03 | 失败（仅后端 422） | **维持通过** | `frontend/src/pages/LoginPage.tsx:147-192`（`PASSWORD_MIN_LENGTH`、`PasswordRuleHint`、`disabled={... || !checks.valid}`）；`AC-CC-01-edge-02-weak-password.png` 及 smoke JSON 中 3 引擎 `hint_visible/submit_disabled` 均为真 |
| AC-DG-22 | 失败（无 60s 调度） | **维持通过** | `main.py` lifespan 内 `ttl_loop` 后台任务（`interrupt_scan_seconds` 默认 60）；`test_ac_dg22_lifespan_ttl_scan_expires_without_requests` 在**零请求**下等到 `expired`，并断言无报告、`diagnosis_events` 写入 `expired` |
| AC-EV-07 | 通过（失败转通过） | **撤回通过 → 未验证** | 证据 JSON 自述 `knowledge_missing_samples=0`、20/20 `knowledge_status=supported`：AC 的 Given（20 条**未覆盖**边界样本）未成立，`fabrication_rate=0.0` 属“分母无区分力”的空转结论。AC-DG-13 修复后该场景已可构造，应重做 |
| AC-IN-14 | 失败（无 `user_correct` 留痕） | **通过** | `test_ac_in14_confirm_field_correction_writes_user_correct_without_revision`（`event=user_correct` 恰 1 条、`revision=1`、summary 含 `torque_nm`）+ 未修正时不写事件 |
| AC-KB-04 | 失败（无字段/类目校验） | **通过** | `test_ac_kb04_import_validation_reports_repairs_without_activation`、`test_ac_kb04_missing_advice_and_baseline_are_rejected`（缺“处置建议”/缺“正常基线”均拒绝且不激活） |
| AC-SY-04 | 失败（无一键启动） | **通过** | 仓库根 `start.ps1`（8.7KB）+ `test_start_script_exists_with_port_conflict_guidance`（文件存在且含端口占用提示与替代端口参数） |
| AC-SE-01 | 失败（无检测/无日志） | **通过** | `text_guard.sanitize_text`（7 类注入模式：中英指令覆盖、提示词窃取、角色劫持、安全绕过、分隔符）；`test_ac_se01_prompt_injection_rejected_and_diagnosis_continues` 3 类攻击 → `security_event=prompt_injection` 日志含 `text_sha256` 且无原文、消息落库已剥离注入片段、抽取继续（`torque_nm` 正确）；报告侧由 `test_reasoning` 的“丢弃伪造引用/数字”保证不含无关内容 |
| AC-SE-03 | 失败（4 词、无日志） | **通过** | `config/sensitive_words.txt` **15 词**；`mask_sensitive_words` 命中替换 `***` 并写 `security_event=sensitive_word_hit`（不含原文）；`test_text_guard` 3 条诱导样例 + 报告级脱敏；`report.build_report` 接入词表 |

> 结论：5 项原 P0 失败全部真实落地；“测试窗口自述”与代码/测试/产物三方一致，未发现伪造。

---

## 4. DeepSeek 真实生效核验（用户指定的前置条件）

| 核验点 | 结果 | 证据 |
| --- | --- | --- |
| `DELIVERY-NOTES` 声称的诊断 `dx_01M5RRHSM0QEYWNN1SDZMP259T` | **存在且一致** | 现网 `storage/app.db`：`status=succeeded`、`primary_type=HDF`、`confidence=0.95`、`duration_ms=4977`；`report_meta` = `{"model_name":"deepseek-chat","llm_used":true,"llm_calls":1,"prompt_version":"reporter-v1","template_version":"report.md.j2-v1","kb_version":"kb_v1"}` |
| 二次复核诊断 `dx_01M5RRZSGGX7WEEZ1NMRNTAYYJ` | **一致** | `report_meta` 同样为 `model_name=deepseek-chat`、`llm_used=true`、`llm_calls=1` |
| 评测批次真实性 | **真实网络调用** | artifact 140/140 `llm_used=true`，逐条 `latency_ms≈5980`（fake 基线为 108ms），与 EVAL §8 的 fake/deepseek 对照一致 |
| `.env` 当前模式 | `deepseek`（Key 存在） | 生效需重启进程 |
| 结论 | **KPI-01 数据可用** | 双条 `report_meta` 均满足 `model_name=deepseek-chat` 且 `llm_used=true` |

**附带发现（不阻塞，但需登记）**：`storage/eval/evb_….json` 的逐样本字段**不含** `report_meta`/`model_name`/`prompt_version`，KPI-01 的“模型与提示词版本固定”只能由 EVAL 文档 + 现网 DB 侧证，artifact 自身不可自证（OBS-07）。

---

## 5. 逐条 AC 判定（90 条）

### 5.1 账号与会话（US，8）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-US-01 | P0 | 通过 | `extras-auth-upload-history.json`（201/200/`me` 一致） | |
| AC-US-02 | P0 | 通过 | 同上（409 `USERNAME_TAKEN`） | |
| AC-US-03 | P0 | 通过 | `LoginPage.tsx:147-192` + 3 引擎弱口令截图 | 即时提示 + 禁提交 |
| AC-US-04 | P0 | 通过 | `extras-auth-upload-history.json`（401 统一文案） | |
| AC-US-05 | P0 | 通过 | 同上（401 `AUTH_REQUIRED`）+ `App.tsx` 路由保护 | |
| AC-US-06 | P0 | 通过 | `extras2-edge-cases.json`（第 5 次 423、`Retry-After=300`、正确密码仍 423） | |
| AC-US-07 | P1 | 通过 | `test_auth_flow`（退出后 `/auth/me` 401） | |
| AC-US-08 | P0 | **未验证** | `security.py` 静态 24h；无 25h Cookie 构造测试 | **必须补齐**（令牌生命周期属安全项） |

### 5.2 输入与校验（IN，21）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-IN-01 | P0 | 通过 | `test_csv_upload_and_single_diagnosis` + `E2E §1`（文件名/行号/入口类型） | |
| AC-IN-02 | P0 | 通过 | 证据包（中文表头 7/7 自动映射） | |
| AC-IN-03 | P0 | 通过 | `test_mapping_preview_missing_required_is_not_valid` + `MappingModal` 标红/禁提交 | |
| AC-IN-04 | P0 | 通过 | 证据包（6MB → 413 `FILE_TOO_LARGE`） | 600 行未单独构造，条件为“6MB 或 600 行” |
| AC-IN-05 | P0 | 通过（静态） | `uploads.py:150-151` 非 `.csv` → 415 `FILE_TYPE_NOT_ALLOWED` | 行为无歧义；无独立用例 |
| AC-IN-06 | P0 | 通过 | `test_batch_create_and_counts_conserved` + 240 行真实任务（`degraded_review=32`） | 该批次 `failed=1` 故终态 `partially_failed`，与“全合规行”夹具不同 |
| AC-IN-07 | P0 | 通过 | `AC-KPI-04-batch-rows.json` 第 31 行 `failed`、`error_field=air_temp_k`、其余 239 行继续 | 夹具为范围错误而非 `torque=abc`，行为等价 |
| AC-IN-08 | P0 | 通过 | `test_batch_cancel_then_idempotent` + `E2E §2` | |
| AC-IN-09 | P0 | 通过 | `test_out_of_range_rejected` + 前端字段即时校验 | |
| AC-IN-10 | P0 | 通过 | 规则核验（L 型 / 60Nm / 200min → `wear_torque=12000 > 11000` → OSF） | |
| AC-IN-11 | P0 | **未验证** | 无“NL 7 项齐全 → 直接 retrieve、无追问”的端到端记录 | **必须补齐**（NL 主链路） |
| AC-IN-12 | P0 | 通过 | `test_nl_partial_clarification_and_resume` + `E2E §3` | |
| AC-IN-13 | P0 | **未验证** | 无“二次追问仅列剩余 4 项、已补项不重现、状态仍 `waiting_human`”测试 | **必须补齐** |
| AC-IN-14 | P0 | 通过 | `test_p0_intake`（`user_correct` + `revision=1`；未修正不写事件） | 本轮由失败转通过 |
| AC-IN-15 | P0 | 通过 | `test_device_id_required_and_validated`、`test_device_id_invalid_values`（含 65 字符/`/`）+ 422 不建诊断 | |
| AC-IN-16 | P0 | 通过 | 证据包（501 行 → 422 `CSV_ROW_LIMIT_EXCEEDED`） | 500 行接受未单独断言，由配置上限与 240 行任务侧证 |
| AC-IN-17 | P1 | **未验证** | 无“删除源文件后历史仍显示文件名/行号/入口”测试 | 可带风险接受（元数据已冗余落库，风险中等） |
| AC-IN-18 | P0 | 通过 | `test_machine_stopped_blocked`（转速=0/扭矩=0 阻断） | |
| AC-IN-19 | P0 | 通过 | `test_ac_in20_duplicate_rows…`（10 行完全相同 → 10 个独立 `diagnosis_id`、`row_no=1..10`） | 测试名编号错位（应为 IN-19），行为正确 |
| AC-IN-20 | P1 | 通过 | `test_mapping_scheme_crud`（保存/复用/删除/清空） | 同名覆盖与冲突提示未逐条断言 |
| AC-IN-21 | P0 | 通过 | `test_ac_in21_batch_timeout_cancels_pending_rows` + `AC-IN-21-batch-timeout.json` | |

### 5.3 诊断与状态机（DG，24）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-DG-01 | P0 | 通过 | 规则核验 + EVAL（正常 26/30、KPI-02 8/8） | |
| AC-DG-02 | P0 | 通过 | 规则核验（温差 7.2K/1250rpm → HDF）+ EVAL 20/20 | |
| AC-DG-03 | P0 | 通过 | 规则核验（功率 3204W → PWF）+ EVAL 20/20 | |
| AC-DG-04 | P0 | 通过 | 规则核验（L 型 12000 > 11000 → OSF）+ EVAL 20/20 | |
| AC-DG-05 | P0 | 通过 | 规则核验（210min → TWF）+ EVAL 20/20 + RNF 无兜底测试 | |
| AC-DG-06 | P0 | 通过 | 规则核验（OSF+HDF，主 OSF；多标签优先级测试） | |
| AC-DG-07 | P0 | **未验证** | 仅 `test_rt07_medium_confidence_first_retries_once`（路由层） | **必须补齐** 0.7875 集成夹具（trace `retry_count=1` + Top-8） |
| AC-DG-08 | P0 | 通过 | `test_review_confirm_generates_report`（confirm 后仅出报告） | |
| AC-DG-09 | P0 | **未验证** | 仅 `test_rt10_review_supplement_rebuilds_parse`（路由层） | **必须补齐** `diagnosis_revision=2` + 旧数据保留 |
| AC-DG-10 | P0 | 通过 | `test_rt11_abort_goes_aborted` + `25-aborted.png` | |
| AC-DG-11 | P0 | **未验证** | 快照中断载荷代码 + `13-resumed-review.png` | 可带风险接受（快照契约测试已覆盖载荷；缺刷新网络记录） |
| AC-DG-12 | P0 | 通过 | `useDiagnosisStream.ts`（服务端 `retry` 原生重连；3 次失败转 2s 轮询）+ `08/09` 截图 | |
| AC-DG-13 | P0 | 通过 | `test_ac_dg13` ×3（重启 missing、不 rebuild、报告声明未覆盖） | 本轮由失败转通过 |
| AC-DG-14 | P0 | 通过 | `test_ac_dg23` + `AC-DG-23-ttl-db-events.json`（过期后新建 id 不同） | |
| AC-DG-15 | P0 | 通过 | `test_rt17_deduplicates_active_diagnosis`（200 + `deduplicated`） | |
| AC-DG-16 | P0 | 通过 | `test_ac_dg16` ×3（`VERSION_CONFLICT`） | 本轮由失败转通过 |
| AC-DG-17 | P0 | **未验证** | 仅 `test_rt12/test_rt13`（路由）；现网 `EDGE-19` 报告 LLM 超时回落模板后仍 `succeeded` | **必须补齐**（且该现网案例提示失败未降级，风险高） |
| AC-DG-18 | P0 | 通过 | `test_rt08_low_confidence_first_never_retries`（`retry_count=0`） | |
| AC-DG-19 | P0 | 通过 | `test_temp_inversion_is_quality_flag`（不判 HDF/正常、置信度下降） | |
| AC-DG-20 | P0 | 通过 | `test_rt08_batch_low_confidence_goes_auto_review` | 无 240 行夹具，但真实批次出现 32 条 `degraded_review` |
| AC-DG-21 | P0 | 通过 | `test_ac_dg21` ×4（parse/retrieve/diagnose/report 超窗）+ `AC-DG-21-timeout.json`（4 节点 16.4–16.5s、无报告、SSE 终态） | 测试按 0.5s/1.6s 等比压缩，非恰好 15s |
| AC-DG-22 | P0 | 通过 | `test_ac_dg22`（零请求自动 `expired`） | 本轮由失败转通过 |
| AC-DG-23 | P0 | 通过 | `test_ac_dg23`（409 `DIAGNOSIS_EXPIRED`、无报告） | |
| AC-DG-24 | P0 | 通过 | `test_rt10_round_two_supplement_is_rejected` + `E2E §4` | |

### 5.4 知识库（KB，6）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-KB-01 | P0 | **未验证** | 无 Top-5 含 HDF、`max_score≥0.35`、`coverage=covered` 断言 | **必须补齐**（检索质量主口径） |
| AC-KB-02 | P0 | **未验证** | 无“同类型 ≤2 条、按分数降序”多样性测试 | **必须补齐** |
| AC-KB-03 | P1 | 通过 | `test_ac_kb03_import_activate_rollback_is_manual`、`test_ac_kb03_manifest_and_entry_count_recorded` | 本轮由失败转通过（不再自动覆盖线上版本） |
| AC-KB-04 | P0 | 通过 | `test_ac_kb04` ×2（缺字段/缺类目拒绝、不激活） | 本轮由失败转通过 |
| AC-KB-05 | P0 | 通过 | `test_ac_dg13`（`/health` `vector_index=missing`、`status=degraded`、其余入口 202 正常、不伪造结论） | `hits=[]`/`max_score=0`/`coverage=none` 数值未直接断言 |
| AC-KB-06 | P1 | **失败** | `evaluation.py:535` `top5_hit_rate: None` | 50 条检索集与前后对比缺失 |

### 5.5 报告（RP，7）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-RP-01 | P0 | 通过 | EVAL KPI-02 100%（960/960） | |
| AC-RP-02 | P0 | 通过 | `30-evidence-drawer.png` + `test_reasoning`（evidence 绑定、未知引用丢弃） | |
| AC-RP-03 | P0 | 通过 | `ReportPanel.tsx` `react-markdown` + `skipHtml`；`report.py` 清洗原始 HTML | |
| AC-RP-04 | P0 | 通过 | `E2E §1` 导出 200 + `filename*=UTF-8''` | |
| AC-RP-05 | P0 | **未验证** | 仅 `test_routing` 的 0.62 分支断言 | 可带风险接受（RT-07 已单测；缺“数值+文字同现”断言） |
| AC-RP-06 | P0 | 通过 | `report.py` 强制追加免责声明；120/120 自检 | 无删除端点 |
| AC-RP-07 | P0 | 通过 | EVAL 8/8 + `test_rt12/test_rt13`（缺项清单与 `report_retry_count`） | |

### 5.6 历史（HS，6）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-HS-01 | P0 | 通过 | 证据包（`status=succeeded&page_size=5` → `total=16`，时间倒序） | |
| AC-HS-02 | P0 | 通过 | `records.py` `ORDER BY created_at, rowid` + `test_snapshot_trace_steps…` | 同毫秒先后稳定 |
| AC-HS-03 | P1 | 通过 | 证据包（DELETE 批量诊断 409）+ 非批量终态可删 | |
| AC-HS-04 | P0 | 通过 | 证据包（他人 `diagnosis_id` → 404 `DIAGNOSIS_NOT_FOUND`） | |
| AC-HS-05 | P1 | **未验证** | `AC-KPI-04-batch-export.csv` 实测仅 3/6 状态（`succeeded 207 / degraded_review 32 / failed 1`），缺 `degraded`、`failed_timeout`、`cancelled` | 可带风险接受（导出列齐全、`_csv_safe` 静态；缺“待人工复核”摘要断言） |
| AC-HS-06 | P0 | 通过 | `02-workbench-idle.png`、`14-chat-empty.png`、`22-history-drawer.png` | |

### 5.7 评测（EV，8）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-EV-01 | P0 | 通过 | artifact（指标表/混淆矩阵/逐样本/bad case/版本/耗时）；`docs/EVAL` | 调参记录存在但 `top5_hit_rate=null`（另计 KB-06） |
| AC-EV-02 | P0 | 通过（C-011） | 五分类 96.36% ≥90%；KPI-02 100%；KPI-03 avg 6035/P95 6685；超时率 0 | 六分类 88.33% 同时披露 |
| AC-EV-03 | P0 | **未验证** | 无“非法样本 → `failed`、其余继续、分母仍 120”测试 | **必须补齐**（KPI 口径完整性） |
| AC-EV-04 | P0 | 通过 | artifact（avg 6035 / P50 5998 / P95 6685 / max 7530 / 超时 0） | |
| AC-EV-05 | P1 | **失败** | 全仓无提示词回归/自动回滚实现（`grep baseline|rollback` 无业务代码） | |
| AC-EV-06 | P1 | 通过 | `27/28/29` 截图 + `test_eval_contract` ×5 | |
| AC-EV-07 | P0 | **未验证** | 证据集 20/20 `supported`、`knowledge_missing_samples=0` | **必须补齐**（前置未成立；DG-13 修复后已可构造） |
| AC-EV-08 | P0 | **未验证** | 240 行批次 `report_meta={"model_name":"rule-engine","llm_used":null}` | **必须补齐**（需 deepseek 模式重跑） |

### 5.8 系统（SY，4）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-SY-01 | P0 | 通过（静态） | `startup.py` `llm_config=missing` + `services.ensure_llm_configured` 503 | 无“缺 Key 启动”测试 |
| AC-SY-02 | P0 | 通过 | `test_health_contract`（`X-Request-Id`）+ 日志字段静态 | 无密码/令牌脱敏断言 |
| AC-SY-03 | P1 | **失败** | `startup.py:23-26`：回退向量后端仍记 `embedding_model=ok`，`status` 不会 degraded | BGE 异常无 degraded 与原因 |
| AC-SY-04 | P0 | 通过 | `start.ps1` + `test_start_script_exists_with_port_conflict_guidance` | 本轮由失败转通过 |

### 5.9 安全（SE，5）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-SE-01 | P0 | 通过 | `test_ac_se01` ×3 + `test_text_guard`（检测/脱敏日志/流程继续/报告无无关内容） | 本轮由失败转通过 |
| AC-SE-02 | P1 | 通过（静态） | 证据包（`.exe` → 415）+ `batches.py` `_csv_safe` 前缀单引号 | 公式转义无独立用例 |
| AC-SE-03 | P0 | 通过 | 15 词表 + `test_text_guard` 3 条 + 报告脱敏 + 命中日志 | “标准提示”文案未断言 |
| AC-SE-04 | P0 | **未验证** | 无“无有效会话请求导出 → 401 且不返回报告内容”测试 | **必须补齐**（上轮被误作公式注入而漏判） |
| AC-SE-05 | P1 | **失败** | 无 `APP_ENV=production` 自检（HTTPS/DB 加密/密钥拒绝启动） | 上轮误记为 AC-SY-05 |

### 5.10 兼容性（CC，1）

| AC-ID | P | 结论 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-CC-01 | P0 | **待评审裁决** | `AC-CC-01-browser-smoke.json` 7/7 `pass=true`、42 张截图；Chrome 155/156、Firefox 155/157、WebKit 26.6/27.2 双版本；**Edge 仅 156 单版本**、**Safari 以 WebKit 内核替代** | 见 §7 |

---

## 6. 未验证 16 条：必须补齐 / 可带风险接受

### 6.1 必须补齐（12 条 P0，阻塞）

| AC-ID | 缺口 | 最低补证要求 |
| --- | --- | --- |
| AC-US-08 | 25h 会话 Cookie | 构造过期签发时间 → `/auth/me` 401 + 页面跳登录（自动化） |
| AC-IN-11 | NL 7 项齐全直达 | E2E/契约：抽取 7/7 → 无追问 → `retrieve` 节点出现 → 报告 |
| AC-IN-13 | 渐进式澄清 | 二次追问仅列剩余 4 项、已补项不重现、状态仍 `waiting_human` |
| AC-DG-07 | 0.7875 夹具 | 集成夹具：首次 0.7875 → `retry_count=1` + Top-8 → `waiting_human` |
| AC-DG-09 | revision 递增 | `diagnosis_revision=2`、`revision=2` 的 `parse_input` 步骤、旧字段保留 |
| AC-DG-17 | 报告缺项链路 | 模板连续两次缺“鉴别诊断” → `report_retry_count=1` + `degraded` + 顶部缺项 + 告警 1 次 |
| AC-KB-01 | Top-5/覆盖率 | 固定 query → 含 HDF 条目、`max_score≥0.35`、`coverage=covered` |
| AC-KB-02 | 多样性 | 同类型 5 条 query → 同类型 ≤2 条、分数降序 |
| AC-EV-03 | KPI 分母 | 第 61 条置非法 → `failed`、其余继续、`report_count=119`、分母仍 120 |
| AC-EV-07 | KPI-05 前置 | 20 条**真实未覆盖**样本（可用 DG-13 的 missing 索引路径）+ 2 名评审逐条两项判定 |
| AC-EV-08 | KPI-04 环境 | `EDG_LLM_MODE=deepseek` 重跑 240 行，保留新旧批次对比与 artifact |
| AC-SE-04 | 未授权导出 | 无 Cookie 请求 `/batches/{id}/export.csv`（及 `/diagnoses/{id}/report.md`）→ 401，响应体不含报告 |

### 6.2 可带风险接受（4 条，需在交付说明中登记）

| AC-ID | 缺口 | 接受理由 | 残余风险 |
| --- | --- | --- | --- |
| AC-DG-11 | 刷新后 review 恢复无网络记录 | 快照中断载荷有契约测试；有 `13-resumed-review.png` 实拍 | 刷新时序异常时面板可能不可操作（中） |
| AC-RP-05 | 0.62 数值+文字同现未断言 | RT-07 分支已单测；报告模板含置信度渲染 | 文案缺失不易被测试发现（低） |
| AC-IN-17 | 删源文件后历史详情未测 | 文件名/行号/入口类型已冗余落库（`diagnoses`/批次行） | 源文件清理策略变更时回归（低） |
| AC-HS-05 | 六状态导出仅实测 3 种 | 导出列齐全（含 `error_field/error_code`）、`_csv_safe` 静态可核 | `degraded`/`failed_timeout` 行摘要文案未验证（低） |

---

## 7. AC-CC-01：待评审裁决（审查员不自行通过）

### 7.1 已达成

- 四引擎覆盖：Chrome 156 / Chrome 155（Chrome for Testing）/ Edge 156 / Firefox 157 / Firefox 155 / WebKit 27.2 / WebKit 26.6，**7 组配置 × 6 步全部 `pass=true`**（登录、弱口令即时提示、表单诊断、SSE 实时进度、报告渲染、历史抽屉），共 42 张截图。
- 主链路无阻断性错误，SSE 正常。

### 7.2 未达成（客观不可得）

1. **Edge 第二个大版本**：Microsoft 无公开历史版本分发渠道，仅 156.0.4314.42；Chromium 内核已由 Chrome 155/156 覆盖，但不能替代 Edge 自身版本回归。
2. **原生 Safari**：Windows 无 Safari，以 Playwright WebKit（同源内核）替代；缺 Safari 专有差异（ITP、字体渲染、滚动/弹窗定位）。

### 7.3 接受条件（须产品方书面裁决并登记 ARCH §10.4）

- 条件 A（接受）：① 出具“Edge 单一版本 + WebKit 替代 Safari”的书面风险接受，明确残余风险由发布方承担；② 交付说明与验收记录不得写“四浏览器最新两个大版本全部通过”，只能写“四引擎覆盖，两个版本维度 3/4 族达成”；③ 建议补充一次 macOS 真机 Safari 冒烟与 Edge 企业版回滚渠道验证作为发布后 30 天内补测项。
- 条件 B（不接受）：在具备 Edge 次新版本安装包的机器补 1 次同链路冒烟，并在 macOS 真机 Safari 走 1 次同链路，方可判通过。

---

## 8. 必须关闭的阻塞项

### 8.1 P0 阻塞（全部关闭后方可重验）

1. **KPI-04 环境**：deepseek 模式重跑 240 行批量，替换 `rule-engine` 批次结论（AC-EV-08）。
2. **KPI-05 有效性**：以真实“知识未覆盖”样本重做 20 条评审（AC-EV-07）。
3. **未授权导出**：补 AC-SE-04 用例（P0 安全）。
4. **KPI 口径**：补 AC-EV-03 非法样本与分母测试。
5. **检索质量**：补 AC-KB-01、AC-KB-02。
6. **置信度/修订/报告失败链路**：补 AC-DG-07、AC-DG-09、AC-DG-17 集成夹具。
7. **NL 链路**：补 AC-IN-11、AC-IN-13。
8. **会话过期**：补 AC-US-08。
9. **AC-CC-01**：取得产品方书面裁决（§7）。

### 8.2 P1（交付前修复）

- AC-KB-06 `top5_hit_rate` 落值（`evaluation.py:535`）。
- AC-EV-05 提示词回归/自动回滚。
- AC-SY-03 BGE 异常 → `/health` degraded 并指明原因。
- AC-SE-05 `APP_ENV=production` 自检（HTTPS/DB 加密/密钥，失败拒绝启动）。

### 8.3 转“有条件通过”的最低条件

仅当产品方书面接受以下全部内容，且登记为新契约条目（建议 `ARCH §10.4 C-012`，不得复用/扩大 C-011）：

1. §6.2 的 4 项 P1/P0 残余风险与 §7.3 条件 A 的浏览器偏差；
2. §8.2 的 4 项 P1 缺陷作为已知缺陷上线并给出修复时间点；
3. §8.1 的 9 项 P0 在发布前关闭（不可仅“计划关闭”）。

在上述书面接受缺位时，本判定维持 **不通过**。

---

## 9. 其他偏差与观察（登记，不改变 AC 表）

| 编号 | 现象 | 证据 | 影响 |
| --- | --- | --- | --- |
| OBS-01 | `/confirm` 命中 RT-17 后前端误置 `terminal` — **已修复** | `ChatPanel.tsx:217-220`（仅终态才 `terminal`）+ `test_obs01_confirm_dedup_keeps_active_session_and_non_terminal_status` | 已闭环 |
| OBS-02 | `knowledge.build()` 自动归档旧 active — **已修复** | `test_ac_kb03_import_activate_rollback_is_manual`（手动 activate/rollback） | 已闭环 |
| OBS-03 | `run_once()` 无生产调度 — **已修复** | `main.py` lifespan `ttl_loop` + `test_ac_dg22` | 已闭环 |
| OBS-04 | `E2E-UI-测试记录.md` §6 两项待修复与代码不一致（代码已修、文档未回写） | `mapping.py` + `records.py:402` 与测试一致；E2E 文档仍写旧问题 | 验收材料陈旧，建议回写 |
| OBS-05 | RETRY 只扩大 `top_k`，不降低覆盖阈值 | `knowledge.py` 重试分支 | 与 ARCH 检索调参语义有偏差，随 AC-KB-02 一并复核 |
| OBS-06 | 上一轮判定表 AC 编号错位（多出 AC-SY-05、AC-SE-04/05 错位、IN-15~20 错位、RP-05 优先级） | §0.3 | 已导致“91 条”错误口径；建议在验收日志勘误并留存 |
| OBS-07 | 评测 artifact 不含 `report_meta`/`model_name`/`prompt_version` | `storage/eval/evb_….json` 字段仅 15 个 | KPI-01 的版本可追溯性依赖文档与现网 DB 侧证，建议 artifact 增列 |
| OBS-08 | 测试命名错位：`test_ac_in20_duplicate_rows…` 实对应 AC-IN-19；`test_ac_dg13` 已正确 | `tests/contract/test_p0_batch.py:49` | 仅命名问题，不影响行为，建议改名 |
| OBS-09 | KPI-04 批次在 `rule-engine` 模式产生，交付文档称“KPI-04 通过” | 现网 DB `report_meta` | 表述需回写环境口径，否则易被读作 DeepSeek 下达标 |
| OBS-10 | `EDGE-19` 报告 LLM 超时回落模板后 `status=succeeded`、`degraded_reasons=[]` | `AC-EVIDENCE-PACK.md` §1 / 现网批次 | 失败可观测但未降级，与 AC-DG-17 同源风险，须在补测中一并确认 |

---

## 10. 重验入口

```powershell
# 后端
cd backend; python -m pytest -q            # 基线 169 passed，须保持且新增用例全绿

# 评测（deepseek 模式，重跑 KPI-04/KPI-05 与 KPI-01 对照）
python scripts/run_evaluation.py

# 批量 KPI-04（deepseek 模式 240 行，保留新旧批次）
python C:\Users\25352\AppData\Local\Temp\qa_edg\qa_api.py kpi04

# E2E：CSV 单条 / 批量取消导出 / NL 两次澄清 / review 两轮 / chat 全链路 / 四浏览器
python C:\Users\25352\AppData\Local\Temp\qa_edg\browser_smoke_v2.py
```

**重验判据**：169 基线不回退；§8.1 九项全部有可复核证据；§8.2 四项关闭；AC-CC-01 有书面裁决；KPI-04/KPI-05 在 deepseek 模式下重新落值。

---

## 11. 结论

| 维度 | 结论 |
| --- | --- |
| P0 功能失败 | **0 条**（上轮 9 条全部关闭并经测试/Runtime 证据确认） |
| P0 证据缺口 | **12 条必须补齐 + 2 条可带风险接受 + 1 条待裁决** |
| P1 缺陷 | **4 条失败 + 2 条未验证** |
| KPI | KPI-01/02/03/超时率 达标（KPI-01 按 C-011）；KPI-04、KPI-05 **证据无效** |
| 最终裁决 | **【不通过】** |
| 唯一转正路径 | 产品方书面裁决 §7 + 接受 §6.2/§8.2 + 关闭 §8.1 全部 P0 后重新验收（新契约条目 C-012） |

> 本文件为新增判定文档，未修改任何冻结文档（PRD/ARCH/UIUX/HANDOFF/DB/EVAL/FINAL-ACCEPTANCE 均未改动）。
