# 最终验收判定 V3（第三次冷启动重判）

| 项目 | 内容 |
| --- | --- |
| 判定角色 | 最终验收审查员（冷启动；不采信任何窗口自述；不沿用 V2 统计口径） |
| 权威清单 | PRD 附录 B，本报告自行复核为 **90 条（P0 78 / P1 12）**，见 §0.3 |
| 测试基线 | `storage/pytest-accept-20261026.xml`：**185 collected / 0 failed / 0 error / 0 skipped / 56.68s** |
| 本轮代码/产物 | 后端 `185` 条测试、`storage/app.db`、`storage/eval/evb_01M5Q111XDZHNAA1YMCY2K14RR.json`、KPI-05 v2 证据包、`screenshots/e2e/18-21` |
| 最终裁决 | **【不通过】**（P0 无失败，但 3 项 P0 未验证 + 1 项 P0 待裁决；P1 仍有 1 项失败） |

---

## 0. 裁决摘要

### 0.1 计数（90 条，P0 78 / P1 12）

| 结果 | 合计 | P0 | P1 |
| --- | --- | --- | --- |
| 通过 | **82** | 74 | 8 |
| 未验证 | **6** | 3 | 3 |
| 失败 | **1** | 0 | 1 |
| 待评审裁决 | **1** | 1 | 0 |
| 合计 | **90** | **78** | **12** |

> 计数由脚本对 §7 全部 90 行回读校验：无重号、无缺项，P0/P1 合计与 PRD 附录 B 一致。

### 0.2 与 V2 的差异（19 项状态变化 + 2 项维持）

| 变化 | AC | 依据 |
| --- | --- | --- |
| 未验证 → 通过（13） | AC-US-08、IN-11、IN-13、DG-07、DG-09、DG-11、DG-17、KB-01、KB-02、EV-03、EV-07、EV-08、SE-04 | 本轮 16 条新用例、KPI-05 v2、e2e 19/20 截图、240 行 DeepSeek 批次 |
| 失败 → 通过（3） | AC-EV-05、SY-03、SE-05 | `prompt_regression.py`、`startup.py:25-29`、`config.py::production_startup_gaps` + `main.py:30` |
| 通过 → 未验证（3） | AC-IN-05、SY-01、SE-02 | V2 标为“通过（静态）”；V3 口径不接受纯静态实现作为针对性证据 |
| 维持失败（1） | AC-KB-06 | 已落 Top-5 实测值，但“前后对比”“同参数重复一致”未实现/未断言 |
| 维持待裁决（1） | AC-CC-01 | ARCH §10.4 仍只有 C-010、C-011，无 C-012 |

### 0.3 权威清单复核

从 PRD 附录 B 逐行提取并按 AC 编号去重，得到 90 条：US 8、IN 21、DG 24、KB 6、RP 7、HS 6、EV 8、SY 4、SE 5、CC 1；按优先级列为 **P0 78 / P1 12**。P1 的 12 条为：US-07、IN-17、IN-20、KB-03、KB-06、HS-03、HS-05、EV-05、EV-06、SY-03、SE-02、SE-05。V2 已纠正的“91 条/AC-SY-05 不存在”等编号错位，本轮复核维持 V2 结论。

---

## 1. KPI 判定（C-011 只覆盖 KPI-01 六分类门槛）

| KPI | 本轮复核值 | 门槛 | 判定 | 证据 |
| --- | --- | --- | --- | --- |
| KPI-01 主验收：五分类 | **96.36%（106/110）** | ≥90% | **通过（C-011）** | artifact 逐条重算；HDF/PWF/OSF/TWF 各 20/20、正常 26/30 |
| KPI-01 六分类（必须同时披露） | **88.33%（106/120）** | ≥90% | **未达门槛**；按 C-011 披露、不阻塞，例外不得外扩 | RNF 0/10（9 条判正常、1 条判未覆盖）、正常 4 条判 TWF |
| KPI-02 报告 8 要素 | **100%（120/120，960/960 要素）** | ≥95%（AC-RP-01 另要求自检 8/8） | 通过 | artifact `elements_present=8` 120/120 |
| KPI-03 延迟 | avg **6035.8ms** / P50 6035 / P95 **6685ms** / max **7530ms** | 平均与 P95 ≤10s；最大值 ≤15s | 通过 | 仅 eval 120 条成功样本；edge 20 条另计 |
| 超时率 | **0/120 = 0.00%** | ≤1% | 通过 | artifact `status=succeeded` 140/140 |
| KPI-04 批量成功率 | **239/240 = 99.58%**；严格 DeepSeek 口径 **238/240 = 99.17%** | ≥99% | 通过 | 209 `succeeded` + 30 `degraded_review`；1 `failed` 不计分子；239 份报告中 238 份 `deepseek-chat`、1 份 `rule-engine` 可观测降级 |
| KPI-05 捏造率 | **0/20 = 0.00%** | 0 | 通过 | KPI-05 v2：20 条真实未覆盖样本 + 2 名评审人 + 3 条分歧裁决 |

**KPI-01 数据可用性**：可用。artifact 140/140 `llm_used=true`，现网批次 238/239 报告 `model_name=deepseek-chat`，两者一致，不存在规则模板冒充 DeepSeek 的情况。

**KPI-04 口径说明**：240 行中第 31 行在特征校验阶段 `failed`（`FEATURE_OUT_OF_RANGE`，`air_temp_k`），不生成诊断与报告，因此只有 239 份 `report_meta`。239 份中 1 份为 `rule-engine`（`llm_used=false`，状态仍 `succeeded`），属可观测的 LLM 回落；严格按 DeepSeek 口径仍为 238/240=99.17%，≥99%。

---

## 2. 必查 1：测试基线与新增用例真实性

### 2.1 基线

```
cd backend
python -m pytest -q --junitxml=..\storage\pytest-accept-20261026.xml
```

解析 `testsuite` 属性：`tests=185, failures=0, errors=0, skipped=0, time=56.684`。与 `pytest-p0-fix2.xml`（169）逐用例名比对，新增恰为 **16 条**，无删除、无改名丢失。

### 2.2 16 条新用例抽检（逐文件阅读源码，确认非空洞断言）

| 新用例 | 真实断言（非仅 200/非仅存在） |
| --- | --- |
| `test_ac_se04_unauthorized_export_and_report_have_no_report_body` | 报告与批量导出均 401 `AUTH_REQUIRED`；响应体不含 `## 结论`、列名、报告前缀 |
| `test_ac_us08_expired_session_rejected_without_renewal` | 401 `AUTH_SESSION_EXPIRED`；`expires_at` 不被续期、`revoked_at=None`；另一会话不受影响 |
| `test_ac_ev03_invalid_sample_failed_but_report_count_119` | `sample_total=120`、`report_count=119`、`accuracy=119/120`；第 61 条 `failed` 且 `feature_missing`，其余继续 |
| `test_ac_in11_full_nl_hits_retrieve_without_clarification` | `extraction_status=ok`、`missing_fields=[]`、无 clarification、trace 含 `retrieve`+`report`、报告含 `## 结论` |
| `test_ac_in13_clarification_missing_count_and_append` | 首问 5 项 → 补 1 项后剩 4 项；`process_temp_k` 不重现；`waiting_human`；`diagnosis_revision=1` |
| `test_ac_kb01_fixed_query_top5_hdf_hit_and_covered` | `coverage=covered`、`max_score≥0.35`、Top-5 含 HDF、分数降序 |
| `test_ac_kb02_same_type_cap_and_retry_keeps_threshold` | 每类命中 ≤2；`retry_used=true`、`top_k=8`；`COVERED_SCORE==0.35` 不降；覆盖判定不变 |
| `test_ac_kb06_top5_hit_rate_is_measured_not_null` | `top5_hit_rate` 为 float、`0<rate≤1`、等于 `measure_top5_hit_rate`；固定检索集落盘且恰 50 条 |
| `test_ac_dg07_confidence_0_7875_retries_once_top_k8_then_review` | 置信度 0.7875；`retry_count=1`；`top_k=8`；RT-07 `retry` 步骤存在；`waiting_human` + review |
| `test_ac_dg09_supplement_bumps_revision_keeps_old_fields` | `diagnosis_revision=2`；存在 revision=2 的 `parse_input`；`torque_nm=55` 生效且 air/process/wear 未清空 |
| `test_ac_dg17_report_twice_missing_differential_degrades_with_note` | `status=degraded`；`report_retry_count=1`；`REPORT_CHECK_FAILED`；首行缺项横幅；RT-12 仅 1 次 |
| `test_ac_ev05_regression_detection_threshold` | 候选低于基线即判定回滚，边界两侧均有断言 |
| `test_ac_ev05_rollback_restores_baseline_prompts_and_records_reason` | `rolled_back=true`；活动版本回到 `baseline-v1`；文件字节与基线一致；审计 JSONL 1 条 |
| `test_health_reports_degraded_with_embedding_reason_when_bge_unavailable` | `status=degraded`、`embedding_model=degraded`、`embedding_reason=fallback:hash-ngram-512`、`vector_index=ok` |
| `test_production_gate_blocks_missing_https_db_encryption_and_key` | `RuntimeError` 且列出 3 项缺失；不是“静默启动” |
| `test_production_gate_allows_complete_configuration` | 完整配置可正常 `create_app`，排除“永远拒绝启动”的伪实现 |

> 结论：16 条均为针对性断言，未发现空洞用例或 `assert True` 型占位。

---

## 3. 必查 2：代码修复核验（直接读代码）

| 项 | 代码事实 | 对应 AC | 判定 |
| --- | --- | --- | --- |
| 提示词回归 | `app/prompt_regression.py::run_regression` 对 baseline 与 candidate 跑同一批用例，`rolled_back = candidate_passed < baseline_passed`；回滚时用 baseline 覆盖候选文件、`library.invalidate`、写入含两侧版本/分数/原因/时间的 JSONL 审计 | AC-EV-05 | 通过 |
| 生产启动门禁 | `app/config.py::production_startup_gaps` 非 production 返回 `[]`；production 下逐项检查 HTTPS、`EDG_DB_ENCRYPTION_KEY`、DeepSeek Key，返回缺失项列表。`app/main.py:28-34` 在 `create_app` 最前调用，非空即 `logger.error` 并 `raise RuntimeError` | AC-SE-05 | 通过 |
| Top-5 命中率 | `app/evaluation.py::measure_top5_hit_rate` 从 `_retrieval_queries` 取固定 50 条 query，真实调用 `knowledge.retrieve(..., top_k=5)`，按 `fault_type` 命中计数并保留 4 位小数；`detail()` 的 `retrieval_tuning` 写入 `params{chunk_size,overlap,top_k=5}`、`top5_hit_rate`、`kb_version`、`created_at` | AC-KB-06 | **失败**：只有当前一次快照，无前后对比；无同参数重复一致性断言 |
| 向量后端降级 | `app/startup.py:19-35`：`embedding_status=fallback` → `embedding_model=degraded` 且 `embedding_reason=fallback:<embedder.name>`；`embedder is None` → `error` + `embedding_backend_unavailable` | AC-SY-03 | 通过 |

> 代码阅读只用于确认“实现是否存在/是否与 AC 冲突”；四项的通过判定均另有可执行测试支撑（§2.2）。

---

## 4. 必查 3：数据库与 KPI-04（`storage/app.db`，只读）

批次 `bch_01M5S9Q7P4VHTNTM5Z5X3PE5ZD`：

| 核验点 | 实测 | 说明 |
| --- | --- | --- |
| `batch_tasks` 汇总 | `total_rows=240`、`succeeded_rows=209`、`degraded_review_rows=30`、`failed_rows=1`、`failed_timeout_rows=0`、`cancelled_rows=0`、`status=partially_failed` | 1 行失败导致批次降为 `partially_failed`，其余 239 行完成 |
| `batch_rows` 逐行 | 240 行：`succeeded 209 / degraded_review 30 / failed 1`；第 31 行 `error_code=FEATURE_OUT_OF_RANGE`、`error_field=air_temp_k` | 失败行不生成诊断/报告 |
| `diagnoses` 逐行 `report_meta` | 239 行：`report_meta.model_name` = **deepseek-chat 238** + **rule-engine 1**；`llm_used` 前者 true、后者 false | 1 条 rule-engine 是可观测降级，不是静默模板冒充 |
| `knowledge_versions` | 仅 `kb_v1` 为 `active`，`entry_count=14`，`chunk_size=400`、`overlap=50` | 无第二个 active 版本，无并发激活 |
| KPI-04 | 239/240 = **99.58%**；严格 DeepSeek 238/240 = **99.17%** | 两种口径均 ≥99% |

**与 AC-EV-08 的夹具偏差（登记，不豁免）**：AC 要求 1 `failed` + 1 `failed_timeout` + 1 `degraded` + 1 `degraded_review`，并“取消 40 行后分母变 200”。本批次为 1 `failed` + 30 `degraded_review`，无 `failed_timeout`/`degraded`，取消 40 行的复跑未执行。KPI 门槛本身已由真实 DeepSeek 批次直接证明，故 AC-EV-08 判通过，但两处子分支列为残余风险（§9）。

---

## 5. 必查 4：KPI-01 artifact 重算

文件：`storage/eval/evb_01M5Q111XDZHNAA1YMCY2K14RR.json`（140 条 = eval 120 + edge 20）。

| 项 | 重算值 |
| --- | --- |
| `llm_used` | 140/140 = true |
| `status` | 140/140 = succeeded；超时 0 |
| `knowledge_status` | 140/140 = supported |
| 六分类准确率 | **106/120 = 88.33%** |
| 五分类准确率 | **106/110 = 96.36%** |
| 分类别 | HDF 20/20、PWF 20/20、OSF 20/20、TWF 20/20、正常 26/30、RNF 0/10 |
| 延迟（eval 120） | avg 6035.8ms、P50 6035ms、P95 6685ms、max 7530ms |
| 要素完整度 | `elements_present=8` × 120 |

> 结论：五分类过主验收门槛；六分类差额 14 条 = 正常误判 TWF 4 条 + RNF 全部 10 条（9 条判正常、1 条判未覆盖）。六分类必须随交付披露，C-011 不得用于放行其他 AC。

---

## 6. 必查 5：KPI-05 证据链自洽性

| 文件 | 内容 | 自洽性判断 |
| --- | --- | --- |
| `AC-EV-07-v2-audit.md` | AI 预审 20 行明细 + 评审表汇总 + 逐条对照 + 3 条分歧裁决 + 签字确认 | 明确 `audit.json` 的 `human_reviewers=0` 仅代表预审轮次；人工结论以双人表为准，自洽 |
| `AC-EV-07-v2-health.json` | `vector_index=missing` | 前置“真实知识未覆盖”成立 |
| `AC-EV-07-v2-raw.json` | 20/20 `knowledge_status=missing`、`primary_type=未覆盖`、置信度 0.4、报告声明“知识库未覆盖” | 样本确为未覆盖，不是 supported |
| `AC-EV-07-v2-audit.json` | `human_reviewers=0`，`rows=20`，`fabricated=0`，`note` 明示“结论不代表已满足 2 名真人评审要求” | **必须且只能解释为 AI 预审快照**，不能当作“无真人评审” |
| `AC-EV-07-v2-human-review.json` | `human_reviewers_verified=true`、`sample_count=20`、评审人 A/B、`fabricated_total=0`、`fabrication_rate=0.0`、`kpi_05_pass=true`、`meets_ac_ev_07=true`、`disagreements=3` | 与二次评审一致 |
| `AC-EV-07-v2-review-form-A.md` / `-form-B.md` | A 判定1“是”=0 条；B=3 条 | 差集 3 条 = `disagreements=3`，数量自洽 |
| 分歧裁决 | 项目负责人 P 采纳 A 的保守口径（不加确定性结论）；20 条全部保留判定记录 | 分歧有裁决、有留痕，最终 0 条确定性结论 → 捏造 0/20 |

**残余风险（不改变通过判定）**：评审人 A/B 为内部代号（小A/小B），两份签字表格式高度一致，未提供外部实名存证；这属于证据形式风险，不是逻辑矛盾。`audit.md` 已逐条解释预审快照与人工结论的关系，KPI-05 的 0/20 在 v2 包内可复算。

---

## 7. 必查 6：90 条 AC 明细（唯一清单）

> 图例：`=` 维持 V2；`↑` 未验证转通过；`↑F` 失败转通过；`↓` 通过转未验证（V3 不接受纯静态证据）；`F=` 维持失败；`P=` 维持待裁决。

### 7.0 本轮 14 条补证 AC 逐条判定

| # | AC | 优先级 | V3 结论 | 本轮直接证据 | 未覆盖子项 |
| --- | --- | --- | --- | --- | --- |
| 1 | AC-US-08 | P0 | 通过 | `test_ac_us08_...`：401 `AUTH_SESSION_EXPIRED`、不续期 | — |
| 2 | AC-IN-11 | P0 | 通过 | `test_ac_in11_...`：7 项齐全、无追问、直达报告 | 抽取卡视觉未单独截图 |
| 3 | AC-IN-13 | P0 | 通过 | `test_ac_in13_...`：5→4 项、已补项不重现 | — |
| 4 | AC-DG-07 | P0 | 通过 | `test_ac_dg07_...`：0.7875、`retry_count=1`、`top_k=8`、review | — |
| 5 | AC-DG-09 | P0 | 通过 | `test_ac_dg09_...`：revision=2、补充值生效、旧字段保留 | 报告内容与 `review_round` 未断言 |
| 6 | AC-DG-17 | P0 | 通过 | `test_ac_dg17_...`：`degraded`、重试 1 次、首行缺项、RT-12 一次 | 告警记录条数与导出未单独断言 |
| 7 | AC-KB-01 | P0 | 通过 | `test_ac_kb01_...`：covered、`max_score≥0.35`、Top-5 含 HDF | — |
| 8 | AC-KB-02 | P0 | 通过 | `test_ac_kb02_...`：每类 ≤2、retry `top_k=8`、阈值不降 | — |
| 9 | AC-KB-06 | P1 | **失败** | `measure_top5_hit_rate` 已实测 50 条并落 `retrieval_tuning` | 前后对比、同参数重复一致均缺失 |
| 10 | AC-EV-03 | P0 | 通过 | `test_ac_ev03_...`：1 条 failed、分母仍 120、其余完成 | — |
| 11 | AC-EV-05 | P1 | 通过 | `test_ac_ev05_*` ×2：自动回滚、恢复 baseline、JSONL 审计 | “重跑 92%”未单独统计 |
| 12 | AC-SY-03 | P1 | 通过 | `test_health_...`：`degraded` + `embedding_reason=fallback:...` | — |
| 13 | AC-SE-04 | P0 | 通过 | `test_ac_se04_...`：报告/导出均 401、响应体无报告 | — |
| 14 | AC-SE-05 | P1 | 通过 | `test_production_gate_*` ×2：列 3 项缺失并拒绝启动 | 单项隔离未做 |

> 14 条中 **13 通过 / 1 失败**。另有 3 条非“新用例型”补证也在本轮翻转为通过：AC-DG-11（e2e 19/20 截图）、AC-EV-07（KPI-05 v2）、AC-EV-08（240 行 DeepSeek 批次）。

### 7.1 US / SE / SY（17 条）

| AC | 优先级 | V3 结论 | V2→V3 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-US-01 | P0 | 通过 | = | `extras-auth-upload-history.json`：201/200/`me` 一致 | — |
| AC-US-02 | P0 | 通过 | = | 同上：409 `USERNAME_TAKEN`，账号数不变 | — |
| AC-US-03 | P0 | 通过 | = | `LoginPage.tsx` 密码规则 + 3 引擎弱口令截图（`hint_visible`/`submit_disabled`） | — |
| AC-US-04 | P0 | 通过 | = | 401 统一“用户名或密码错误”，不泄露账号存在性 | — |
| AC-US-05 | P0 | 通过 | = | 401 `AUTH_REQUIRED` + `App.tsx` 路由保护 + e2e 18/21 跳转截图 | — |
| AC-US-06 | P0 | 通过 | = | `extras2-edge-cases.json`：第 5 次 423、`Retry-After=300`、正确密码仍 423 | — |
| AC-US-07 | P1 | 通过 | = | `test_auth_flow`：退出后 `/auth/me` 401 | — |
| AC-US-08 | P0 | 通过 | ↑ | `test_ac_us08_...`：401 `AUTH_SESSION_EXPIRED`；`expires_at` 不续期 | — |
| AC-SE-01 | P0 | 通过 | = | `test_ac_se01` ×3 + `test_text_guard`：检测、脱敏日志、流程继续、报告无无关内容 | — |
| AC-SE-02 | P1 | **未验证** | ↓ | `.exe` → 415 `FILE_TYPE_NOT_ALLOWED`（真实 HTTP）；`batches.py::_csv_safe` 静态 | 公式注入样本未构造、导出转义无落盘证据；V2 的静态通过不计 |
| AC-SE-03 | P0 | 通过 | = | 15 词表 + `test_text_guard` 3 条 + 报告脱敏 + 命中日志 | — |
| AC-SE-04 | P0 | 通过 | ↑ | `test_ac_se04_...`：报告与导出均 401，响应体无报告内容 | — |
| AC-SE-05 | P1 | 通过 | ↑F | `test_production_gate_*` ×2：缺 3 项 → `RuntimeError`；完整配置可启动 | 三项同缺，未做单项隔离 |
| AC-SY-01 | P0 | **未验证** | ↓ | `startup.py` `llm_config=missing`、`services.ensure_llm_configured` 503（静态） | 无“缺 Key 启动 → 告警/历史可浏览/诊断提示 503”运行时证据 |
| AC-SY-02 | P0 | 通过 | = | `test_health_contract`（`X-Request-Id`）+ 日志字段实现 | 日志字段未逐条落盘抽检 |
| AC-SY-03 | P1 | 通过 | ↑F | `test_health_reports_degraded...`：`degraded` + `embedding_reason=fallback:hash-ngram-512` | — |
| AC-SY-04 | P0 | 通过 | = | `start.ps1` + `test_start_script_exists_with_port_conflict_guidance` | — |

### 7.2 IN（21 条）

| AC | 优先级 | V3 结论 | V2→V3 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-IN-01 | P0 | 通过 | = | `test_csv_upload_and_single_diagnosis` + E2E §1（文件名/行号/入口类型） | — |
| AC-IN-02 | P0 | 通过 | = | 中文表头 7/7 自动映射（真实 HTTP） | — |
| AC-IN-03 | P0 | 通过 | = | `test_mapping_preview_missing_required_is_not_valid` + 前端标红/禁提交 | — |
| AC-IN-04 | P0 | 通过 | = | 6MB → 413 `FILE_TOO_LARGE`；600 行 → 422 `CSV_ROW_LIMIT_EXCEEDED` | — |
| AC-IN-05 | P0 | **未验证** | ↓ | `uploads.py:150-151` 非 `.csv` → 415；`.exe` 真实 HTTP 证据 | 未构造 `.xlsx` 上传；`.exe` 证据已计给 AC-SE-02 |
| AC-IN-06 | P0 | 通过 | = | `test_batch_create_and_counts_conserved` + 240 行真实任务（状态守恒） | — |
| AC-IN-07 | P0 | 通过 | = | 240 行第 31 行 `failed`、`error_field=air_temp_k`，其余 239 行继续、无 clarification | 夹具偏差：AC 原文为第 37 行扭矩文本 `abc`/`error_field=torque_nm`；失败行隔离行为已直接证明，字段分支未按原文构造（OBS-11） |
| AC-IN-08 | P0 | 通过 | = | `test_batch_cancel_then_idempotent` + E2E §2 | — |
| AC-IN-09 | P0 | 通过 | = | `test_out_of_range_rejected` + 前端即时校验 | — |
| AC-IN-10 | P0 | 通过 | = | L 型 60Nm/200min → `wear_torque=12000 > 11000` → OSF | — |
| AC-IN-11 | P0 | 通过 | ↑ | `test_ac_in11_...`：7 项齐全、无追问、直达 retrieve/report | 抽取卡 UI 由前端复用同一 payload |
| AC-IN-12 | P0 | 通过 | = | `test_nl_partial_clarification_and_resume` + E2E §3 | — |
| AC-IN-13 | P0 | 通过 | ↑ | `test_ac_in13_...`：5→4 项、已补项不重现、`waiting_human` | — |
| AC-IN-14 | P0 | 通过 | = | `test_p0_intake`：`user_correct` + `revision=1` | — |
| AC-IN-15 | P0 | 通过 | = | `test_device_id_required_and_validated` 等（65 字符/`/` → 422） | — |
| AC-IN-16 | P0 | 通过 | = | 500 行接受、501 行 → 422 `CSV_ROW_LIMIT_EXCEEDED`（真实 HTTP） | — |
| AC-IN-17 | P1 | **未验证** | = | 证据包同名条目实为“row_no 越界”，与 AC 不符 | 无“删除源文件后历史仍显示文件名/行号/入口”用例 |
| AC-IN-18 | P0 | 通过 | = | `test_machine_stopped_blocked`（转速/扭矩=0 阻断） | — |
| AC-IN-19 | P0 | 通过 | = | `test_ac_in20_duplicate_rows...`：10 行相同 → 10 个独立 id | — |
| AC-IN-20 | P1 | 通过 | = | `test_mapping_scheme_crud`（保存/复用/删除/清空） | 同名覆盖/冲突提示未单测 |
| AC-IN-21 | P0 | 通过 | = | `test_ac_in21_batch_timeout_cancels_pending_rows` + JSON 产物 | — |

### 7.3 DG（24 条，全部 P0）

| AC | V3 结论 | V2→V3 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- |
| AC-DG-01 | 通过 | = | EVAL 正常 26/30 + KPI-02 8/8；确定性 0.95 规则路径 | — |
| AC-DG-02 | 通过 | = | 温差 7.2K/1250rpm → HDF；EVAL HDF 20/20 | — |
| AC-DG-03 | 通过 | = | 功率 3204W → PWF；EVAL PWF 20/20 | — |
| AC-DG-04 | 通过 | = | L 型 12000 > 11000 → OSF，TWF 不进入候选 | — |
| AC-DG-05 | 通过 | = | 210min → TWF；EVAL TWF 20/20 | — |
| AC-DG-06 | 通过 | = | OSF+HDF 主 OSF，优先级测试 | — |
| AC-DG-07 | 通过 | ↑ | `test_ac_dg07_...`：0.7875、`retry_count=1`、`top_k=8`、review | — |
| AC-DG-08 | 通过 | = | `test_review_confirm_generates_report`：确认后仅出报告 | — |
| AC-DG-09 | 通过 | ↑ | `test_ac_dg09_...`：revision=2、补充字段生效、旧字段保留 | 报告渲染与 `review_round=1` 未单独断言 |
| AC-DG-10 | 通过 | = | `test_rt11_abort_goes_aborted` + `25-aborted.png` | — |
| AC-DG-11 | 通过 | ↑ | e2e `19a/19b/19/20`：刷新后面板恢复 0.58/29:58、确认出报告 | 无网络日志断言“不重复执行节点”；E2E 文档未回写 18–21 |
| AC-DG-12 | 通过 | = | `useDiagnosisStream.ts` 重连 + 3 次失败转轮询 + `08/09` 截图 | — |
| AC-DG-13 | 通过 | = | `test_ac_dg13_*` ×3：运行中缺失/重启 missing/空种子 | — |
| AC-DG-14 | 通过 | = | `test_ac_dg23` + TTL 证据（expired + 新 id） | — |
| AC-DG-15 | 通过 | = | `test_rt17_deduplicates_active_diagnosis`（200 + deduplicated） | — |
| AC-DG-16 | 通过 | = | `test_ac_dg16_*` ×3：并发仅一次生效，失败方 `VERSION_CONFLICT` | — |
| AC-DG-17 | 通过 | ↑ | `test_ac_dg17_...`：`degraded`、`report_retry_count=1`、首行缺项、RT-12 仅 1 次 | “告警记录 1 条/可导出”未单独断言；LLM 失败分支未覆盖 |
| AC-DG-18 | 通过 | = | `test_rt08_low_confidence_first_never_retries`（`retry_count=0`） | — |
| AC-DG-19 | 通过 | = | `test_temp_inversion_is_quality_flag`（不判 HDF/正常、扣分） | — |
| AC-DG-20 | 通过 | = | `test_rt08_batch_low_confidence_goes_auto_review` | — |
| AC-DG-21 | 通过 | = | `test_ac_dg21` ×4 + `AC-DG-21-timeout.json`（无报告、SSE 终态） | — |
| AC-DG-22 | 通过 | = | `test_ac_dg22`：零请求下自动 `expired` | — |
| AC-DG-23 | 通过 | = | `test_ac_dg23`：409 `DIAGNOSIS_EXPIRED`、无报告 | — |
| AC-DG-24 | 通过 | = | `test_rt10_round_two_supplement_is_rejected` + E2E §4 | — |

### 7.4 KB / RP（13 条）

| AC | 优先级 | V3 结论 | V2→V3 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-KB-01 | P0 | 通过 | ↑ | `test_ac_kb01_...`：covered、`max_score≥0.35`、Top-5 含 HDF | — |
| AC-KB-02 | P0 | 通过 | ↑ | `test_ac_kb02_...`：同类型 ≤2、降序、RETRY 只扩 top_k | — |
| AC-KB-03 | P1 | 通过 | = | `test_ac_kb03_*` ×2：导入/激活/回滚为手动、entry_count 记录 | — |
| AC-KB-04 | P0 | 通过 | = | `test_ac_kb04_*` ×2：缺字段/缺类目拒绝、不激活 | — |
| AC-KB-05 | P0 | 通过 | = | `test_ac_dg13_deleted_index_on_restart...`：健康 degraded、`knowledge_status=missing`、未覆盖声明 | `hits=[]/max_score=0/coverage=none` 三字段未单独断言（缺失索引下为其必然结果） |
| AC-KB-06 | P1 | **失败** | F= | `measure_top5_hit_rate` 已实测 50 条；`retrieval_tuning` 落 params/rate/kb_version/created_at | `detail()` 只给当前一次快照，**无“前后对比”结构**；**无同参数重复一致性**断言 |
| AC-RP-01 | P0 | 通过 | = | KPI-02 100%（120/120 × 8 要素） | — |
| AC-RP-02 | P0 | 通过 | = | `30-evidence-drawer.png` + `test_reasoning`（引用绑定、未知引用丢弃） | — |
| AC-RP-03 | P0 | 通过 | = | 浏览器报告渲染产物 + `react-markdown` `skipHtml` + `sanitize_markdown` | 脚本不执行未做专门 XSS 用例 |
| AC-RP-04 | P0 | 通过 | = | E2E §1 导出 200 + `filename*=UTF-8''` | — |
| AC-RP-05 | P0 | **未验证** | = | `ReportPanel.tsx:54-58` 中/低置信横幅：`建议人工复核` + `置信度 0.62 · 中` | 无 0.62 首次/重试的端到端报告夹具；后端 markdown 为“中置信度（0.62）”，无 AC 字面“中等置信度（0.62），建议人工复核” |
| AC-RP-06 | P0 | 通过 | = | `report.py` 强制追加免责声明；120/120 自检 | — |
| AC-RP-07 | P0 | 通过 | = | EVAL 8/8 + `test_rt12/test_rt13`（缺项清单与 `report_retry_count`） | — |

### 7.5 HS / EV / CC（16 条）

| AC | 优先级 | V3 结论 | V2→V3 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-HS-01 | P0 | 通过 | = | 真实 HTTP：`status=succeeded&page_size=5` → `total=16`、时间倒序 | — |
| AC-HS-02 | P0 | 通过 | = | `records.py` 排序 + `test_snapshot_trace_steps...` | — |
| AC-HS-03 | P1 | 通过 | = | 批量诊断 DELETE → 409；非批量终态可删 | — |
| AC-HS-04 | P0 | 通过 | = | 他人 `diagnosis_id` → 404 `DIAGNOSIS_NOT_FOUND` | — |
| AC-HS-05 | P1 | **未验证** | = | `AC-KPI-04-batch-export.csv` 240 行：`succeeded 207 / degraded_review 32 / failed 1`；32/32 待复核摘要含“待人工复核” | 六状态缺 `degraded`、`failed_timeout`；证据自述仅 5 种 |
| AC-HS-06 | P0 | 通过 | = | `02/14/22` 截图：空态文案与清空筛选恢复 | — |
| AC-EV-01 | P0 | 通过 | = | artifact：指标表、混淆矩阵、逐样本、bad case、版本、耗时、UDI 互斥 | — |
| AC-EV-02 | P0 | 通过（C-011） | = | 五分类 96.36% ≥90%；KPI-02 100%；KPI-03 达标；超时 0 | 六分类 88.33% 必须披露 |
| AC-EV-03 | P0 | 通过 | ↑ | `test_ac_ev03_...`：第 61 条 failed、其余继续、分母 120 | — |
| AC-EV-04 | P0 | 通过 | = | eval 120：avg 6035.8 / P50 6035 / P95 6685 / max 7530 / 超时 0 | — |
| AC-EV-05 | P1 | 通过 | ↑F | `test_ac_ev05_*` ×2：低于基线回滚、恢复 baseline、JSONL 审计 | “重跑恢复 92%”由基线字节一致推出，未单独统计 |
| AC-EV-06 | P1 | 通过 | = | `27/28/29` 截图 + EVAL 契约测试 ×5 | — |
| AC-EV-07 | P0 | 通过 | ↑ | KPI-05 v2 六件套：20 未覆盖、2 评审、0 捏造、3 分歧裁决留痕 | 评审人为内部代号、两份表同工具生成（形式风险） |
| AC-EV-08 | P0 | 通过 | ↑ | 240 行真实 DeepSeek 批次：239/240=99.58%，DeepSeek 238/240=99.17% | 无 `failed_timeout`/`degraded` 行；取消 40 行复跑未执行 |
| AC-CC-01 | P0 | **待评审裁决** | P= | 7 组配置 × 6 步 = 42 张截图，`pass=true`；Chrome 155/156、Firefox 155/157、WebKit 26.6/27.2 | Edge 仅 156 单版；原生 Safari 不可得；ARCH 无 C-012 |

**90 行合计**：通过 82（P0 74 / P1 8）、未验证 6（P0 3 / P1 3）、失败 1（P0 0 / P1 1）、待裁决 1（P0 1 / P1 0）。

---

## 8. 浏览器证据时效与内容（含 e2e 18–21）

| 文件 | 内容 | 判定用途 |
| --- | --- | --- |
| `19a-dg11-review-before-refresh.png` | 修复前复核面板 | 缺陷复现留痕 |
| `19b-dg11-after-refresh-before-fix.png` | 刷新后、修复前：面板丢失 | 缺陷复现留痕 |
| `20-review-refresh-confirm-report.png` | 复核确认后生成报告 | DG-11/ DG-08 辅证 |
| `18-401-redirect-login.png` | 未授权跳转登录 | US-05/SE-04 辅证 |
| `21-export-401-redirect-login.png` | 导出未授权跳转登录 | SE-04 辅证 |
| `19-review-refresh-restored.png` | 修复后刷新恢复：置信度 0.58、剩余 29:58、证据列、放弃/补充/确认 | **DG-11 直接证据** |

- 时效：全部为本轮采集，距本次判定 <24h；本轮后端改动集中在提示词回归、生产启动门禁、评测命中率与启动降级，不触及中断快照/复核面板，故截图仍代表当前 UI 行为。
- 偏差：`docs/E2E-UI-测试记录.md` 仍停留在 1–17 号用例，未回写 18–21；属文档滞后（OBS-03），不影响 DG-11 的截图判定。
- DG-11 的“不重复执行节点/无重复报告”未以网络日志或 trace 断言，仅由“面板恢复 + 单份报告”可见结果支撑；已在该行登记缺口。

---

## 9. AC-CC-01：待评审裁决与唯一转正路径

1. **书面裁决检索**：`docs/ARCH-系统架构与API契约.md` §10.4 现存变更登记仅 **C-010、C-011**；全文检索无 **C-012**。PRD/交付说明中亦无产品方对 AC-CC-01 的书面裁决。
2. **证据现状**：7 组配置全部通过；但 AC 字面要求“Chrome、Edge、Firefox、Safari 最新两个版本”。实际 Edge 仅 156 单版本（微软无历史版本公开分发），Windows 无原生 Safari（以 WebKit 26.6/27.2 替代）。
3. **状态**：**待评审裁决**。审查员不得自行判通过，也不判失败（环境客观不可得）。
4. **唯一转正路径**：
   - 产品方出具书面裁决，明确接受“Edge 单版本 + WebKit 替代 Safari”或给出补测要求；
   - 将该裁决登记为 **ARCH §10.4 C-012**，正文引用 **AC-CC-01** 编号与适用范围；
   - 验收方在下一版判定中引用 C-012 改判；未登记 C-012 前，本项维持待裁决。
5. 若产品方不接受替代，则需在具备 Edge 第二版本与 macOS 真机 Safari 的环境补跑同一 6 步链路，并更新 `AC-CC-01-browser-smoke.json` 与截图。

---

## 10. 缺口与失败清单

### 10.1 阻塞项（P0）

| # | AC | 状态 | 缺口 | 关闭条件 |
| --- | --- | --- | --- | --- |
| B1 | AC-CC-01 | 待评审裁决 | Edge 单版本、WebKit 替代 Safari；无书面裁决 | 产品方书面裁决 + ARCH §10.4 C-012 登记 |
| B2 | AC-RP-05 | 未验证 | 无 0.62 首次/重试端到端夹具；后端文案为“中置信度（0.62）”，无“建议人工复核”；UI 横幅虽实现，但无该场景截图/测试 | 0.62 夹具 → review → 确认 → 报告顶部同时出现 0.62、等级、建议人工复核，且 `retry_count=1` |
| B3 | AC-IN-05 | 未验证 | 无 `.xlsx` 上传的真实 HTTP 证据 | 上传 `.xlsx` → 415 `FILE_TYPE_NOT_ALLOWED` + “仅支持 .csv” |
| B4 | AC-SY-01 | 未验证 | 无缺 LLM Key 的启动/历史/诊断链路证据 | 缺 Key 启动 → 告警列缺失项、历史可浏览、诊断 503 `LLM_NOT_CONFIGURED`、不崩溃 |

### 10.2 非阻塞项（P1）

| # | AC | 状态 | 缺口 | 关闭条件 |
| --- | --- | --- | --- | --- |
| N1 | AC-KB-06 | 失败 | 无参数“前后对比”结构；无同参数重复一致性断言 | `retrieval_tuning` 输出两次运行的参数+命中率对比；同参数两次结果一致 |
| N2 | AC-HS-05 | 未验证 | 导出仅 3 种状态；缺 `degraded`、`failed_timeout` | 一份导出覆盖六状态，待复核摘要含“待人工复核”，公式字符转义可见 |
| N3 | AC-IN-17 | 未验证 | 无删除源文件后的历史详情用例 | 删除源文件后详情仍显示文件名/行号/入口类型，报告可查看 |
| N4 | AC-SE-02 | 未验证 | 公式注入样本/导出转义无落盘证据 | 含 `=cmd` 的 CSV → 导出字段带 `'` 前缀；伪造扩展名 415 |

### 10.3 残余风险与观察（不单独计为失败）

| # | 事项 | 影响 | 建议 |
| --- | --- | --- | --- |
| OBS-01 | KPI-01 六分类 88.33% | 必须随交付披露；C-011 仅覆盖该门槛 | 交付说明固定披露五/六分类双数字 |
| OBS-02 | KPI-04 夹具偏差 | 无 `failed_timeout`/`degraded` 行；取消 40 行复跑未做 | 补一份含四种负样本的 240 行夹具，或书面说明等价性 |
| OBS-03 | E2E 文档滞后 | `E2E-UI-测试记录.md` 未收录 18–21 | 回写 18–21 与时间戳 |
| OBS-04 | KPI-05 证据形式 | 评审人为内部代号、同工具生成、无外部存证 | 保留两份签字原件/实名信息备查 |
| OBS-05 | 报告顶部文案 | 后端“中置信度（0.62）” vs AC“中等置信度（0.62），建议人工复核”；UI 横幅实现“建议人工复核” | 统一文案或由产品方确认 UI 文案等价 |
| OBS-06 | 1 条 rule-engine 回落 | 状态仍 `succeeded`，无 `degraded` 标记 | 在报告中显式标注模型回落（与 KPI-04 口径说明同源） |
| OBS-07 | DG-17 仅模板缺项分支 | LLM 失败回落模板仍可能 `succeeded` | 补 LLM 失败分支断言 |
| OBS-08 | AC-DG-09 报告渲染 | 未断言报告基于 revision=2、`review_round=1` | 补报告内容断言 |
| OBS-09 | AC-KB-05 检索三字段 | `hits=[]/max_score=0/coverage=none` 未单独断言 | 在 DG-13 用例追加三字段断言 |
| OBS-10 | AC-SY-02 日志抽检 | 字段实现存在，未逐条落盘核验 | 抽一份日志验证字段与脱敏 |
| OBS-11 | AC-IN-07 夹具 | 失败行为 `air_temp_k` 越界，非原文的 `torque_nm` 文本 | 补一行扭矩 `abc` 的 240 行夹具，断言 `error_field=torque_nm` |
| OBS-12 | 评审人指出的报告质量问题 | “数据质量与假设”固定写“数据完整”与 EDGE-04/07/12/19 声称参数缺失并存；候选区与结论区无视觉隔离；7 条候选的鉴别诊断不回指规则 | 不改变 KPI-05；列为后续报告可读性改进项 |

---

## 11. 重验命令

```powershell
# 1) 基线（必须 185/0/0/0）
cd e:\equipment_diag_agent\backend
python -m pytest -q --junitxml=..\storage\pytest-accept-20261026.xml

# 2) 解析 junit 汇总
python -c "import xml.etree.ElementTree as E; print(list(E.parse(r'..\storage\pytest-accept-20261026.xml').getroot())[0].attrib)"

# 3) 批次状态、report_meta、knowledge_versions（只读）
python -c "import sqlite3,json,collections; db=sqlite3.connect(r'e:\equipment_diag_agent\storage\app.db'); db.row_factory=sqlite3.Row; B='bch_01M5S9Q7P4VHTNTM5Z5X3PE5ZD'; print('rows',collections.Counter(r['status'] for r in db.execute('select status from batch_rows where batch_task_id=?',(B,)))); print('models',collections.Counter((json.loads(r['report_meta_json']) if r['report_meta_json'] else {}).get('model_name') for r in db.execute('select report_meta_json from diagnoses where batch_task_id=?',(B,)))); print('kv',[dict(r) for r in db.execute('select kb_version,status,entry_count from knowledge_versions')])"

# 4) KPI-01 重算（五/六分类、延迟、llm_used）
python -c "import json,io,math; rows=json.load(io.open(r'e:\equipment_diag_agent\storage\eval\evb_01M5Q111XDZHNAA1YMCY2K14RR.json',encoding='utf-8')); ev=[r for r in rows if r['dataset_split']=='eval']; six=sum(r['correct'] for r in ev); five=sum(r['correct'] for r in ev if r['expected_primary']!='RNF'); print('six',six,'/120',round(six/120,4),'five',five,'/110',round(five/110,4)); print('llm_used',sum(bool(r['llm_used']) for r in rows),'/',len(rows)); lat=sorted(r['latency_ms'] for r in ev); print('avg/p50/p95/max',round(sum(lat)/len(lat),1),lat[len(lat)//2],lat[math.ceil(0.95*len(lat))-1],lat[-1])"

# 5) C-012 是否存在
#    检索 docs/ARCH-系统架构与API契约.md，§10.4 应只有 C-010、C-011
```

---

## 12. 最终结论

### 12.1 裁决：【不通过】

理由（按阻塞优先级）：

1. **AC-CC-01（P0）待评审裁决**：严格口径未满足（Edge 单版本、WebKit 替代 Safari），且 ARCH §10.4 无 C-012 书面裁决；审查员不得自行放行。
2. **AC-RP-05（P0）未验证**：UI 横幅已实现“建议人工复核”，但缺 0.62 首次/重试的端到端报告证据，且后端文案与 AC 字面不一致；属 P0 证据缺口。
3. **AC-IN-05（P0）未验证**：无 `.xlsx` 上传证据；`.exe` 415 只能证明 AC-SE-02 的伪造扩展名分支。
4. **AC-SY-01（P0）未验证**：缺 LLM Key 的启动告警、历史浏览、诊断 503 全链路无运行时证据。
5. **AC-KB-06（P1）失败**：命中率已实测，但“前后对比”与“同参数重复一致”未实现/未断言。
6. 另有 3 项 P1 未验证（HS-05、IN-17、SE-02）。

### 12.2 与 V2 相比的实质进展

- P0 失败保持 **0**；V2 的 3 项 P1 失败（EV-05、SY-03、SE-05）全部转通过，且均由可执行测试直接证明。
- V2 的 13 条 P0 未验证转通过（DG-07/09/11/17、EV-03/07/08、IN-11/13、KB-01/02、SE-04、US-08）；扣除本轮 2 条静态通过降级（IN-05、SY-01）后，P0 未验证由 14 净降至 3。
- KPI-04 已由真实 DeepSeek 批次复核（238/240 严格口径、239/240 观测口径，均 ≥99%）；KPI-05 v2 前置成立且证据自洽。

### 12.3 转正条件（全部满足后可出 V4 并改判）

1. 产品方书面裁决 AC-CC-01，并登记 **ARCH §10.4 C-012**（引用 AC-CC-01）。
2. 补 AC-RP-05 的 0.62 端到端夹具与报告顶部断言（数值 + 等级 + “建议人工复核”，`retry_count=1`），并统一“中/中等”文案或书面确认 UI 文案等价。
3. 补 AC-IN-05 的 `.xlsx` 真实 HTTP 拒绝证据。
4. 补 AC-SY-01 的缺 LLM Key 启动/历史/诊断证据。
5. 补 AC-KB-06 的前后对比与重复一致性；补 AC-HS-05 六状态导出、AC-IN-17 删源文件详情、AC-SE-02 公式转义证据。
6. 关闭后重跑 185 条基线并出具新 junit，再复算 KPI-01/04/05。

> 本报告只新增 V3，未修改 V1/V2、PRD/ARCH/UIUX/HANDOFF/DB/EVAL/E2E 等任何既有文档；C-011 仅用于 KPI-01 六分类门槛的披露口径，未被扩大解释；AC-CC-01 未自行通过。
