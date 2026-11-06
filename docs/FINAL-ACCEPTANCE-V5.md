# 最终验收判定 V5（第五次冷启动重判）

| 项目 | 内容 |
| --- | --- |
| 判定角色 | 最终验收审查员（冷启动；不采信窗口自述；不沿用 V4 统计口径） |
| 权威清单 | PRD 附录 B，自行复核 **90 条（P0 78 / P1 12）** |
| 测试基线 | `storage/pytest-accept-v5.xml`：**194 collected / 0 failed / 0 error / 0 skipped / 50.69s** |
| 本轮变化 | AC-KB-06 补跨参数实测与同参数重复断言（+3 用例，净增 2）；证据文件 9 个全部在本轮重写 |
| 最终裁决 | **【通过】**（90/90 通过；P0 78/78、P1 12/12；无剩余阻塞项） |

---

## 0. 裁决摘要

### 0.1 计数（90 条，P0 78 / P1 12）

| 结果 | 合计 | P0 | P1 |
| --- | --- | --- | --- |
| 通过 | **90** | 78 | 12 |
| 未验证 | **0** | 0 | 0 |
| 失败 | **0** | 0 | 0 |
| 待评审裁决 | **0** | 0 | 0 |
| 合计 | **90** | **78** | **12** |

> 计数由脚本对 §5 全部 90 行回读校验：无重号、无缺项、无多余；AC 集合与 PRD 附录 B 完全一致（90 条，P0 78 / P1 12）。

### 0.2 V4 → V5 变化（1 项 AC + 基线）

| AC | V4 | V5 | 变化依据 |
| --- | --- | --- | --- |
| AC-KB-06 | 未验证 | **通过** | `retrieval_tuning.runs` 两组参数不同（400/50/5 与 200/20/8）、各自在临时知识库实测、`delta` 按两轮差值计算、固定集 50 条、同参数重复 `consistent=true`；落盘 `AC-KB-06-retrieval-comparison.json`（含 `repeat`、`params_changed`） |
| 其余 89 条 | 通过 | 通过 | 全量回归 194 用例全绿，关键证据文件本轮重写后内容未退化（§3） |

### 0.3 判定口径

- 通过只认可：可执行测试、真实 HTTP、浏览器产物、落盘 artifact。静态实现不算。
- C-011 仅用于 KPI-01 六分类门槛的披露；C-012 仅用于 AC-CC-01；本轮未新增或引用任何其他裁决。
- 本轮未自行豁免任何 P0 或 P1；唯一需要说明的是证据文件命名偏差（OBS-12，不影响 AC 判定）。

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
| KPI-05 捏造率 | **0/20 = 0.00%** | 0 | 通过 | 20 条未覆盖样本、2 名评审、3 条分歧裁决、`fabricated_total=0` |

**KPI-01 数据可用性**：artifact 140/140 `llm_used=true`；现网批次 238/239 报告为 `deepseek-chat`。两者一致，未被规则模板冒充。

**KPI-04 口径**：240 行中第 31 行 `FEATURE_OUT_OF_RANGE`（`air_temp_k`）在特征校验阶段失败，不生成诊断/报告，故只有 239 份 `report_meta`。239 份中 1 份 `rule-engine`（`llm_used=false`，状态 `succeeded`），属可观测回落；严格 DeepSeek 口径 238/240=99.17%，仍 ≥99%。

**KPI-05 自洽性**：`AC-EV-07-v2-human-review.json` 显示 `sample_count=20`、`knowledge_status_missing=20`、`reviewers=2`、`disagreements=3`、`fabricated_total=0`、`human_reviewers_verified=true`；`audit.json` 的 `human_reviewers=0` 仅作 AI 预审快照解释，`audit.md`、两份签字表、`raw.json` 数量与结论一致，未发现矛盾。

---

## 2. 必查 1：基线 194 全绿与新增用例真实性

```
cd backend
python -m pytest -q --junitxml=..\storage\pytest-accept-v5.xml
```

`testsuite`：`tests=194, failures=0, errors=0, skipped=0, time=50.686`。相对 V4 的 192 条：移除 1 条旧的 KB-06 用例、新增 3 条，净增 2。

| 新用例 | 具体断言 |
| --- | --- |
| `test_ac_kb06_two_runs_use_different_params_and_report_delta` | `runs` 序号 `[1,2]`；`first != second` 且三个字段均不同；`first == {400,50,5}`、`second == {200,20,8}`；每条 `sample_total==50`；`delta == run2.rate - run1.rate`（±1e-4）；`top5_hit_rate == run1.rate` |
| `test_ac_kb06_same_params_repeat_is_consistent` | `repeat.params == runs[0].params == params`；`repeat.top5_hit_rate == runs[0].top5_hit_rate`；`consistent is True`；再次调用 `run_retrieval_tuning` 后两轮命中率与 `delta` 完全一致 |
| `test_ac_kb06_tuning_readable_from_detail_and_matches_cli` | detail 可读回 `run/params/top5_hit_rate/sample_total/kb_version/created_at`；`runs[0].params.top_k==5`、`runs[1].params.top_k==8`；`measure_top5_hit_rate` 与 `runs[0]` 相差 ≤1e-4 |

> 未发现 `assert True`、仅断言 200、或把请求参数回显当结果的占位用例；新增用例均对具体数值/结构断言。

---

## 3. 必查 2：AC-KB-06 路径 A 逐项核验

### 3.1 代码实现（`backend/app/evaluation.py`）

- `TUNING_SPECS`（第 531–534 行）：run1 = `chunk_size=400, overlap=50, top_k=5`；run2 = `chunk_size=200, overlap=20, top_k=8`。
- `_measure_with_params`（第 537–590 行）：为每组参数创建**临时** storage/db，按指定 `chunk_size/overlap` 建库并校验 manifest 参数已生效，在固定检索集上以该组 `top_k` 实测，结束后删除临时目录。
- `run_retrieval_tuning`（第 593–611 行）：顺序执行两组参数 → 再以 run1 参数重跑一次 `repeat` → `delta = round(run2.rate - run1.rate, 4)` → `consistent = repeat.rate == run1.rate`。
- `_retrieval_queries`（第 481–509 行）：固定集缺失时按知识种子确定性生成并落盘，不足 50 条直接报错。

### 3.2 落盘证据与代码输出一致性

实际证据文件：`storage/evidence/AC-KB-06-retrieval-comparison.json`（990 字节，本轮重写）。

| 核验点 | 证据值 | 判定 |
| --- | --- | --- |
| 两次参数不同 | run1 `{chunk_size:400, overlap:50, top_k:5}`；run2 `{chunk_size:200, overlap:20, top_k:8}` | 通过 |
| `delta` 计算 | `1.0 - 1.0 = 0.0`，文件 `delta=0.0` | 通过 |
| 固定集 50 条 | 两轮 `sample_total=50`，`repeat.sample_total=50` | 通过 |
| 同参数重复一致 | `repeat.params == runs[0].params`、两者命中率均 `1.0`、`consistent=true` | 通过 |
| 参数变更标记 | `params_changed=true` | 通过 |
| 临时库版本 | `kb_tuning_c400_o50` / `kb_tuning_c200_o20`，`backend=hash` | 通过 |
| active 知识版本未被改动 | `storage/app.db` 中 `knowledge_versions` 仅 `kb_v1`（active，14 条） | 通过 |

> 必查指定的文件名 `AC-KB-06-param-sweep.json` 不存在；实际文件名为 `AC-KB-06-retrieval-comparison.json`，字段与代码输出逐项一致（上表）。记为 OBS-12（命名偏差，不影响 AC 行为判定）。

### 3.3 路径 B

`ARCH-系统架构与API契约.md` 全文检索无 `C-013`；§10.4 仍只有 C-010/C-011/C-012。故路径 B 不成立，本轮按路径 A 核验并判通过。

---

## 4. 必查 3：V4 已通过项回归抽检与 KPI 复算

| 抽检项 | 本轮直接证据 | 判定 |
| --- | --- | --- |
| AC-RP-05 | `AC-RP-05-report.json`：`confidence=0.62`、`confidence_level=medium`、`retry_count=1`、`confidence_line="中等置信度（0.62），建议人工复核，已人工确认"` | 未退化 |
| AC-IN-05 | `AC-IN-05-xlsx-upload.json`：`FILE_TYPE_NOT_ALLOWED` / `仅支持 .csv 文件` | 未退化 |
| AC-SY-01 | `AC-SY-01-llm-missing.json`：`health_status=degraded`、`llm_config=missing`、`llm_config_missing=EDG_DEEPSEEK_API_KEY`、history 200、诊断 503 `LLM_NOT_CONFIGURED`、`health_after_diagnosis=200` | 未退化 |
| AC-CC-01 | `screenshots/evidence/AC-CC-01-browser-smoke.json`（6907 字节）；`ARCH §10.4` C-012 仍在，范围仍限 AC-CC-01 | 未退化 |
| AC-HS-05 | 六状态 CSV 本轮重写：`succeeded/degraded/degraded_review/failed/failed_timeout/cancelled`；待复核摘要含“待人工复核”；`'=2+2` | 未退化 |
| AC-SE-02 | 四个公式值导出均带 `'` 前缀（`'=cmd`、`'+SUM(1)`、`'-1+1`、`'@SUM(1)`），`SAFE-1` 正常 | 未退化 |
| AC-IN-17 | `AC-IN-17-history-after-delete.json`：删除源文件后详情 200、`input_type=csv_single`、报告 200、历史 1 条 | 未退化 |

**KPI 复算**（与 §1 一致，脚本按 V3 口径重算）：KPI-01 106/120 与 106/110、`llm_used` 140/140、延迟 avg 6035.8 / P50 6035 / P95 6685 / max 7530、超时 0；KPI-04 209 + 30 + 1 行、239 份报告（238 deepseek-chat + 1 rule-engine）；KPI-05 20 条 / 0 捏造 / 3 分歧。均与 V4 一致，无退化。

---

## 5. 必查 4：V1~V4 与冻结文档未被改动

仓库无 `.git`（`git status` 返回 not a repository），故以文件最后写入时间与内容为准：

| 文档 | 本轮是否变化 |
| --- | --- |
| `PRD-设备故障诊断智能体-V1.0.0.md` | 否 |
| `UIUX-设备故障诊断智能体.md` | 否 |
| `DB-数据库设计文档.md` | 否 |
| `ARCH-系统架构与API契约.md` | 否（无 C-013） |
| `FINAL-ACCEPTANCE.md`（V1） | 否 |
| `FINAL-ACCEPTANCE-V2.md` | 否 |
| `FINAL-ACCEPTANCE-V3.md` | 否 |
| `FINAL-ACCEPTANCE-V4.md` | 否 |

本轮仅新增 `docs/FINAL-ACCEPTANCE-V5.md` 与 `storage/pytest-accept-v5.xml`；其余改动为测试运行重写 `storage/evidence/*` 证据文件（测试自身行为）。

附录：本轮开始前已存在 KB-06 的实现与用例改动（`backend/app/evaluation.py`、`backend/tests/contract/test_ac_kb06_reproducibility.py`）；验收只核验其结果，未在本轮修改这两处，也不属于冻结文档。

---

## 6. 90 条 AC 明细（唯一清单）

> 图例：`=` 维持 V4；`U→P` V4 未验证→通过。

### 6.1 US / SE / SY（17 条）

| AC | 优先级 | V5 | V4→V5 | 直接证据（本轮核验） | 缺口/说明 |
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
| AC-SE-02 | P1 | 通过 | = | `=cmd/+SUM(1)/-1+1/@SUM(1)` 导出均带 `'`；`.csv.exe` 415；落盘 CSV | 公式字段行同时被 `DEVICE_ID_INVALID` 拒绝，转义仍生效 |
| AC-SE-03 | P0 | 通过 | = | 15 词表 + 3 条 text_guard + 报告脱敏 + 命中日志 | — |
| AC-SE-04 | P0 | 通过 | = | 报告/导出均 401，响应体无报告内容 | — |
| AC-SE-05 | P1 | 通过 | = | 缺 HTTPS/DB 加密/Key → `RuntimeError` 列 3 项；完整配置可启动 | 三项同缺，单项隔离未做（OBS-07） |
| AC-SY-01 | P0 | 通过 | = | 缺 Key：health `llm_config=missing` + 缺失项、history 200、诊断 503 `LLM_NOT_CONFIGURED`、health 仍 200 | 历史为 0 条，仅证明端点可用 |
| AC-SY-02 | P0 | 通过 | = | `X-Request-Id` 契约 + 日志字段实现 | 日志未逐条落盘抽检（OBS-06） |
| AC-SY-03 | P1 | 通过 | = | `degraded` + `embedding_reason=fallback:hash-ngram-512` | — |
| AC-SY-04 | P0 | 通过 | = | `start.ps1` 端口冲突提示 + 测试 | — |

### 6.2 IN（21 条）

| AC | 优先级 | V5 | V4→V5 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-IN-01 | P0 | 通过 | = | CSV 单条诊断 + 文件名/行号/入口类型 | — |
| AC-IN-02 | P0 | 通过 | = | 中文表头 7/7 自动映射 | — |
| AC-IN-03 | P0 | 通过 | = | 缺必填项 → 映射无效 + 前端标红/禁提交 | — |
| AC-IN-04 | P0 | 通过 | = | 6MB → 413；600 行 → 422 | — |
| AC-IN-05 | P0 | 通过 | = | `.xlsx` 真实上传 → 415 + “仅支持 .csv”；落盘 JSON | — |
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
| AC-IN-17 | P1 | 通过 | = | 删除源文件后详情/报告/历史正常；落盘 JSON | — |
| AC-IN-18 | P0 | 通过 | = | 转速/扭矩=0 → 阻断 | — |
| AC-IN-19 | P0 | 通过 | = | 10 行相同 → 10 个独立 id | — |
| AC-IN-20 | P1 | 通过 | = | 映射方案保存/复用/删除/清空 | 同名覆盖/冲突未单测 |
| AC-IN-21 | P0 | 通过 | = | 批量超时取消待处理行 + JSON 产物 | — |

### 6.3 DG（24 条，全部 P0）

| AC | V5 | V4→V5 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- |
| AC-DG-01 | 通过 | = | EVAL 正常 26/30 + KPI-02 8/8 | — |
| AC-DG-02 | 通过 | = | 温差 7.2K/1250rpm → HDF；HDF 20/20 | — |
| AC-DG-03 | 通过 | = | 功率 3204W → PWF；PWF 20/20 | — |
| AC-DG-04 | 通过 | = | L 型 12000 → OSF，TWF 不进入候选 | — |
| AC-DG-05 | 通过 | = | 210min → TWF；TWF 20/20 | — |
| AC-DG-06 | 通过 | = | OSF+HDF 主 OSF，优先级测试 | — |
| AC-DG-07 | 通过 | = | 0.7875、`retry_count=1`、`top_k=8`、review | — |
| AC-DG-08 | 通过 | = | 确认后仅出报告 | — |
| AC-DG-09 | 通过 | = | `diagnosis_revision=2`、补充值生效、旧字段保留 | 报告渲染与 `review_round` 未断言（OBS-04） |
| AC-DG-10 | 通过 | = | 中止 → `aborted` + 截图 | — |
| AC-DG-11 | 通过 | = | e2e 19a/19b/19/20：刷新恢复、确认出报告 | 无网络日志断言“不重复节点” |
| AC-DG-12 | 通过 | = | SSE 重连 + 3 次失败转轮询 + 截图 | — |
| AC-DG-13 | 通过 | = | 运行中缺失/重启 missing/空种子 | — |
| AC-DG-14 | 通过 | = | TTL + `expired` + 新 id | — |
| AC-DG-15 | 通过 | = | 指纹去重 200 `deduplicated` | — |
| AC-DG-16 | 通过 | = | 并发仅一次生效，失败方 `VERSION_CONFLICT` | — |
| AC-DG-17 | 通过 | = | `degraded`、重试 1 次、首行缺项、RT-12 一次 | 告警记录/导出未单独断言（OBS-03） |
| AC-DG-18 | 通过 | = | 0.62 低置信首轮不重试（`retry_count=0`） | — |
| AC-DG-19 | 通过 | = | 温差倒挂 → 质量标记、不判 HDF/正常 | — |
| AC-DG-20 | 通过 | = | 批量低置信 → `auto_review` | — |
| AC-DG-21 | 通过 | = | 4 条超时用例 + 无报告 + SSE 终态 | — |
| AC-DG-22 | 通过 | = | 零请求下自动 `expired` | — |
| AC-DG-23 | 通过 | = | `DIAGNOSIS_EXPIRED` 409、无报告 | — |
| AC-DG-24 | 通过 | = | 第二轮补充被拒 + E2E §4 | — |

### 6.4 KB / RP（13 条）

| AC | 优先级 | V5 | V4→V5 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-KB-01 | P0 | 通过 | = | covered、`max_score≥0.35`、Top-5 含 HDF | — |
| AC-KB-02 | P0 | 通过 | = | 每类 ≤2、retry `top_k=8`、阈值不降 | — |
| AC-KB-03 | P1 | 通过 | = | 导入/激活/回滚手动、`entry_count` 记录 | — |
| AC-KB-04 | P0 | 通过 | = | 缺字段/缺类目拒绝、不激活 | — |
| AC-KB-05 | P0 | 通过 | = | 缺索引 → health degraded、`knowledge_status=missing`、报告声明未覆盖 | `hits=[]/max_score=0/coverage=none` 未单独断言（OBS-05） |
| AC-KB-06 | P1 | **通过** | U→P | 两组不同参数（400/50/5、200/20/8）分别建临时库实测；固定集 50；`delta=1.0-1.0=0.0`；`repeat` 同参数 `consistent=true`、`params_changed=true`；active 仍仅 `kb_v1` | 证据文件名为 `AC-KB-06-retrieval-comparison.json`（OBS-12） |
| AC-RP-01 | P0 | 通过 | = | KPI-02 100%（120/120 × 8 要素） | — |
| AC-RP-02 | P0 | 通过 | = | 证据抽屉 + 引用绑定/未知引用丢弃 | — |
| AC-RP-03 | P0 | 通过 | = | 报告渲染产物 + `skipHtml` + `sanitize_markdown` | 脚本不执行无专门 XSS 用例 |
| AC-RP-04 | P0 | 通过 | = | 导出 200 + `filename*=UTF-8''` | — |
| AC-RP-05 | P0 | 通过 | = | 0.62 → `retry_count=1` → 确认 → 报告前 16 行含三项指定文案；落盘 JSON | 文案尾部附加“，已人工确认”（确认后状态） |
| AC-RP-06 | P0 | 通过 | = | 强制免责声明 + 120/120 自检 | — |
| AC-RP-07 | P0 | 通过 | = | 8/8 要素 + 缺项清单 + `report_retry_count` | — |

### 6.5 HS / EV / CC（15 条）

| AC | 优先级 | V5 | V4→V5 | 直接证据（本轮核验） | 缺口/说明 |
| --- | --- | --- | --- | --- | --- |
| AC-HS-01 | P0 | 通过 | = | `status=succeeded&page_size=5` → total 16、时间倒序 | — |
| AC-HS-02 | P0 | 通过 | = | 记录排序 + snapshot trace | — |
| AC-HS-03 | P1 | 通过 | = | 批量 DELETE 409；非批量终态可删 | — |
| AC-HS-04 | P0 | 通过 | = | 他人 id → 404 | — |
| AC-HS-05 | P1 | 通过 | = | 一份真实导出 CSV 六状态齐全；待复核摘要；`'=2+2`；落盘 CSV/JSON | 六状态由 DB 夹具注入，非真实运行产生（OBS-01） |
| AC-HS-06 | P0 | 通过 | = | 空态/清空筛选恢复截图 | — |
| AC-EV-01 | P0 | 通过 | = | artifact：指标、混淆矩阵、逐样本、bad case、版本、耗时、UDI 互斥 | — |
| AC-EV-02 | P0 | 通过（C-011） | = | 五分类 96.36% ≥90%；KPI-02 100%；KPI-03 达标；超时 0 | 六分类 88.33% 必须披露 |
| AC-EV-03 | P0 | 通过 | = | 第 61 条 failed、其余继续、分母 120 | — |
| AC-EV-04 | P0 | 通过 | = | avg 6035.8 / P95 6685 / max 7530 / 超时 0 | — |
| AC-EV-05 | P1 | 通过 | = | 低于基线回滚、恢复 baseline、JSONL 审计 | “重跑 92%”未单独统计 |
| AC-EV-06 | P1 | 通过 | = | 评测页截图 + 5 条契约测试 | — |
| AC-EV-07 | P0 | 通过 | = | KPI-05 v2 六件套：20 未覆盖、2 评审、0 捏造、3 分歧裁决 | 评审人为内部代号，无外部实名存证（OBS-09） |
| AC-EV-08 | P0 | 通过 | = | 239/240=99.58%；DeepSeek 238/240=99.17% | 无 `failed_timeout`/`degraded` 行；取消 40 行复跑未做（OBS-08） |
| AC-CC-01 | P0 | 通过 | = | C-012 产品方批准，范围仅 AC-CC-01；7 配置 × 6 步/42 截图 | Edge 单版本、WebKit 替代 Safari（C-012 已裁决） |

**90 行合计**：通过 90（P0 78 / P1 12）、未验证 0、失败 0、待裁决 0。

---

## 7. 缺口清单与残余观察

### 7.1 阻塞缺口

无。

### 7.2 残余观察（不影响 V5 计数）

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
| OBS-12 | KB-06 证据命名 | 必查指定 `AC-KB-06-param-sweep.json` 不存在；实际落盘为 `AC-KB-06-retrieval-comparison.json`，字段与代码输出一致 |

---

## 8. 重验命令

```powershell
# 1) 基线（应为 194/0/0/0）
cd e:\equipment_diag_agent\backend
python -m pytest -q --junitxml=..\storage\pytest-accept-v5.xml

# 2) 解析 junit
python -c "import xml.etree.ElementTree as E; print(list(E.parse(r'..\storage\pytest-accept-v5.xml').getroot())[0].attrib)"

# 3) KB-06 证据（两轮参数不同 + delta + 重复一致）
python -c "import json; d=json.load(open(r'e:\equipment_diag_agent\storage\evidence\AC-KB-06-retrieval-comparison.json',encoding='utf-8')); print([r['params'] for r in d['runs']], [r['sample_total'] for r in d['runs']], d['delta'], d['consistent'], d['params_changed'], d['repeat']['params'])"

# 4) active 知识版本（应仅一个 active）
python -c "import sqlite3; db=sqlite3.connect(r'e:\equipment_diag_agent\storage\app.db'); db.row_factory=sqlite3.Row; print([dict(r) for r in db.execute('select kb_version,status,entry_count,built_at from knowledge_versions')])"

# 5) KPI-01 重算
python -c "import json,io,math; rows=json.load(io.open(r'e:\equipment_diag_agent\storage\eval\evb_01M5Q111XDZHNAA1YMCY2K14RR.json',encoding='utf-8')); ev=[r for r in rows if r['dataset_split']=='eval']; six=sum(r['correct'] for r in ev); five=sum(r['correct'] for r in ev if r['expected_primary']!='RNF'); print('six',six,'/120',round(six/120,4),'five',five,'/110',round(five/110,4)); print('llm_used',sum(bool(r['llm_used']) for r in rows),'/',len(rows)); lat=sorted(r['latency_ms'] for r in ev); print('avg/p50/p95/max',round(sum(lat)/len(lat),1),lat[len(lat)//2],lat[math.ceil(0.95*len(lat))-1],lat[-1])"

# 6) KPI-04 批次与报告口径
python -c "import sqlite3,json,collections; db=sqlite3.connect(r'e:\equipment_diag_agent\storage\app.db'); db.row_factory=sqlite3.Row; B='bch_01M5S9Q7P4VHTNTM5Z5X3PE5ZD'; print(collections.Counter(r['status'] for r in db.execute('select status from batch_rows where batch_task_id=?',(B,)))); print(collections.Counter((json.loads(r['report_meta_json']) if r['report_meta_json'] else {}).get('model_name') for r in db.execute('select report_meta_json from diagnoses where batch_task_id=?',(B,))))"

# 7) 九个证据文件
#    storage/evidence/AC-RP-05-report.json
#    storage/evidence/AC-IN-05-xlsx-upload.json
#    storage/evidence/AC-SY-01-llm-missing.json
#    storage/evidence/AC-KB-06-retrieval-comparison.json
#    storage/evidence/AC-HS-05-six-status-export.csv
#    storage/evidence/AC-HS-05-export-summary.json
#    storage/evidence/AC-IN-17-history-after-delete.json
#    storage/evidence/AC-SE-02-formula-export.csv
#    storage/evidence/AC-SE-02-formula-escape.json

# 8) C-012（AC-CC-01）与 C-013 缺失（KB-06 走路径 A）
#    检索 docs/ARCH-系统架构与API契约.md §10.4
```

---

## 9. 最终裁决

### 【通过】

- **P0：78/78 通过。** RP-05、IN-05、SY-01、CC-01 等关键项在本轮全量回归中证据重写后未退化；无 P0 失败或未验证。
- **P1：12/12 通过。** AC-KB-06 已由“未验证”转正：`runs` 两次参数确实不同（400/50/5 与 200/20/8），各自建临时库实测，`delta` 按两轮差值计算，固定集 50 条，同参数 `repeat` 一致（`consistent=true`），且 active 知识版本仍为唯一 `kb_v1`，未被调参过程改动。
- **KPI 门槛**：五分类 96.36% 过主验收；六分类 88.33% 按 C-011 披露；KPI-04 两种口径均 ≥99%；KPI-05 为 0/20。
- **裁决引用**：C-011 仅覆盖 KPI-01 六分类门槛；C-012 仅覆盖 AC-CC-01；未新增其他豁免。
- **文档约束**：V1~V4 与 PRD/ARCH/UIUX/DB 未被本轮改动（§5）。
- **残余观察**：OBS-01~12 均不构成 AC 或 KPI 阻塞，建议在后续迭代中补齐（其中 OBS-12 建议将证据文件重命名为 `AC-KB-06-param-sweep.json` 以对齐验收索引）。
