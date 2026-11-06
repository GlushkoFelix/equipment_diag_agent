# 最终验收判定（冷启动）

| 项目 | 内容 |
| --- | --- |
| 判定角色 | 最终验收审查员（冷启动，不采信窗口自述） |
| 判定依据 | PRD V3.0.0 附录 B、ARCH V1.2.0、UIUX V1.2.0、HANDOFF V1.2.2、DB V1.1.0、`docs/EVAL-评测报告.md`、`docs/E2E-UI-测试记录.md`、`backend/tests` 实测结果、`screenshots/` |
| 最终裁决 | **【不通过】** |

## 0. 冷启动证据基线

1. 后端实测：`cd backend && python -m pytest -q` 退出码 0，收集并通过 **137** 条；分文件数量：contract（batch 6、batch_reconcile 1、chat 10、db 6、diagnosis 12、eval 5、mapping 9、openapi 3）、unit（evaluation 11、features 19、llm 6、nodes_llm 3、reasoning 7、routing 34、sse 5）。
2. 评测产物：`docs/EVAL-评测报告.md` 最终批次 `evb_01M5Q111XDZHNAA1YMCY2K14RR`，120 条 eval + 20 条 edge。
3. E2E 证据：`docs/E2E-UI-测试记录.md` 记录 4 条链路（CSV 单条、批量取消/导出、NL 两次澄清、review 两轮），另有 `screenshots/` 中未被书面记录覆盖的 chat、SSE 断线、超时、过期、评测页截图。
4. 未修改任何冻结文档；本文件为新增判定文档。

判定口径：
- **通过**：有直接测试、书面 E2E 记录或可复核的静态实现证据，且行为与 AC 一致。
- **未验证**：实现看似存在，但缺少针对该 AC 的测试/记录，或仅有截图、无法证明服务端行为。
- **失败**：实现缺失、行为与 AC/契约冲突，或权威产物给出不达标结果。

---

## 1. 裁决摘要

| 结果 | 数量 | 说明 |
| --- | --- | --- |
| 通过 | 39 | |
| 失败 | 14 | 其中 P0 9 条、P1 5 条 |
| 未验证 | 38 | 其中 P0 未验证 33 条，属交付阻塞证据缺口 |
| 合计 | 91 | PRD 附录 B US/IN/DG/KB/RP/HS/EV/SY/SE/CC 全量 |

P0 失败（直接阻塞交付，9 条）：

1. `AC-EV-02` KPI-01 准确率 88.33% < 90%。
2. `AC-EV-07` KPI-05 未计算（`null`），非 0。
3. `AC-US-03` 前端缺少密码规则即时提示（仅后端 422 兜底）。
4. `AC-IN-14` 用户修正未写入 `diagnosis_steps.event=user_correct`。
5. `AC-DG-22` 无 60s 后台中断过期扫描任务（仅请求触发懒判定）。
6. `AC-KB-04` 知识导入缺少必填字段/分类校验。
7. `AC-SY-04` 无一键启动脚本/端口冲突处理。
8. `AC-SE-01` 无提示词注入检测与安全事件日志。
9. `AC-SE-03` 敏感词仅 4 个（<12），无独立词表/命中日志。

P1 失败（交付前应修复，5 条）：

1. `AC-KB-03` 新版本自动归档旧 active，无手动激活/回滚。
2. `AC-KB-06` 调参记录 `top5_hit_rate` 为 `null`。
3. `AC-EV-05` 无提示词回归/自动回滚。
4. `AC-SY-03` BGE 异常未提供 health degraded。
5. `AC-SY-05` 无生产环境自检。

> 注：P0 未验证 33 条中，`AC-CC-01`（四浏览器）、`AC-DG-21`（15s 超时注入）、`AC-IN-20/21`（批量重复行与超时）直接阻断交付，必须在重验前补齐。

---

## 2. KPI 判定

| KPI | 结果 | 门槛 | 判定 | 性质 |
| --- | --- | --- | --- | --- |
| KPI-01 六分类准确率 | 88.33%（106/120） | ≥90% | **失败** | **评测集标签与 PRD 规则/可辨识性冲突为主，非代码伪造或指标造假**；但 PRD 主验收口径未达标 |
| KPI-02 报告 8 要素完整率 | 100.00%（960/960） | 100% | 达标 | 实现与评测共同证明 |
| KPI-03 P95 延迟 | 6685 ms | ≤10 s | 达标 | 真实 DeepSeek 调用下达标 |
| KPI-04 批量成功率 | 无批量评测产物 | 99% | **未验证** | 仅有 60 行 UI 取消链路，不能替代 240 行评测 |
| KPI-05 捏造率 | `null` | 0 | **失败** | 流程缺口：未组织 2 名评审，字段未落值 |
| 超时率 | 0.00%（0/120） | ≤1% | 达标 | 评测报告 §1 |
| artifact 落盘 | 已落盘 | 可追溯 | 达标 | `storage/eval/evb_01M5Q111XDZHNAA1YMCY2K14RR.json` |

### KPI-01 未达标归因

| 错误类型 | 条数 | 归因 | 是否技术缺陷 |
| --- | --- | --- | --- |
| 正常集 `tool_wear ≥190` 触发 TWF | 4 | AI4I 标注为正常，但按 PRD TWF 规则命中；规则证据优先，LLM 不得覆盖 | 否，属标签与规则口径冲突 |
| RNF 被判正常/未覆盖 | 10 | RNF 无稳定特征签名；PRD 禁止 RNF 规则兜底，LLM 也无法从特征区分 | 否，属数据不可分 + PRD 规则约束；但“未覆盖”是否计错需产品口径确认 |
| 其他 | 0 | 规则/LLM/检索/报告均无额外错误 | 否 |

结论：`EVAL` 报告如实披露 88.33% 与剔除 RNF 后 96.36%，未发现伪造指标或虚假 LLM 调用；但 **PRD 附录 B `AC-EV-02` 是硬门槛，不能因归因合理而自动视为通过**。

---

## 3. 逐 AC 判定（PRD 附录 B）

### 3.1 账号与会话（US）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-US-01 | P0 | 未验证 | `security.py:52-65`；`screenshots/01-register.png` | 有注册页截图，无注册成功/落库测试 |
| AC-US-02 | P0 | 未验证 | `security.py:58-70` | 唯一约束代码存在，无重复注册测试 |
| AC-US-03 | P0 | 失败 | `security.py:56-57` 有后端弱密码 422；`frontend/src/pages/LoginPage.tsx` 无 `minLength/pattern/即时校验` | 仅“提交被拒”，缺“前端即时提示”，AC 未完整满足 |
| AC-US-04 | P0 | 未验证 | `security.py:94,123` 统一凭据错误文案 | 无错误密码/不存在用户测试 |
| AC-US-05 | P0 | 未验证 | `frontend/src/App.tsx` 路由保护；后端 401 | 无未登录访问/401 跳转测试或截图 |
| AC-US-06 | P0 | 未验证 | `security.py:96-123`；`LoginPage.tsx` 423 倒计时 | 实现存在，无 5 次失败锁定测试 |
| AC-US-07 | P1 | 通过 | `test_diagnosis_contract.py::test_auth_flow` | 退出后 `/auth/me` 返回 401 |
| AC-US-08 | P0 | 未验证 | `security.py:77,162` 24h 过期 | 无过期会话测试；仅代码路径 |

### 3.2 输入与校验（IN）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-IN-01 | P0 | 通过 | `E2E-UI-测试记录.md` §1；`test_diagnosis_contract.py::test_csv_upload_and_single_diagnosis` | 上传→3 行预览→单条诊断→SSE→报告→导出 |
| AC-IN-02 | P0 | 未验证 | `uploads.py` 中文表头别名；`MappingModal.tsx` | 无中文表头 E2E/测试 |
| AC-IN-03 | P0 | 通过 | `test_mapping_contract.py` missing_required；`MappingModal.tsx:82-88,170` | 缺列禁止提交且标红 |
| AC-IN-04 | P0 | 未验证 | `config.py:56-57` 5MB/500；`uploads.py:150-161` | 无 6MB/600 行边界测试 |
| AC-IN-05 | P0 | 未验证 | `uploads.py` UTF-8/GBK 解码；`screenshots/01-csv-mapping.png` | 无 xlsx 截图/测试（仅代码支持） |
| AC-IN-06 | P0 | 通过 | `test_routing.py::test_rt08_batch_low_confidence_goes_auto_review`；`screenshots/07-batch-cancelled.png` | 有批量“待人工复核”截图；无 240 行夹具 |
| AC-IN-07 | P0 | 未验证 | `batches.py` 行错误隔离/`error_field` | 无单行失败行级错误测试 |
| AC-IN-08 | P0 | 通过 | `E2E-UI-测试记录.md` §2；`test_batch_contract.py::test_batch_cancel_then_idempotent` | 取消后计数守恒，行状态无 waiting_human/expired |
| AC-IN-09 | P0 | 通过 | `test_features.py::test_out_of_range_rejected`；前端字段校验 | 后端覆盖；前端即时提示见代码 |
| AC-IN-10 | P0 | 通过 | 冷启动脚本核验：L 型 + `wear_torque=12000` → OSF；`diagnosis.py` 规则 | PRD 示例命中 OSF |
| AC-IN-11 | P0 | 未验证 | `E2E` 仅验证 NL 缺项；`test_nl...` 仅 partial | 无 NL 完整直达 retrieve 的链路记录 |
| AC-IN-12 | P0 | 通过 | `E2E-UI-测试记录.md` §3；`test_diagnosis_contract.py::test_nl_partial_clarification_and_resume` | 缺设备 422；缺 3 特征进入 clarify |
| AC-IN-13 | P0 | 未验证 | `config.py:49` 30 分钟；`E2E` 显示 30:00 倒计时 | 无真实 30 分钟过期/无效补充不重置测试 |
| AC-IN-14 | P0 | 失败 | 后端无 `user_correct` 写入（`chat.py` confirm 路径）；`StepFlow` 仅能显示该事件 | 用户修正未留痕，AC 明确失败 |
| AC-IN-15 | P0 | 通过 | `test_diagnosis_contract.py::test_form_diagnosis_end_to_end` | 完整输入推进（含规则/检索/报告） |
| AC-IN-16 | P0 | 未验证 | `test_mapping_contract.py` 9 条 | 无重复表头、30 行非法前 50 统计测试 |
| AC-IN-17 | P0 | 未验证 | `mapping.py:46-52` row_no 越界 422 | 代码存在，无测试/截图 |
| AC-IN-18 | P0 | 通过 | `test_chat_contract.py::test_confirm_rejects_null_and_missing_device_id`；`test_rt17...` | `null`/缺 `device_id` 均 422 |
| AC-IN-19 | P1 | 通过 | `test_mapping_contract.py::test_mapping_scheme_crud` | 方案保存/复用/删除/清空 |
| AC-IN-20 | P0 | 未验证 | `batches.py`/指纹模块计算 batch 指纹 | 无批量重复行人工复核/追溯测试 |
| AC-IN-21 | P0 | 未验证 | `config.py:50` 任务超时；`batches.py` 取消调度 | 无 180 分钟批量超时、运行行完成/未开始行取消测试 |

### 3.3 诊断与状态机（DG）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-DG-01 | P0 | 通过 | 冷启动规则核验：M/10.5K/1500rpm/6283W/100min → 正常；`diagnosis.py` rules | 正常定义四点 |
| AC-DG-02 | P0 | 通过 | 冷启动核验：7.2K/1250rpm → HDF；`test_features.py` 派生特征 | |
| AC-DG-03 | P0 | 通过 | 冷启动核验：10.5K/1000rpm/3204W → PWF | |
| AC-DG-04 | P0 | 通过 | 冷启动核验：L/60Nm/200min → OSF（wear_torque=12000） | |
| AC-DG-05 | P0 | 通过 | 冷启动核验：210min/30Nm → TWF；RNF 无兜底（`test_reasoning.py::test_rnf_requires_unattributable_flag`） | |
| AC-DG-06 | P0 | 通过 | 冷启动核验：7.2K/1000rpm/14000 → OSF+HDF，主类型 OSF | |
| AC-DG-07 | P0 | 未验证 | `test_routing.py::test_rt07...`；`diagnosis.py` 置信度公式 | 无 0.7875→自动检索一次→review 的集成夹具 |
| AC-DG-08 | P0 | 通过 | `test_diagnosis_contract.py::test_review_confirm_generates_report`；`test_rt09` | 确认后仅进入报告，不重跑检索/推理 |
| AC-DG-09 | P0 | 未验证 | `test_rt10_review_supplement_rebuilds_parse` 仅路由 | 无“revision 变化、旧数据保留”集成测试 |
| AC-DG-10 | P0 | 通过 | `test_rt11_abort_goes_aborted`；`screenshots/25-aborted.png` | 终止且无报告 |
| AC-DG-11 | P0 | 未验证 | 快照中断载荷代码；`screenshots/13-resumed-review.png` | 刷新后 review 恢复无独立测试/网络记录 |
| AC-DG-12 | P0 | 通过 | `useDiagnosisStream.ts` retry/3 次失败 2s 轮询；`screenshots/08-sse-reconnect-banner.png`、`09-sse-reconnected.png` | 有断线/恢复截图，无书面网络日志 |
| AC-DG-13 | P0 | 未验证 | `test_rt05`；`knowledge.py` index missing → `none` | 无缺失索引端到端降级测试 |
| AC-DG-14 | P0 | 未验证 | `test_rt16`；`records.expire_if_needed` | 无“过期后相同输入新建”集成测试 |
| AC-DG-15 | P0 | 通过 | `test_diagnosis_contract.py::test_rt17_deduplicates_active_diagnosis` | 200 + deduplicated |
| AC-DG-16 | P0 | 未验证 | `diagnoses.py:331-340` 版本检查；`records.set_running` 单进程串行 | 无并发双 resume 测试；代码无 `WHERE version=?` 条件更新，依赖单事件循环 |
| AC-DG-17 | P0 | 未验证 | `test_rt12/test_rt13`；报告节点失败回落 | 无“报告 LLM 失败/缺要素→重试一次→degraded”集成测试 |
| AC-DG-18 | P0 | 通过 | `test_routing.py::test_rt08_low_confidence_first_never_retries`；快照字段 | `retry_count=0` 语义由路由测试覆盖 |
| AC-DG-19 | P0 | 通过 | `test_features.py::test_temp_inversion_is_quality_flag`；`diagnosis.py:143` 0.10 罚分 | 反转不判 HDF、不判正常、置信度下降 |
| AC-DG-20 | P0 | 通过 | `test_rt08_batch_low_confidence_goes_auto_review` | 路由覆盖；无 240 行夹具 |
| AC-DG-21 | P0 | 未验证 | `runtime/deadline.py`；`tests` 中无 >15s 节点注入测试；仅 `screenshots/23-failed-timeout.png` | P0 验证缺口：时间窗/无报告/SSE 事件未被测试证明 |
| AC-DG-22 | P0 | 失败 | `runtime/runner.py:200-211` 有一次扫描函数，但 `main.py`/启动无 60s 定时任务调用（grep `run_once` 无生产调用） | 无请求时不会后台置 `expired`；不满足“每 60s 扫描” |
| AC-DG-23 | P0 | 未验证 | `config.py:49` 30 分钟；`records.expire_if_needed` | 无 30 分钟 TTL 过期事件/无报告测试 |
| AC-DG-24 | P0 | 通过 | `test_rt10_round_two_supplement_is_rejected`；`E2E §4` | 第 2 轮补充置灰，确认/放弃可用 |

### 3.4 知识库（KB）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-KB-01 | P0 | 未验证 | `knowledge.py:238-286` top_k/score | 无 top5、缺失索引、覆盖率单测 |
| AC-KB-02 | P0 | 未验证 | `knowledge.py:249-286` 类型 2+3 策略；`nodes.py:172-177` retry top8 | 无重试扩充命中测试；阈值不随 retry 降低 |
| AC-KB-03 | P1 | 失败 | `knowledge.py:171-190` build 自动 `archived` 旧 active 并插入新 active；无 activate/rollback API/CLI | 违反“新版本不自动覆盖线上版本”，且无可回滚入口 |
| AC-KB-04 | P0 | 失败 | `knowledge.py:150-190` 直接写库，无必填字段/分类/类型校验 | 缺“处置建议”与缺“正常基线”类目均不会被拒绝，索引仍会更新 |
| AC-KB-05 | P0 | 未验证 | `startup.py:23-31` index missing → `missing`；`knowledge.retrieve` 返回 `none` | 无健康检查降级/其他入口可用测试 |
| AC-KB-06 | P1 | 失败 | `evaluation.py:526-536` `top5_hit_rate: None` | 调参对照记录存在但关键指标未计算 |

### 3.5 报告（RP）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-RP-01 | P0 | 通过 | `EVAL §1` KPI-02 100%（960/960）；`report.py` 8 要素 | |
| AC-RP-02 | P0 | 通过 | `screenshots/30-evidence-drawer.png`；`reasoning.py` evidence 绑定、`report.py` 引用校验 | 证据可跳转知识条目 |
| AC-RP-03 | P0 | 通过 | `ReportPanel.tsx` `react-markdown` + `skipHtml`；`report.py:229-234` 清洗 | 静态实现通过；无攻击用例 |
| AC-RP-04 | P0 | 通过 | `E2E §1` 导出 200；`diagnoses.py:381-390` `filename*=UTF-8''` | |
| AC-RP-05 | P1 | 未验证 | 无 0.62 review 夹具；`test_review_confirm...` 未断言置信度 | AC 指定首次/重试后均 0.62，未验证 |
| AC-RP-06 | P0 | 通过 | `report.py:234-236` 免责声明强制追加；评测 120/120 自检 | 无删除端点 |
| AC-RP-07 | P1 | 通过 | `EVAL §1/§4` 8/8；报告缺项修复一次代码 | |

### 3.6 历史（HS）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-HS-01 | P0 | 未验证 | `api/diagnoses.py` 列表参数/`records` 查询支持分页/筛选 | 无各筛选组合测试或截图 |
| AC-HS-02 | P0 | 通过 | `records.py:402` 改为 `ORDER BY created_at, rowid`；`test_snapshot_trace_steps...`；`E2E §1` | E2E 文档 §6 的旧问题已在代码修复，但文档未回写 |
| AC-HS-03 | P1 | 未验证 | 删除仅非批量终态（代码） | 无批量诊断删除 409 测试 |
| AC-HS-04 | P0 | 未验证 | `_row_or_404` 按 `user_id` 过滤 | 无越权 404 测试 |
| AC-HS-05 | P1 | 未验证 | `batches.py` 导出六状态列/`_csv_safe` | 无六状态齐全导出测试 |
| AC-HS-06 | P1 | 通过 | `screenshots/02-workbench-idle.png`、`14-chat-empty.png`、`22-history-drawer.png` | 空态/空历史截图存在 |

### 3.7 评测（EV）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-EV-01 | P0 | 通过 | `EVAL §1/§5/§6`；artifact 路径 | 指标、样例、bad case、artifact 齐全；tuning top5 缺失另见 KB-06 |
| AC-EV-02 | P0 | 失败 | `EVAL §1` 88.33%（106/120）<90% | PRD 附录 B 硬门槛未达 |
| AC-EV-03 | P0 | 未验证 | `evaluation.py` 失败样本/分母逻辑 | 无失败样本被排除、`report_count` 分母测试 |
| AC-EV-04 | P1 | 未验证 | `EVAL` KPI-03/P95/超时率达标；无批量 KPI-04 产物 | KPI-04 无证据 |
| AC-EV-05 | P1 | 失败 | 全仓无 prompt 回归/回滚实现（grep `rollback|baseline` 无业务代码） | 连续两轮低于基线回滚未做 |
| AC-EV-06 | P1 | 通过 | `screenshots/27-eval.png`、`28-eval-matrix.png`、`29-eval-badcases.png`；`EvalPage.tsx` 5 卡/6×7/20 条 | 无书面交互日志 |
| AC-EV-07 | P0 | 失败 | `evaluation.py` `fabrication_rate=null`；`EVAL §1` KPI-05 `null` | 未组织 2 名评审，KPI-05 未落 0 |
| AC-EV-08 | P1 | 未验证 | `EVAL` 无批量 240 行成功率产物 | 无 KPI-04 批量评测 |

### 3.8 系统（SY）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-SY-01 | P0 | 通过 | `startup.py:30-32` `llm_config=missing`；`services.ensure_llm_configured` | 启动不崩，表现为健康降级/调用 503；无测试 |
| AC-SY-02 | P0 | 通过 | `test_diagnosis_contract.py::test_health_contract` | 五依赖字段 + `X-Request-Id` |
| AC-SY-03 | P1 | 失败 | `startup.py:35-41` BGE 缺失时 `bge-m3` 模式直接抛异常退出，`auto` 模式回退且健康仍 `ok` | 未实现“health degraded 且其他功能可见” |
| AC-SY-04 | P0 | 失败 | 根目录/`backend/scripts` 无 `*.bat/*.ps1/*.sh` 启动脚本；无端口冲突处理代码 | AC 明确要求一键启动 |
| AC-SY-05 | P1 | 失败 | 无 `APP_ENV=production` 自检、HTTPS/加密/密钥检查代码 | 生产自检未实现 |

### 3.9 安全（SE）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-SE-01 | P0 | 失败 | 无提示词注入检测/拒绝/安全事件日志；`llm_client.py` 仅记录 hash | 攻击输入不影响规则层，但 AC 的检测与日志未实现 |
| AC-SE-02 | P0 | 未验证 | `uploads.py:150-161` 后缀 + 解码校验 | 无伪造扩展名测试 |
| AC-SE-03 | P0 | 失败 | `report.py:31` 仅 `("炸毁","引爆","攻击","杀人")` 4 词；无独立词表/命中日志 | 不满足 ≥12 词与日志审计 |
| AC-SE-04 | P1 | 通过 | `batches.py:464-470` `_csv_safe` 前缀单引号 | 静态实现；无公式注入测试 |
| AC-SE-05 | P1 | 通过 | `security.py:96-123` 登录失败锁定/`Retry-After` | 可视为基础限流；无压力测试 |

### 3.10 兼容性（CC）

| AC-ID | 优先级 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| AC-CC-01 | P0 | 未验证 | `E2E-UI-测试记录.md` 明确工具为 Chrome/CDP；无 Edge/Firefox/Safari 记录 | 四浏览器冒烟未完成，交付阻塞 |

---

## 4. 例外验收判定

### 4.1 是否接受“88.33% + bad case 全部归因于数据标签噪声”

**判定：不接受作为“通过”或“有条件通过”的依据。**

理由：

1. PRD 附录 B `AC-EV-02` 与 §3.10 将 KPI-01 六分类 ≥90% 定义为主验收硬门槛；`EVAL` 自身结论也写明“仍低于 90%，不满足最终验收”。
2. 即使产品方愿意接受 KPI-01 例外，仍有 **9 条 P0 失败 + 4 条 P0 未验证** 与 KPI-01 无关，不能顺带通过。
3. `KPI-05` 为 `null` 而非 0，`KPI-04` 无批量评测产物，均不能由“数据噪声”解释。

### 4.2 如果产品方坚持 KPI-01 例外，最低前置条件

仅在产品方书面批准时，才可讨论“有条件通过”，且必须同时满足：

1. 在交付说明中披露：六分类 88.33%（106/120）、剔除 RNF 96.36%（106/110）、14 条 bad case 的逐条归因、`R-05` 数据标签噪声上限。
2. 将 RNF 作为**参考指标**单列，不把 RNF 计入主准确率的同时仍展示六分类原始值；不得删除 RNF 样本或改写标签而不披露。
3. 对正常集 4 条 `wear≥190` 样本单独说明其与 PRD TWF 规则冲突，禁止通过放宽规则或让 LLM 覆盖规则证据来“修正”。
4. 新增契约登记（建议 `ARCH §10.4 C-010`）固化例外口径，并同步 PRD 附录 B / KPI 口径；在完成登记前，不得以“例外”替代验收。
5. 明确 RNF 的“未覆盖”是否计错：`AC-DG-05` 允许 RNF 输出“未覆盖”，而 KPI-01 六分类又把 RNF 计为必须命中，二者存在文档级矛盾，必须由产品口径裁决，不能由后端自行选择。

> 结论：即便接受例外，也只能是“带书面例外的重新验收”，不是本次判定可直接给出的“有条件通过”。

### 4.3 若要求调整评测集口径

若产品方不接受例外，应由后端/评测负责人提出评测集口径调整方案，且：

- 先登记 `ARCH §10.4`（如 `C-010`）并同步 PRD，再改评测集/标签；
- 不得直接放宽 RNF 规则、删除 RNF 样本、修改 PRD 阈值或伪造 KPI；
- 调整后重跑 120 条固定种子评测，目标 ≥108/120（90%），并保留新旧批次对比。

---

## 5. 其他契约偏差（不改变 AC 表，但需登记）

| 编号 | 现象 | 证据 | 影响 |
| --- | --- | --- | --- |
| OBS-01 | `/confirm` 命中 RT-17 后前端把会话置 `terminal` | `frontend/src/components/ChatPanel.tsx:218-228` | 与 HANDOFF §4.10“会话变 active、按原状态渲染”不一致；可能导致已有运行中诊断无法继续交互 |
| OBS-02 | `knowledge.build()` 自动归档旧 active 并激活新版本 | `backend/app/knowledge.py:171-190` | 与 AC-KB-03“不自动覆盖线上版本 + 可回滚”冲突 |
| OBS-03 | `run_once()` 过期扫描无生产调度 | `backend/app/runtime/runner.py:200-211`；`main.py` 无调用 | 与 AC-DG-22“60s 扫描”冲突；只有读请求触发懒过期 |
| OBS-04 | E2E 文档 §6 两项待修复与当前代码不一致 | `mapping.py:70-84` + `test_mapping_preview_single_returns_three_rows`；`records.py:402` + `test_snapshot_trace_steps...` | 代码已修复，E2E 文档未回写，验收材料存在陈旧证据 |
| OBS-05 | RETRY 只扩大 `top_k`，不降低覆盖阈值 | `knowledge.py:284-286` | 与“重试降低阈值扩充”的检索调参语义存在偏差，影响 KB-02 口径 |

---

## 6. 必须完成的下一步（按优先级）

### P0 阻断（全部完成后才可重验）

1. **KPI-01**：由产品方裁决例外或调整评测口径并登记 `ARCH §10.4`；重跑评测，目标 ≥90%；不得放宽 RNF/改 PRD/伪造指标。
2. **KPI-05**：组织 2 名评审完成捏造率统计，落 `fabrication_rate=0` 或如实记录失败；不得以 `null` 交付。
3. **四浏览器**：补 Edge/Firefox/Safari 冒烟记录（至少最新两个大版本）。
4. **60s 扫描**：在启动生命周期注册后台任务，调用 `runner.run_once()`，补“无请求 2 分钟自动 expired”测试。
5. **用户修正留痕**：在 `/confirm` 修改字段时写 `diagnosis_steps.event=user_correct`，且不改 `diagnosis_revision`，补 AC-IN-14 测试。
6. **提示词注入与敏感词**：增加检测/拒绝/安全日志；敏感词表 ≥12 并从配置加载，补 3 类输入测试。
7. **知识导入校验**：导入时校验必填字段/分类/类型，失败列修复项且不激活；补 KB-04 测试。
8. **一键启动**：提供启动脚本与端口冲突提示；补端口占用测试或记录。
9. **前端密码即时校验**：注册/改密输入框加规则提示，弱密码不发请求。
10. **补齐 P0 未验证**：批量重复行指纹、批量超时、15s 节点超时注入、完整 NL、TTL 过期、并发 resume。

### P1 交付前修复

- KB 版本手动激活/回滚（AC-KB-03）。
- 调参记录 `top5_hit_rate` 计算（AC-KB-06）。
- 提示词回归/自动回滚（AC-EV-05）。
- BGE 异常 health degraded（AC-SY-03）。
- 生产环境自检（AC-SY-05）。
- 0.62 review 夹具、历史筛选/越权/批量导出六状态、KPI-04 批量评测。

### 重验入口

- 后端：`cd backend && python -m pytest -q`（当前 137 passed，需保持且新增测试通过）。
- 评测：`python scripts/run_evaluation.py`，保留 artifact 与旧批次对比。
- E2E：四链路 + chat 链路 + 四浏览器，补书面网络/控制台记录。
- 所有契约变更先登记 `ARCH §10.4`，不得静默修改。
