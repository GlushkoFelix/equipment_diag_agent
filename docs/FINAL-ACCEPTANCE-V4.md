# 最终验收判定 V4（第四次冷启动重判）

| 项目 | 内容 |
| --- | --- |
| 判定日期 | 2026-10-26 |
| 判定角色 | 最终验收审查员（冷启动；不采信窗口自述；不沿用 V3 统计口径） |
| 权威清单 | PRD 附录 B，自行复核 **90 条（P0 78 / P1 12）** |
| 测试基线 | `storage/pytest-accept-v4.xml`：**192 collected / 0 failed / 0 error / 0 skipped / 48.05s**（2026-10-26 14:13:28 +08:00 实跑） |
| 本轮新增 | 7 条契约用例 + 9 个落盘证据文件（7 个 AC）；`ARCH §10.4 C-012` 已登记 |
| 最终裁决 | **【有条件通过】**（78/78 P0 通过；唯一条件为 P1 的 AC-KB-06 参数变更场景未实测） |

---

## 0. 裁决摘要

### 0.1 计数（90 条，P0 78 / P1 12）

| 结果 | 合计 | P0 | P1 |
| --- | --- | --- | --- |
| 通过 | **89** | 78 | 11 |
| 未验证 | **1** | 0 | 1 |
| 失败 | **0** | 0 | 0 |
| 待评审裁决 | **0** | 0 | 0 |
| 合计 | **90** | **78** | **12** |

> 计数由脚本对 §5 全部 90 行回读校验：无重号、无缺项；AC 集合与 PRD 附录 B 完全一致（90 条，P0 78 / P1 12）。

### 0.2 V3 → V4 变化（8 项）

| AC | V3 | V4 | 变化依据 |
| --- | --- | --- | --- |
| AC-RP-05 | 未验证 | **通过** | 0.62 夹具 → `retry_count=1` → 确认 → 报告首 16 行含“0.62 / 中等置信度 / 建议人工复核”；落盘 `AC-RP-05-report.json` |
| AC-IN-05 | 未验证 | **通过** | `.xlsx` 真实上传 → 415 `FILE_TYPE_NOT_ALLOWED` + “仅支持 .csv”；落盘 `AC-IN-05-xlsx-upload.json` |
| AC-SY-01 | 未验证 | **通过** | 缺 Key 启动 → `/health` 列 `EDG_DEEPSEEK_API_KEY`、历史 200、诊断 503 `LLM_NOT_CONFIGURED`、随后 health 仍 200 |
| AC-HS-05 | 未验证 | **通过** | 一份真实导出 CSV 覆盖六状态；`degraded_review` 摘要含“待人工复核”；`cancelled` 的 `=2+2` 导出为 `'=2+2` |
| AC-IN-17 | 未验证 | **通过** | 删除源文件后详情仍显示 `in17.csv`/`row_no=1`/`csv_single`，报告 200、历史 1 条 |
| AC-SE-02 | 未验证 | **通过** | `=cmd/+SUM(1)/-1+1/@SUM(1)` 导出均带 `'` 前缀；伪造扩展名 415；落盘 CSV |
| AC-CC-01 | 待评审裁决 | **通过** | `ARCH §10.4 C-012` 已登记，产品方 2026-10-26 批准，适用范围仅 AC-CC-01；V4 引用后生效 |
| AC-KB-06 | 失败 | **未验证** | 已补 `runs[1,2]/delta/consistent` 与同参数重复一致断言；但两次运行参数完全相同，AC 要求的“修改 chunk_size/overlap/Top-K 后重跑 + 参数前后对比”未实测 |

### 0.3 判定口径

- 通过只认可：可执行测试、真实 HTTP、浏览器产物、落盘 artifact。静态实现不算；V3 的 82 条通过项在 V4 复审中未发现证据退化。
- C-011 仅用于 KPI-01 六分类门槛的披露，不外扩到其他 AC；C-012 仅用于 AC-CC-01。
- 本轮未自行豁免任何 P0；唯一未验证项为 P1。

---

## 1. KPI 表（复算，口径同 V3 §1）

| KPI | 本轮复算值 | 门槛 | 判定 | 证据 |
| --- | --- | --- | --- | --- |
| KPI-01 五分类（主验收） | **96.36%（106/110）** | ≥90% | 通过（C-011） | artifact 逐条重算；HDF/PWF/OSF/TWF 各 20/20、正常 26/30 |
| KPI-01 六分类（必须同时披露） | **88.33%（106/120）** | ≥90% | 未达门槛，按 C-011 披露、不阻塞 | RNF 0/10、正常 4 条误判 TWF |
| KPI-02 报告 8 要素 | **100%（120/120，960/960）** | ≥95% | 通过 | `elements_present=8` × 120 |
| KPI-03 延迟 | avg **6035.8ms** / P50 6035 / P95 **6685ms** / max **7530ms** | avg 与 P95 ≤10s；max ≤15s | 通过 | eval 120 条成功样本 |
| 超时率 | **0/120 = 0.00%** | ≤1% | 通过 | artifact 全 succeeded |
| KPI-04 批量成功率 | **239/240 = 99.58%**；严格 DeepSeek **238/240 = 99.17%** | ≥99% | 通过 | 209 succeeded + 30 degraded_review；1 failed 排除；239 份报告 = 238 deepseek-chat + 1 rule-engine |
| KPI-05 捏造率 | **0/20 = 0.00%** | 0 | 通过 | v2 双人评审 + 3 条分歧裁决；详见 §4 |

**KPI-01 数据可用性**：artifact 140/140 `llm_used=true`；现网批次 238/239 报告为 `deepseek-chat`。两者一致，未被规则模板冒充。

**KPI-04 口径**：240 行中第 31 行 `FEATURE_OUT_OF_RANGE`（`air_temp_k`）在特征校验阶段失败，不生成诊断/报告，故只有 239 份 `report_meta`。239 份中 1 份 `rule-engine`（`llm_used=false`，状态 `succeeded`），属可观测回落；严格 DeepSeek 口径 238/240=99.17%，仍 ≥99%。

**KPI-05 自洽性**：`AC-EV-07-v2-audit.json` 的 `human_reviewers=0` 只能解释为 **AI 预审快照**（`note` 明示不代表满足 2 名真人评审）；10-26 人工评审包为 `human_reviewers_verified=true`、2 名评审人、20 条、`fabricated_total=0`、3 条分歧由 P 裁决采纳 A 的保守口径。`audit.md`、两份签字表、`raw.json`、`health.json` 数量与结论一致，未发现矛盾。

---

## 2. 必查 1：基线 192 全绿与新增用例真实性

```
cd backend
python -m pytest -q --junitxml=..\storage\pytest-accept-v4.xml
```

`testsuite`：`tests=192, failures=0, errors=0, skipped=0, time=48.049, timestamp=2026-10-26T14:13:28.835177+08:00`。相对 185 基线新增 7 条，逐条阅读源码，均为具体值断言：

| 新用例 | 具体断言 |
| --- | --- |
| `test_ac_rp05_confidence_062_report_has_medium_and_review_hint` | `retry_count==1`、`confidence==0.62`、确认后 `succeeded`；markdown 含 `0.62`/`中等置信度`/`建议人工复核`，且以“中等置信度（0.62），建议人工复核”开头；报告前 16 行同时含三项 |
| `test_ac_in05_xlsx_upload_rejected_415` | `设备数据.xlsx` → 415；`code==FILE_TYPE_NOT_ALLOWED`；message 含“仅支持 .csv” |
| `test_ac_sy01_missing_llm_key_health_history_and_503` | health 200/degraded、`llm_config==missing`、缺失项含 `EDG_DEEPSEEK_API_KEY`；history 200；诊断 503 `LLM_NOT_CONFIGURED`；再次 health 200 |
| `test_ac_kb06_two_runs_comparison_and_determinism` | `runs==[1,2]`、两次 params/rate 相同、`delta==0.0`、`consistent is True`；重复 GET 结果完全一致；固定集 50 条；`measure_top5_hit_rate` 等于报告值 |
| `test_ac_hs05_export_covers_six_statuses_and_escapes_formula` | 导出 CSV 的 status 序列等于六状态；`degraded_review` 摘要含“待人工复核”；`cancelled` 的 `=2+2` 变成 `'=2+2` |
| `test_ac_in17_history_detail_survives_source_file_deletion` | 删除 `stored_path` 后详情 200、`file_name==in17.csv`、`row_no==1`、`input_type==csv_single`；报告 200；历史 `total==1` |
| `test_ac_se02_formula_fields_escaped_in_export` | 4 个公式字段导出均以 `'` 开头；`SAFE-1` 不受影响；`.csv.exe` → 415 |

> 未发现 `assert True`、仅断言 200、或把请求参数回显当结果的占位用例。

---

## 3. 必查 2–6：V3 八个缺口的逐项闭包

| # | AC | V3 缺口 | 本轮直接证据 | V4 判定 |
| --- | --- | --- | --- | --- |
| 1 | AC-RP-05 | 无 0.62 端到端夹具；后端文案不含“建议人工复核” | `report.py:38-48`：medium/low 追加 `，建议人工复核`，medium 名为“中等”；`test_ac_rp05_...` 走完整 create→review→confirm→report；落盘 `confidence_line="中等置信度（0.62），建议人工复核，已人工确认"` | **通过** |
| 2 | AC-IN-05 | 无 `.xlsx` 上传证据 | `test_ac_in05_...` 以 `.xlsx` 文件名 + xlsx MIME + PK 头真实上传；415 + 指定文案；落盘 `AC-IN-05-xlsx-upload.json` | **通过** |
| 3 | AC-SY-01 | 无缺 Key 运行时链路 | `startup.py:32-45` 在 `deepseek` 且 Key 为空时写 `llm_config=missing` + `llm_config_missing` 并告警；`test_ac_sy01_...` 验证 health/history/503/存活；落盘 JSON | **通过** |
| 4 | AC-KB-06 | 无前后对比结构；无同参数重复断言 | `evaluation.py:571-596` 连续两次 `measure_top5_hit_rate`，输出 `runs/top5_hit_rate/delta/consistent`；测试断言两次完全一致 | **未验证**（见下） |
| 5 | AC-HS-05 | 导出仅 3 状态 | 真实上传+批量后，以夹具注入六状态，再走真实导出：CSV 六状态齐全、待复核摘要、公式转义；落盘 CSV/JSON | **通过** |
| 6 | AC-IN-17 | 无删源文件用例 | `test_ac_in17_...` 删除 `stored_path` 后详情/报告/历史均正常；落盘 JSON | **通过** |
| 7 | AC-SE-02 | 公式转义无落盘证据 | `test_ac_se02_...` 用 4 个公式值构造真实 CSV，导出全部带 `'` 前缀；`.csv.exe` 415；落盘 CSV/JSON | **通过** |
| 8 | AC-CC-01 | 无书面裁决/C-012 | `ARCH §10.4` 新增 C-012（2026-10-26，产品方批准），适用范围仅 AC-CC-01；V4 引用 | **通过** |

### 3.1 AC-KB-06 的保留意见（唯一条件）

AC 原文：“修改 chunk_size、overlap、Top-K 后重跑 → 报告记录参数组合、Top-5 命中率与前后对比；同参数重复运行结果一致。”

已证明：固定 50 条检索集、参数组合与实测命中率落盘、连续两次结果一致（`delta=0`、`consistent=true`）、重复 GET 完全一致。

未证明：两次 `runs` 的参数**完全相同**（均为 `chunk_size=400, overlap=50, top_k=5`），`params` 直接取自 active 知识版本 manifest，没有“修改 chunk_size/overlap/Top-K 后重跑”的动作，也没有跨参数的前后对比。当前 `delta` 恒为 0，证明的是**重复性**，不是**参数敏感性**。

因此 AC-KB-06 不能判通过；按“实现存在但缺少针对性证据”归为 **未验证（P1）**，不判失败（对比结构与重复一致性已真实落地）。

---

## 4. AC-CC-01：C-012 引用与生效

`docs/ARCH-系统架构与API契约.md` §10.4 第 3826 行：

> `C-012 | 2026-10-26 | AC-CC-01 浏览器/版本覆盖裁决：接受“Edge 单版本 + WebKit 替代 Safari”的客观替代方案……适用范围仅限 AC-CC-01，不外扩到其他 AC 或 KPI | 验收口径 | 产品/测试/交付 | 产品方已批准（2026-10-26）；随 V4 验收引用生效`

§10.4 C-012 明细进一步限定：仅引用 AC-CC-01；不构成对 PRD 附录 B 的永久修改；具备 Edge 次新版本或 macOS 原生 Safari 时仍建议补测；未引用前维持待裁决。

V4 在本节明确引用 C-012，故 AC-CC-01 由“待评审裁决”改判 **通过**。证据仍为 7 组配置（Chrome 156/155、Edge 156、Firefox 157/155、WebKit 27.2/26.6）× 6 步、42 张截图、`AC-CC-01-browser-smoke.json`；不将 C-012 外扩到任何其他 AC 或 KPI。

---

## 5. 90 条 AC 明细（唯一清单）

> 图例：`=` 维持 V3；`↑` V3 未验证→通过；`↑P` V3 待裁决→通过；`F→U` V3 失败→未验证。

### 5.1 US / SE / SY（17 条）

| AC | 优先级 | V4 | V3→V4 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-US-01 | P0 | 通过 | = | 注册 201、登录 200、`/me` 一致 | — |
| AC-US-02 | P0 | 通过 | = | 重复用户名 409 `USERNAME_TAKEN`，账号数不变 | — |
| AC-US-03 | P0 | 通过 | = | 密码规则 + Chrome/Edge/Firefox 弱口令截图（提示可见、提交禁用） | — |
| AC-US-04 | P0 | 通过 | = | 401 统一“用户名或密码错误”，不泄露账号存在性 | — |
| AC-US-05 | P0 | 通过 | = | 401 `AUTH_REQUIRED` + 路由保护 + e2e 18/21 跳转 | — |
| AC-US-06 | P0 | 通过 | = | 第 5 次失败 423、`Retry-After=300`、正确密码仍 423 | — |
| AC-US-07 | P1 | 通过 | = | 退出后 `/auth/me` 401 | — |
| AC-US-08 | P0 | 通过 | = | 401 `AUTH_SESSION_EXPIRED`，`expires_at` 不续期 | — |
| AC-SE-01 | P0 | 通过 | = | 注入检测/脱敏日志/流程继续/报告无无关内容（3 用例） | — |
| AC-SE-02 | P1 | 通过 | ↑ | `=cmd/+SUM(1)/-1+1/@SUM(1)` 导出均带 `'`；`.csv.exe` 415；落盘 CSV | 公式字段行同时被 `DEVICE_ID_INVALID` 拒绝，转义仍生效 |
| AC-SE-03 | P0 | 通过 | = | 15 词表 + 3 条 text_guard + 报告脱敏 + 命中日志 | — |
| AC-SE-04 | P0 | 通过 | = | 报告/导出均 401，响应体无报告内容 | — |
| AC-SE-05 | P1 | 通过 | = | 缺 HTTPS/DB 加密/Key → `RuntimeError` 列 3 项；完整配置可启动 | 三项同缺，单项隔离未做 |
| AC-SY-01 | P0 | 通过 | ↑ | 缺 Key：health `llm_config=missing` + 缺失项、history 200、诊断 503 `LLM_NOT_CONFIGURED`、health 仍 200 | 历史为 0 条，仅证明端点可用 |
| AC-SY-02 | P0 | 通过 | = | `X-Request-Id` 契约 + 日志字段实现 | 日志未逐条落盘抽检 |
| AC-SY-03 | P1 | 通过 | = | `degraded` + `embedding_reason=fallback:hash-ngram-512` | — |
| AC-SY-04 | P0 | 通过 | = | `start.ps1` 端口冲突提示 + 测试 | — |

### 5.2 IN（21 条）

| AC | 优先级 | V4 | V3→V4 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-IN-01 | P0 | 通过 | = | CSV 单条诊断 + 文件名/行号/入口类型 | — |
| AC-IN-02 | P0 | 通过 | = | 中文表头 7/7 自动映射 | — |
| AC-IN-03 | P0 | 通过 | = | 缺必填项 → 映射无效 + 前端标红/禁提交 | — |
| AC-IN-04 | P0 | 通过 | = | 6MB → 413；600 行 → 422 | — |
| AC-IN-05 | P0 | 通过 | ↑ | `.xlsx` 真实上传 → 415 + “仅支持 .csv”；落盘 JSON | — |
| AC-IN-06 | P0 | 通过 | = | 批量计数守恒 + 240 行真实任务 | 30 条 degraded_review，非 AC 原文的 1 条 |
| AC-IN-07 | P0 | 通过 | = | 第 31 行 failed（`air_temp_k` 越界），其余 239 行继续、无 clarification | 夹具字段与 AC 原文 `torque_nm` 不同（OBS-02） |
| AC-IN-08 | P0 | 通过 | = | 取消 + 重复取消幂等 | — |
| AC-IN-09 | P0 | 通过 | = | 越界值 422 + 前端即时校验 | — |
| AC-IN-10 | P0 | 通过 | = | L 型 60Nm/200min → `wear_torque=12000` → OSF | — |
| AC-IN-11 | P0 | 通过 | = | 7 项齐全、无追问、直达 retrieve/report | — |
| AC-IN-12 | P0 | 通过 | = | 部分抽取 → clarification → 恢复 | — |
| AC-IN-13 | P0 | 通过 | = | 5→4 项、已补项不重现、`waiting_human` | — |
| AC-IN-14 | P0 | 通过 | = | `user_correct` + `revision=1` | — |
| AC-IN-15 | P0 | 通过 | = | 设备号 65 字符/含 `/` → 422 | — |
| AC-IN-16 | P0 | 通过 | = | 500 行接受、501 行 → 422 | — |
| AC-IN-17 | P1 | 通过 | ↑ | 删除源文件后详情/报告/历史正常；落盘 JSON | — |
| AC-IN-18 | P0 | 通过 | = | 转速/扭矩=0 → 阻断 | — |
| AC-IN-19 | P0 | 通过 | = | 10 行相同 → 10 个独立 id | — |
| AC-IN-20 | P1 | 通过 | = | 映射方案保存/复用/删除/清空 | 同名覆盖/冲突未单测 |
| AC-IN-21 | P0 | 通过 | = | 批量超时取消待处理行 + JSON 产物 | — |

### 5.3 DG（24 条，全部 P0）

| AC | V4 | V3→V4 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- |
| AC-DG-01 | 通过 | = | EVAL 正常 26/30 + KPI-02 8/8 | — |
| AC-DG-02 | 通过 | = | 温差 7.2K/1250rpm → HDF；HDF 20/20 | — |
| AC-DG-03 | 通过 | = | 功率 3204W → PWF；PWF 20/20 | — |
| AC-DG-04 | 通过 | = | L 型 12000 → OSF，TWF 不进入候选 | — |
| AC-DG-05 | 通过 | = | 210min → TWF；TWF 20/20 | — |
| AC-DG-06 | 通过 | = | OSF+HDF 主 OSF，优先级测试 | — |
| AC-DG-07 | 通过 | = | 0.7875、`retry_count=1`、`top_k=8`、review | — |
| AC-DG-08 | 通过 | = | 确认后仅出报告 | — |
| AC-DG-09 | 通过 | = | `diagnosis_revision=2`、补充值生效、旧字段保留 | 报告渲染与 `review_round` 未断言 |
| AC-DG-10 | 通过 | = | 中止 → `aborted` + 截图 | — |
| AC-DG-11 | 通过 | = | e2e 19a/19b/19/20：刷新恢复、确认出报告 | 无网络日志断言“不重复节点” |
| AC-DG-12 | 通过 | = | SSE 重连 + 3 次失败转轮询 + 截图 | — |
| AC-DG-13 | 通过 | = | 运行中缺失/重启 missing/空种子 | — |
| AC-DG-14 | 通过 | = | TTL + `expired` + 新 id | — |
| AC-DG-15 | 通过 | = | 指纹去重 200 `deduplicated` | — |
| AC-DG-16 | 通过 | = | 并发仅一次生效，失败方 `VERSION_CONFLICT` | — |
| AC-DG-17 | 通过 | = | `degraded`、重试 1 次、首行缺项、RT-12 一次 | 告警记录/导出未单独断言 |
| AC-DG-18 | 通过 | = | 0.62 低置信首轮不重试（`retry_count=0`） | — |
| AC-DG-19 | 通过 | = | 温差倒挂 → 质量标记、不判 HDF/正常 | — |
| AC-DG-20 | 通过 | = | 批量低置信 → `auto_review` | — |
| AC-DG-21 | 通过 | = | 4 条超时用例 + 无报告 + SSE 终态 | — |
| AC-DG-22 | 通过 | = | 零请求下自动 `expired` | — |
| AC-DG-23 | 通过 | = | `DIAGNOSIS_EXPIRED` 409、无报告 | — |
| AC-DG-24 | 通过 | = | 第二轮补充被拒 + E2E §4 | — |

### 5.4 KB / RP（13 条）

| AC | 优先级 | V4 | V3→V4 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-KB-01 | P0 | 通过 | = | covered、`max_score≥0.35`、Top-5 含 HDF | — |
| AC-KB-02 | P0 | 通过 | = | 每类 ≤2、retry `top_k=8`、阈值不降 | — |
| AC-KB-03 | P1 | 通过 | = | 导入/激活/回滚手动、`entry_count` 记录 | — |
| AC-KB-04 | P0 | 通过 | = | 缺字段/缺类目拒绝、不激活 | — |
| AC-KB-05 | P0 | 通过 | = | 缺索引 → health degraded、`knowledge_status=missing`、报告声明未覆盖 | `hits=[]/max_score=0/coverage=none` 未单独断言 |
| AC-KB-06 | P1 | **未验证** | F→U | `evaluation.py:571-596` 两次实测 + `runs/delta/consistent`；测试断言同参数完全一致 | 两次 params 相同，未做“修改 chunk_size/overlap/Top-K 后重跑”的跨参数对比（§3.1） |
| AC-RP-01 | P0 | 通过 | = | KPI-02 100%（120/120 × 8 要素） | — |
| AC-RP-02 | P0 | 通过 | = | 证据抽屉 + 引用绑定/未知引用丢弃 | — |
| AC-RP-03 | P0 | 通过 | = | 报告渲染产物 + `skipHtml` + `sanitize_markdown` | 脚本不执行无专门 XSS 用例 |
| AC-RP-04 | P0 | 通过 | = | 导出 200 + `filename*=UTF-8''` | — |
| AC-RP-05 | P0 | 通过 | ↑ | 0.62 → `retry_count=1` → 确认 → 报告前 16 行含三项指定文案；落盘 JSON | 文案尾部附加“，已人工确认”（确认后状态） |
| AC-RP-06 | P0 | 通过 | = | 强制免责声明 + 120/120 自检 | — |
| AC-RP-07 | P0 | 通过 | = | 8/8 要素 + 缺项清单 + `report_retry_count` | — |

### 5.5 HS / EV / CC（15 条）

| AC | 优先级 | V4 | V3→V4 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-HS-01 | P0 | 通过 | = | `status=succeeded&page_size=5` → total 16、时间倒序 | — |
| AC-HS-02 | P0 | 通过 | = | 记录排序 + snapshot trace | — |
| AC-HS-03 | P1 | 通过 | = | 批量 DELETE 409；非批量终态可删 | — |
| AC-HS-04 | P0 | 通过 | = | 他人 id → 404 | — |
| AC-HS-05 | P1 | 通过 | ↑ | 一份真实导出 CSV 六状态齐全；待复核摘要；`'=2+2`；落盘 CSV/JSON | 六状态由 DB 夹具注入，非真实运行产生 |
| AC-HS-06 | P0 | 通过 | = | 空态/清空筛选恢复截图 | — |
| AC-EV-01 | P0 | 通过 | = | artifact：指标、混淆矩阵、逐样本、bad case、版本、耗时、UDI 互斥 | — |
| AC-EV-02 | P0 | 通过（C-011） | = | 五分类 96.36% ≥90%；KPI-02 100%；KPI-03 达标；超时 0 | 六分类 88.33% 必须披露 |
| AC-EV-03 | P0 | 通过 | = | 第 61 条 failed、其余继续、分母 120 | — |
| AC-EV-04 | P0 | 通过 | = | avg 6035.8 / P95 6685 / max 7530 / 超时 0 | — |
| AC-EV-05 | P1 | 通过 | = | 低于基线回滚、恢复 baseline、JSONL 审计 | “重跑 92%”未单独统计 |
| AC-EV-06 | P1 | 通过 | = | 评测页截图 + 5 条契约测试 | — |
| AC-EV-07 | P0 | 通过 | = | KPI-05 v2 六件套：20 未覆盖、2 评审、0 捏造、3 分歧裁决 | 评审人为内部代号，无外部实名存证 |
| AC-EV-08 | P0 | 通过 | = | 239/240=99.58%；DeepSeek 238/240=99.17% | 无 `failed_timeout`/`degraded` 行；取消 40 行复跑未做 |
| AC-CC-01 | P0 | 通过 | ↑P | C-012 产品方批准，范围仅 AC-CC-01；7 配置 × 6 步/42 截图 | Edge 单版本、WebKit 替代 Safari（C-012 已裁决） |

**90 行合计**：通过 89（P0 78 / P1 11）、未验证 1（P0 0 / P1 1）、失败 0、待裁决 0。

---

## 6. 缺口清单（V4）

### 6.1 唯一未验证项

| # | AC | 优先级 | 缺口 | 关闭条件 |
| --- | --- | --- | --- | --- |
| 1 | AC-KB-06 | P1 | `runs[1]/runs[2]` 参数完全相同，未执行“修改 chunk_size/overlap/Top-K 后重跑”，无跨参数前后对比 | 构造两组参数（如 400/50/5 与 200/20/8）各跑一次，报告给出两次 params、Top-5、delta 与一致/不一致判定；或产品方书面确认“同参数两次对比”即为 AC 本意（后者属裁决，不能由审查员自行豁免） |

### 6.2 残余观察（不影响 V4 计数）

| # | 事项 | 说明 |
| --- | --- | --- |
| OBS-01 | AC-HS-05 状态来源 | 六状态由测试直接 UPDATE `batch_rows` 注入，导出本身真实；未证明批量运行能自然产生 `degraded`/`failed_timeout` |
| OBS-02 | AC-IN-07 夹具 | 失败行字段为 `air_temp_k`，AC 原文为 `torque_nm` 文本 |
| OBS-03 | AC-DG-17 分支 | 仅模板缺项分支；LLM 失败回落模板未断言 |
| OBS-04 | AC-DG-09 | 报告内容与 `review_round=1` 未单独断言 |
| OBS-05 | AC-KB-05 | 检索三字段未单独断言 |
| OBS-06 | AC-SY-02 | 日志字段未逐条落盘抽检 |
| OBS-07 | AC-SE-05 | 三项同缺，未做单项隔离 |
| OBS-08 | KPI-04 夹具 | 无 `failed_timeout`/`degraded` 行；取消 40 行复跑未执行 |
| OBS-09 | KPI-05 形式 | 评审人为内部代号（小A/小B），两份表格式一致，无外部实名存证 |
| OBS-10 | 1 条 rule-engine 回落 | 状态仍 `succeeded`，未标 `degraded`；报告可观测 `model_name` |
| OBS-11 | E2E 文档 | `E2E-UI-测试记录.md` 仍未回写 18–21，属文档滞后 |

---

## 7. 重验命令

```powershell
# 1) 基线（应为 192/0/0/0）
cd e:\equipment_diag_agent\backend
python -m pytest -q --junitxml=..\storage\pytest-accept-v4.xml

# 2) 解析 junit
python -c "import xml.etree.ElementTree as E; print(list(E.parse(r'..\storage\pytest-accept-v4.xml').getroot())[0].attrib)"

# 3) KPI-04 批次与知识版本（只读）
python -c "import sqlite3,json,collections; db=sqlite3.connect(r'e:\equipment_diag_agent\storage\app.db'); db.row_factory=sqlite3.Row; B='bch_01M5S9Q7P4VHTNTM5Z5X3PE5ZD'; print(collections.Counter(r['status'] for r in db.execute('select status from batch_rows where batch_task_id=?',(B,)))); print(collections.Counter((json.loads(r['report_meta_json']) if r['report_meta_json'] else {}).get('model_name') for r in db.execute('select report_meta_json from diagnoses where batch_task_id=?',(B,)))); print([dict(r) for r in db.execute('select kb_version,status,entry_count from knowledge_versions')])"

# 4) KPI-01 重算
python -c "import json,io,math; rows=json.load(io.open(r'e:\equipment_diag_agent\storage\eval\evb_01M5Q111XDZHNAA1YMCY2K14RR.json',encoding='utf-8')); ev=[r for r in rows if r['dataset_split']=='eval']; six=sum(r['correct'] for r in ev); five=sum(r['correct'] for r in ev if r['expected_primary']!='RNF'); print('six',six,'/120',round(six/120,4),'five',five,'/110',round(five/110,4)); print('llm_used',sum(bool(r['llm_used']) for r in rows),'/',len(rows)); lat=sorted(r['latency_ms'] for r in ev); print('avg/p50/p95/max',round(sum(lat)/len(lat),1),lat[len(lat)//2],lat[math.ceil(0.95*len(lat))-1],lat[-1])"

# 5) 七个缺口证据落盘文件（7 个 AC / 9 个文件）
#    storage/evidence/AC-RP-05-report.json
#    storage/evidence/AC-IN-05-xlsx-upload.json
#    storage/evidence/AC-SY-01-llm-missing.json
#    storage/evidence/AC-KB-06-retrieval-comparison.json
#    storage/evidence/AC-HS-05-six-status-export.csv
#    storage/evidence/AC-HS-05-export-summary.json
#    storage/evidence/AC-IN-17-history-after-delete.json
#    storage/evidence/AC-SE-02-formula-export.csv
#    storage/evidence/AC-SE-02-formula-escape.json

# 6) C-012 登记
#    检索 docs/ARCH-系统架构与API契约.md §10.4，应存在 C-012 且“适用范围仅限 AC-CC-01”
```

---

## 8. 最终裁决

### 【有条件通过】

- **P0：78/78 通过。** V3 的 3 项 P0 未验证（AC-RP-05、IN-05、SY-01）与 1 项 P0 待裁决（AC-CC-01）均已用直接证据关闭；无 P0 失败。
- **P1：11/12 通过，1 项未验证（AC-KB-06）。** 该项已从 V3 的“失败”改善为“未验证”：命中率、固定 50 条集、两次运行结构、同参数重复一致性均已落地；仍缺“修改 chunk_size/overlap/Top-K 后重跑”的跨参数对比。
- **唯一条件**：按 AC-KB-06 原文补一次参数变更后的对比（或由产品方书面确认同参数两次对比即满足本 AC，并登记为裁决；审查员不自行豁免）。
- KPI 门槛：五分类 96.36% 过主验收；六分类 88.33% 必须披露；KPI-04 两种口径均 ≥99%；KPI-05 为 0/20。
- C-011 未被外扩；C-012 仅用于 AC-CC-01；未修改 V1~V3 与任何冻结文档。

> 若验收方只要求 P0 全绿，本版即可判“通过”；本报告按“全部 90 条均须直接证明”的严格口径，保留 AC-KB-06 为唯一条件。
