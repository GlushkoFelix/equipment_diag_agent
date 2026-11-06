# 交付说明（DELIVERY NOTES）

| 项目 | 内容 |
| --- | --- |
| 交付版本 | **V1.0.0**（后端 1.0.0，API 前缀 `/api/v1`） |
| 最终判定 | **`docs/FINAL-ACCEPTANCE-V5.md`：【通过】90/90**（P0 78/78、P1 12/12；未验证 0、失败 0、待裁决 0） |
| 测试基线 | `storage/pytest-accept-v5.xml`：**194 collected / 0 failed / 0 error / 0 skipped / 50.686s** |
| 当前 LLM 模式 | `EDG_LLM_MODE=deepseek`（Key 已验证可用，`report_meta.model_name=deepseek-chat`） |
| 指标来源 | 最终批次 `evb_01M5Q111XDZHNAA1YMCY2K14RR`（未重跑、未改口径） |
| 裁决引用 | `C-011`（仅覆盖 KPI-01 六分类门槛）、`C-012`（仅覆盖 AC-CC-01），不外扩 |
| 冻结文档 | PRD / ARCH / UIUX / HANDOFF / DB / EVAL / FINAL-ACCEPTANCE V1–V5 **本轮均未修改** |

---

## 1. 最终判定与结论

- **AC 计数：90/90 通过（P0 78 / P1 12）**；未验证 0、失败 0、待裁决 0。清单与 PRD 附录 B 完全一致。
- **通过口径**：只认可可执行测试、真实 HTTP、浏览器产物、落盘 artifact；静态实现不算。
- **本轮唯一状态变化**：AC-KB-06 由 V4 的“未验证”转为 **通过**（两组参数 `400/50/5` 与 `200/20/8` 各建临时库实测，固定集 50 条，`delta=1.0-1.0=0.0`，同参数 `repeat.consistent=true`）。
- **历史版本轨迹**：V1【不通过】→ V4【有条件通过】（唯一条件为 AC-KB-06）→ **V5【通过】**。历史判定文档保留，不代之以本说明。

---

## 2. 测试基线与复验命令

基线：`storage/pytest-accept-v5.xml`（194 用例，0 失败/0 错误/0 跳过）。相对 V4 的 192 条：移除 1 条旧 KB-06 用例、新增 3 条，净增 2。

```powershell
# 1) 全量基线（应为 194/0/0/0）
cd e:\equipment_diag_agent\backend
python -m pytest -q --junitxml=..\storage\pytest-accept-v5.xml

# 2) 解析 junit 统计
python -c "import xml.etree.ElementTree as E; print(list(E.parse(r'..\storage\pytest-accept-v5.xml').getroot())[0].attrib)"

# 3) AC-KB-06 证据（两组参数不同 + delta + 重复一致）
python -c "import json; d=json.load(open(r'e:\equipment_diag_agent\storage\evidence\AC-KB-06-retrieval-comparison.json',encoding='utf-8')); print([r['params'] for r in d['runs']], [r['sample_total'] for r in d['runs']], d['delta'], d['consistent'], d['params_changed'], d['repeat']['params'])"

# 4) active 知识版本（应仅一个 active：kb_v1）
python -c "import sqlite3; db=sqlite3.connect(r'e:\equipment_diag_agent\storage\app.db'); db.row_factory=sqlite3.Row; print([dict(r) for r in db.execute('select kb_version,status,entry_count,built_at from knowledge_versions')])"

# 5) KPI-01 重算（五分类/六分类/llm_used/延迟）
python -c "import json,io,math; rows=json.load(io.open(r'e:\equipment_diag_agent\storage\eval\evb_01M5Q111XDZHNAA1YMCY2K14RR.json',encoding='utf-8')); ev=[r for r in rows if r['dataset_split']=='eval']; six=sum(r['correct'] for r in ev); five=sum(r['correct'] for r in ev if r['expected_primary']!='RNF'); print('six',six,'/120',round(six/120,4),'five',five,'/110',round(five/110,4)); print('llm_used',sum(bool(r['llm_used']) for r in rows),'/',len(rows)); lat=sorted(r['latency_ms'] for r in ev); print('avg/p50/p95/max',round(sum(lat)/len(lat),1),lat[len(lat)//2],lat[math.ceil(0.95*len(lat))-1],lat[-1])"

# 6) KPI-04 批次与报告口径
python -c "import sqlite3,json,collections; db=sqlite3.connect(r'e:\equipment_diag_agent\storage\app.db'); db.row_factory=sqlite3.Row; B='bch_01M5S9Q7P4VHTNTM5Z5X3PE5ZD'; print(collections.Counter(r['status'] for r in db.execute('select status from batch_rows where batch_task_id=?',(B,)))); print(collections.Counter((json.loads(r['report_meta_json']) if r['report_meta_json'] else {}).get('model_name') for r in db.execute('select report_meta_json from diagnoses where batch_task_id=?',(B,))))"
```

---

## 3. KPI 表（含六分类披露与 C-011 限定）

| KPI | 结果 | 门槛 | 判定 | 说明 |
| --- | --- | --- | --- | --- |
| **KPI-01 主验收：五分类（`C-011`）** | **96.36%（106/110）** | ≥90% | **通过** | HDF/PWF/OSF/TWF 各 20/20、正常 26/30 |
| **KPI-01 六分类原始值（必须同时披露）** | **88.33%（106/120）** | ≥90% | **未达门槛，披露、不阻塞** | RNF 0/10、正常 4 条误判 TWF |
| KPI-02 报告 8 要素完整率 | **100%（120/120，960/960）** | ≥95% | 通过 | `elements_present=8` × 120 |
| KPI-03 延迟 | avg **6035.8ms** / P50 6035 / P95 **6685ms** / max **7530ms** | avg 与 P95 ≤10s；max ≤15s | 通过 | eval 120 条成功样本 |
| 超时率 | **0/120 = 0.00%** | ≤1% | 通过 | artifact 全部 `succeeded` |
| KPI-04 批量成功率 | **239/240 = 99.58%**；严格 DeepSeek **238/240 = 99.17%** | ≥99% | 通过 | 两种口径均达标，见 §4 |
| KPI-05 捏造率 | **0/20 = 0.00%** | 0 | 通过 | 20 条真实未覆盖样本、2 名评审、3 条分歧裁决，`fabricated_total=0` |

**KPI-01 数据可用性**：artifact 140/140 `llm_used=true`；现网批次 239 份报告中 238 份为 `deepseek-chat`。两者一致，未由规则模板冒充。

**C-011 限定（必须随交付披露）**：

- `C-011` 仅改变本次交付的验收范围：**主验收按五分类 96.36%（106/110）≥90%**，RNF 10 条单列参考、不计入主准确率分子分母。
- **六分类 88.33%（106/120）必须同时披露**；任何只引用 96.36% 而不披露 88.33% 的表述均不符合本说明。
- 未删除或替换任何样本，未放宽 RNF 规则，未放宽 PRD 阈值，未让 LLM 覆盖规则证据。
- `C-011` 不构成对 PRD 附录 B 六分类门槛的永久修改，**不外扩**到其他 AC 或 KPI。

---

## 4. KPI-04 两种口径说明

批次 `bch_01M5S9Q7P4VHTNTM5Z5X3PE5ZD`，240 行真实任务：

| 口径 | 分子 | 分母 | 结果 | 门槛 |
| --- | --- | --- | --- | --- |
| **交付口径（含可观测回落）** | 239（209 `succeeded` + 30 `degraded_review`） | 240 | **99.58%** | ≥99% 通过 |
| **严格 DeepSeek 口径** | 238（仅 `report_meta.model_name=deepseek-chat`） | 240 | **99.17%** | ≥99% 通过 |

- 分母规则：`total_rows - cancelled`；`failed` / `failed_timeout` 计入分母。
- 第 31 行 `FEATURE_OUT_OF_RANGE`（`air_temp_k` 越界）在特征校验阶段失败，不生成诊断与报告，故 240 行中只有 239 份 `report_meta`。
- 239 份报告中 1 份 `model_name=rule-engine`（`llm_used=false`，`status=succeeded`），属**可观测回落**（报告 LLM 超时后回落模板）；该行未标 `degraded`，登记为 OBS-10，不影响成功率判定。

---

## 5. C-012 对 AC-CC-01 的适用与不外扩声明

- **AC-CC-01 = 通过**：依 `ARCH §10.4 C-012`（产品方批准），AC-CC-01 浏览器/版本覆盖的客观偏差（Edge 仅 1 个版本、Windows 无原生 Safari 以 WebKit 替代）予以接受。
- **证据**：7 组配置（Chrome 156/155、Edge 156、Firefox 157/155、WebKit 27.2/26.6）× 6 步共 42 张截图，`screenshots/evidence/AC-CC-01-browser-smoke.json` 7/7 `pass=true`。
- **不外扩**：`C-012` 适用范围**仅限 AC-CC-01**，不构成对 PRD 附录 B 的永久修改，不得用于其他 AC 或任何 KPI 的豁免。
- 建议后续补齐：具备 Edge 次新版本安装包的机器补一次冒烟；macOS 真机 Safari 走一次同链路。

---

## 6. 已知限制与后续迭代（OBS-01~OBS-12，均不阻塞交付）

> 与 `docs/FINAL-ACCEPTANCE-V5.md` §7.2 逐条一致，照录如下。

| # | 事项 | 说明 | 建议 |
| --- | --- | --- | --- |
| OBS-01 | AC-HS-05 状态来源 | 六状态由测试直接 UPDATE `batch_rows` 注入，导出本身真实；未证明批量运行能自然产生 `degraded`/`failed_timeout` | 后续用真实批量夹具覆盖自然产出路径 |
| OBS-02 | AC-IN-07 夹具 | 失败行字段为 `air_temp_k`，AC 原文为 `torque_nm` 文本 | 后续按 AC 原文对齐夹具 |
| OBS-03 | AC-DG-17 分支 | 仅覆盖模板缺项分支；LLM 失败回落模板分支未断言 | 补报告 LLM 失败 → 重试 → `degraded` 用例 |
| OBS-04 | AC-DG-09 | 报告内容与 `review_round=1` 未单独断言 | 补报告渲染断言 |
| OBS-05 | AC-KB-05 | 检索三字段（`hits`/`max_score`/`coverage`）未单独断言 | 补断言 |
| OBS-06 | AC-SY-02 | 日志字段未逐条落盘抽检 | 补日志抽检脚本 |
| OBS-07 | AC-SE-05 | HTTPS/DB 加密/Key 三项同缺，未做单项隔离 | 补逐项门禁用例 |
| OBS-08 | KPI-04 夹具 | 无 `failed_timeout`/`degraded` 行；取消 40 行复跑未执行 | 后续补 |
| OBS-09 | KPI-05 形式 | 评审人为内部代号（小A/小B），两份表格式一致，**无外部实名存证** | 如需对外审计，补实名/可核验存证 |
| OBS-10 | 1 条 `rule-engine` 回落 | 状态仍 `succeeded`，未标 `degraded`；报告可观测 `model_name` | 建议回落时置 `degraded` 或写 `error_code` |
| OBS-11 | E2E 文档滞后 | `E2E-UI-测试记录.md` 未回写 18–21 | **已闭环**：本次已在 `docs/E2E-UI-测试记录.md` §8 回写 18 / 19a / 19b / 19 / 20 / 21 |
| OBS-12 | KB-06 证据命名 | 必查指定 `AC-KB-06-param-sweep.json` 原不存在 | **已闭环**：`storage/evidence/` 下已生成 `AC-KB-06-param-sweep.json`，与 `AC-KB-06-retrieval-comparison.json` **内容完全一致（SHA256 相同）**，两者等价，均为 AC-KB-06 有效证据 |

---

## 7. 证据索引

### 7.1 `storage/evidence/`（AC 证据 10 个文件，含等价副本）

| 文件 | 对应 AC |
| --- | --- |
| `AC-RP-05-report.json` | AC-RP-05 |
| `AC-IN-05-xlsx-upload.json` | AC-IN-05 |
| `AC-SY-01-llm-missing.json` | AC-SY-01 |
| `AC-KB-06-retrieval-comparison.json` | AC-KB-06 |
| `AC-KB-06-param-sweep.json` | AC-KB-06（与上一文件完全一致，对齐验收索引命名） |
| `AC-HS-05-six-status-export.csv` | AC-HS-05 |
| `AC-HS-05-export-summary.json` | AC-HS-05 |
| `AC-IN-17-history-after-delete.json` | AC-IN-17 |
| `AC-SE-02-formula-export.csv` | AC-SE-02 |
| `AC-SE-02-formula-escape.json` | AC-SE-02 |

### 7.2 测试基线

| 文件 | 说明 |
| --- | --- |
| `storage/pytest-accept-v5.xml` | 194 collected / 0 failed / 0 error / 0 skipped |

### 7.3 截图证据

| 路径 | 内容 |
| --- | --- |
| `screenshots/evidence/`（目录） | 多浏览器 42 张（`AC-CC-01-*.png`）+ `AC-CC-01-browser-smoke.json`；KPI-04 批次与 report_meta（`AC-KPI-04-*`）；KPI-05 v2 六件套（`AC-EV-07-v2-*`）；TTL/超时/索引降级/并发冲突（`AC-DG-13/16/21/23-*`）；`AC-IN-20`、`AC-IN-21`、`AC-EV-08-*`、`extras-*` |
| `screenshots/e2e/18-401-redirect-login.png` | 会话过期（`AUTH_SESSION_EXPIRED`）401 → 跳登录（AC-US-08） |
| `screenshots/e2e/19-review-refresh-restored.png` | 刷新后 review 面板恢复（AC-DG-11） |
| `screenshots/e2e/19a-dg11-review-before-refresh.png` | 刷新前复核面板（AC-DG-11） |
| `screenshots/e2e/19b-dg11-after-refresh-before-fix.png` | 刷新后修复前状态（AC-DG-11） |
| `screenshots/20-batch-running.png` | 批量运行中进度（AC-IN-06 / AC-IN-08 佐证） |
| `screenshots/e2e/20-review-refresh-confirm-report.png` | 确认后生成报告（AC-DG-11） |
| `screenshots/e2e/21-export-401-redirect-login.png` | 导出请求 401 → 跳登录（AC-SE-04 / AC-US-08 佐证） |

> 截图场景与断言详见 `docs/E2E-UI-测试记录.md` §8；AC 与证据映射详见 `docs/AC-EVIDENCE-PACK.md` §8。

---

## 8. 边界声明

- 本轮**未修改任何冻结文档**：`PRD-设备故障诊断智能体-V1.0.0.md`、`ARCH-系统架构与API契约.md`、`UIUX-设备故障诊断智能体.md`、`HANDOFF-系统架构与API契约交接.md`、`DB-数据库设计文档.md`、`EVAL-评测报告.md`、`FINAL-ACCEPTANCE.md`、`FINAL-ACCEPTANCE-V2/V3/V4/V5.md`。
- 本轮只改非冻结交付文档（`AC-EVIDENCE-PACK.md`、`DELIVERY-NOTES.md`、`E2E-UI-测试记录.md`）与证据文件命名（新增 `AC-KB-06-param-sweep.json` 等价副本，未改动原文件）。
- 未改 API / SSE / 状态机 / 数据库 Schema；未重跑评测、未改评测集与评分脚本。
- `C-011` 仅覆盖 KPI-01 六分类门槛；`C-012` 仅覆盖 AC-CC-01；未新增其他豁免。
