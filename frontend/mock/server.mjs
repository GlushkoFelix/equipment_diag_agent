/* eslint-disable */
/**
 * Mock API + SSE server for the equipment diagnosis workbench.
 * Contract source: docs/ARCH-系统架构与API契约.md V1.2.0 §5.
 * Development-only. It is not part of the production frontend build.
 */
import http from "node:http";
import { randomUUID } from "node:crypto";

const PORT = Number(process.env.MOCK_PORT || 8000);
const BASE = "/api/v1";
const TTL_MS = 30 * 60 * 1000;

const users = new Map();
users.set("zhangsan", {
  user_id: "usr_demo0001",
  username: "zhangsan",
  password: "Abcd1234",
  created_at: new Date(Date.now() - 86400000).toISOString(),
});
const sessions = new Map();
const loginFailures = new Map();
const uploads = new Map();
const diagnoses = new Map();
const eventLogs = new Map();
const subscribers = new Map();
const chatSessions = new Map();
const batches = new Map();
const batchRows = new Map();
const batchTimers = new Map();
const fingerprints = new Map();

const nowIso = () => new Date().toISOString();
const uid = (prefix) => `${prefix}_${randomUUID().replace(/-/g, "").slice(0, 20)}`;
const clamp = (n, a, b) => Math.min(b, Math.max(a, n));

const DISCLAIMER =
  "本报告由智能体基于传感器数据与故障知识库自动生成，仅供设备运维参考，不构成正式检测结论。涉及特种设备、高危工艺与安全生产的问题，应以企业安全规程和具备资质的专业人员判定为准，必要时应立即停机检修。";

const STEP_LABELS = {
  orchestrator: "总控",
  parse_input: "数据读取",
  retrieve: "知识检索",
  diagnose: "诊断推理",
  report: "报告生成",
};

const FEATURE_META = {
  device_id: { label: "设备标识", unit: null, example: "3号机" },
  product_type: { label: "产品类型", unit: null, example: "M" },
  air_temp_k: { label: "空气温度", unit: "K", example: 298.1 },
  process_temp_k: { label: "工艺温度", unit: "K", example: 308.6 },
  rotational_speed_rpm: { label: "转速", unit: "rpm", example: 1551 },
  torque_nm: { label: "扭矩", unit: "Nm", example: 42.8 },
  tool_wear_min: { label: "刀具磨损", unit: "min", example: 100 },
};

function sendJson(res, status, body, extraHeaders = {}) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Request-Id": `req_${randomUUID().replace(/-/g, "").slice(0, 20)}`,
    ...extraHeaders,
  });
  res.end(payload);
}

function sendError(res, status, code, message, details) {
  sendJson(res, status, {
    error: {
      code,
      message,
      request_id: `req_${randomUUID().replace(/-/g, "").slice(0, 20)}`,
      ...(details ? { details } : {}),
    },
  });
}

function parseCookies(req) {
  const raw = req.headers.cookie || "";
  return Object.fromEntries(
    raw
      .split(";")
      .map((part) => part.trim().split("="))
      .filter((pair) => pair.length === 2)
      .map(([k, v]) => [k, decodeURIComponent(v)]),
  );
}

function currentUser(req) {
  const token = parseCookies(req).edg_session;
  return token ? sessions.get(token) || null : null;
}

function requireUser(req, res) {
  const user = currentUser(req);
  if (!user) {
    sendError(res, 401, "AUTH_REQUIRED", "登录已过期，请重新登录");
    return null;
  }
  return user;
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks);
}

async function readJson(req) {
  const buf = await readBody(req);
  if (!buf.length) return {};
  try {
    return JSON.parse(buf.toString("utf8"));
  } catch {
    return {};
  }
}

function parseMultipart(buf, contentType) {
  const match = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType || "");
  const boundary = match?.[1] || match?.[2];
  if (!boundary) return null;
  const raw = buf.toString("latin1").split(`--${boundary}`);
  for (const part of raw) {
    const sep = part.indexOf("\r\n\r\n");
    if (sep < 0) continue;
    const head = part.slice(0, sep);
    if (!/name="file"/.test(head)) continue;
    const filenameRaw = /filename="([^"]*)"/.exec(head)?.[1] || "upload.csv";
    let filename = filenameRaw;
    try {
      filename = Buffer.from(filenameRaw, "latin1").toString("utf8");
      if (!/[\u4e00-\u9fff]/.test(filename) && /[\u4e00-\u9fff]/.test(filenameRaw)) filename = filenameRaw;
    } catch {
      filename = filenameRaw;
    }
    let content = part.slice(sep + 4);
    if (content.endsWith("\r\n")) content = content.slice(0, -2);
    return { filename, content: Buffer.from(content, "latin1") };
  }
  return null;
}

function splitCsvLine(line) {
  const out = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else {
        quoted = !quoted;
      }
    } else if (ch === "," && !quoted) {
      out.push(cur.trim());
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur.trim());
  return out;
}

function parseCsv(text) {
  const lines = text.replace(/\uFEFF/g, "").split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (!lines.length) return { headers: [], rows: [] };
  const headers = splitCsvLine(lines[0]).map((h) => h.replace(/\s+/g, " ").trim());
  const rows = lines.slice(1).map((line) => splitCsvLine(line));
  return { headers, rows };
}

const HEADER_ALIASES = {
  device_id: ["device id", "device_id", "设备标识", "设备编号"],
  product_type: ["product type", "product_type", "产品类型"],
  air_temp_k: ["air temperature [k]", "air_temp_k", "空气温度"],
  process_temp_k: ["process temperature [k]", "process_temp_k", "工艺温度"],
  rotational_speed_rpm: ["rotational speed [rpm]", "rotational_speed_rpm", "转速"],
  torque_nm: ["torque [nm]", "torque_nm", "扭矩"],
  tool_wear_min: ["tool wear [min]", "tool_wear_min", "刀具磨损"],
};

function suggestMapping(headers) {
  const mapping = {};
  for (const [key, aliases] of Object.entries(HEADER_ALIASES)) {
    mapping[key] =
      headers.find((h) => aliases.includes(h.toLowerCase().trim())) ||
      headers.find((h) => aliases.some((a) => h.toLowerCase().trim().includes(a))) ||
      null;
  }
  return mapping;
}

function toNumber(value) {
  const n = Number(String(value).replace(/[^\d.+-]/g, ""));
  return Number.isFinite(n) ? n : null;
}

function normalizeRow(headers, row, mapping, defaultDeviceId) {
  const get = (key) => {
    const col = mapping[key];
    if (!col) return undefined;
    const idx = headers.indexOf(col);
    return idx >= 0 ? row[idx] : undefined;
  };
  const deviceId = (get("device_id") || defaultDeviceId || "").trim() || null;
  return {
    device_id: deviceId,
    product_type: (get("product_type") || "").trim() || null,
    air_temp_k: toNumber(get("air_temp_k")),
    process_temp_k: toNumber(get("process_temp_k")),
    rotational_speed_rpm: toNumber(get("rotational_speed_rpm")),
    torque_nm: toNumber(get("torque_nm")),
    tool_wear_min: toNumber(get("tool_wear_min")),
  };
}

function deriveFeatures(normalized) {
  const air = normalized.air_temp_k ?? 0;
  const processT = normalized.process_temp_k ?? 0;
  const speed = normalized.rotational_speed_rpm ?? 0;
  const torque = normalized.torque_nm ?? 0;
  return {
    temp_diff: Number((processT - air).toFixed(1)),
    power_w: Number(((2 * Math.PI * speed * torque) / 60).toFixed(1)),
    wear_torque: Number(((normalized.tool_wear_min ?? 0) * torque).toFixed(1)),
  };
}

function missingFieldsFor(features, includeDevice = false) {
  const fields = [];
  const keys = includeDevice
    ? ["device_id", "product_type", "air_temp_k", "process_temp_k", "rotational_speed_rpm", "torque_nm", "tool_wear_min"]
    : ["product_type", "air_temp_k", "process_temp_k", "rotational_speed_rpm", "torque_nm", "tool_wear_min"];
  for (const key of keys) {
    const value = features[key];
    if (value === null || value === undefined || value === "") {
      const meta = FEATURE_META[key];
      fields.push({ field: key, label: meta.label, unit: meta.unit, example: meta.example, reason: "MISSING" });
    }
  }
  return fields;
}

function allFeaturesPresent(features) {
  return missingFieldsFor(features, true).length === 0;
}

function fingerprintOf(features) {
  return [
    "fp",
    features.device_id,
    features.product_type,
    features.air_temp_k,
    features.process_temp_k,
    features.rotational_speed_rpm,
    features.torque_nm,
    features.tool_wear_min,
  ].join("|");
}

function buildReport(snapshot) {
  const f = snapshot.features?.normalized || {};
  const d = snapshot.features?.derived || {};
  const title = snapshot.report_title || `${snapshot.device_id} 诊断报告`;
  const citations = (snapshot.evidence_refs || []).map((e) => `[${e.entry_id}] ${e.title}`).join("、");
  const type = snapshot.primary_type || "未覆盖";
  const confidence = snapshot.confidence ?? 0;
  const level = snapshot.confidence_level === "high" ? "高" : snapshot.confidence_level === "low" ? "低" : "中";
  return `# ${title}

## 1. 诊断结论
设备 **${snapshot.device_id}** 的主类型判定为 **${type}**。当前结论基于 ${Object.keys(f).length} 项标准化特征与故障知识库检索结果，建议在下一个巡检周期前完成复核。

## 2. 置信度与分级
置信度 **${confidence.toFixed(2)} · ${level}**。四因子加权结果：规则证据 0.35、知识覆盖 0.20、LLM 自评 0.25、数据完整度 0.20；扣分项 ${snapshot.confidence_breakdown?.penalties ?? 0}。${
    snapshot.human_decision === "confirm" ? "本结论已由人工确认。" : ""
  }

## 3. 关键数据特征
| 特征 | 数值 | 单位 |
| --- | --- | --- |
| 空气温度 | ${f.air_temp_k ?? "—"} | K |
| 工艺温度 | ${f.process_temp_k ?? "—"} | K |
| 转速 | ${f.rotational_speed_rpm ?? "—"} | rpm |
| 扭矩 | ${f.torque_nm ?? "—"} | Nm |
| 刀具磨损 | ${f.tool_wear_min ?? "—"} | min |
| 温差 | ${d.temp_diff ?? "—"} | K |
| 功率 | ${d.power_w ?? "—"} | W |

## 4. 判断依据
1. 温差 ${d.temp_diff ?? "—"} K 与转速 ${f.rotational_speed_rpm ?? "—"} rpm 的组合命中 ${type} 规则集。
2. 检索命中知识条目 ${citations || "无"}，覆盖度 ${snapshot.retrieval?.coverage === "covered" ? "已覆盖" : "未覆盖"}。
3. 数据完整度 ${Math.round((snapshot.features?.completeness ?? 0) * 100)}%。

## 5. 鉴别诊断
${(snapshot.secondary_types || []).length ? (snapshot.secondary_types || []).map((t) => `- ${t}：需结合振动与温升趋势进一步排除。`).join("\n") : "- 暂无需要优先排除的候选类型。"}

## 6. 维修与处置建议
- 检查散热通道与冷却介质流量，确认无堵塞。
- 复核主轴扭矩负载，必要时降载运行。
- 在下一次停机窗口检查刀具磨损并记录基准值。

## 7. 数据质量与假设
- 数据完整度 ${Math.round((snapshot.features?.completeness ?? 0) * 100)}%，质量标记：${
    (snapshot.features?.data_quality_flags || []).join("、") || "无"
  }。
- 假设：传感器读数在标定有效期内；未提供环境湿度。

## 8. 免责声明与知识边界
> ${DISCLAIMER}
`;
}

function makeSnapshot(partial) {
  return {
    diagnosis_id: partial.diagnosis_id,
    device_id: partial.device_id,
    input_type: partial.input_type || "form",
    input_summary: partial.input_summary || { file_name: null, row_no: null, text_excerpt: null },
    report_title: partial.report_title ?? null,
    status: partial.status || "running",
    version: partial.version ?? 1,
    diagnosis_revision: partial.diagnosis_revision ?? 1,
    retry_count: partial.retry_count ?? 0,
    review_round: partial.review_round ?? 0,
    report_retry_count: partial.report_retry_count ?? 0,
    report_elements_check: partial.report_elements_check ?? null,
    duration_ms: partial.duration_ms ?? 0,
    primary_type: partial.primary_type ?? null,
    secondary_types: partial.secondary_types ?? [],
    confidence: partial.confidence ?? null,
    confidence_level: partial.confidence_level ?? null,
    confidence_breakdown: partial.confidence_breakdown ?? null,
    knowledge_status: partial.knowledge_status ?? null,
    evidence_refs: partial.evidence_refs ?? [],
    features: partial.features ?? null,
    retrieval: partial.retrieval ?? null,
    interrupt: partial.interrupt ?? null,
    human_decision: partial.human_decision ?? null,
    auto_review: partial.auto_review ?? false,
    report: partial.report ?? null,
    report_meta: partial.report_meta ?? null,
    trace_steps: partial.trace_steps ?? [],
    timings: partial.timings ?? { total_ms: 0, nodes: {} },
    error: partial.error ?? null,
    batch: partial.batch ?? null,
    created_at: partial.created_at || nowIso(),
    started_at: partial.started_at ?? null,
    finished_at: partial.finished_at ?? null,
  };
}

function logEvent(streamId, type, payload, revision) {
  const seq = (eventLogs.get(streamId)?.length || 0) + 1;
  const event = {
    seq,
    stream_kind: subscribers.get(streamId)?.kind || (streamId.startsWith("bch_") ? "batch" : "diagnosis"),
    stream_id: streamId,
    type,
    revision: revision ?? null,
    occurred_at: nowIso(),
    payload,
  };
  const log = eventLogs.get(streamId) || [];
  log.push(event);
  eventLogs.set(streamId, log);
  broadcast(streamId, event);
  return event;
}

function broadcast(streamId, event) {
  const entry = subscribers.get(streamId);
  if (!entry) return;
  for (const res of entry.res) {
    writeSse(res, event);
    entry.lastSent.set(res, event.seq);
  }
}

function writeSse(res, event) {
  if (event.seq !== null && event.seq !== undefined) res.write(`id: ${event.seq}\n`);
  res.write(`event: ${event.type}\n`);
  res.write(`data: ${JSON.stringify(event)}\n\n`);
}

function closeSubscribers(streamId) {
  const entry = subscribers.get(streamId);
  if (!entry) return;
  for (const res of entry.res) {
    try {
      res.end();
    } catch {}
  }
  entry.res.clear();
  subscribers.delete(streamId);
}

function addStep(diag, node, phase, summary, duration, ruleId) {
  diag.trace_steps.push({
    step_id: uid("stp"),
    node,
    event: phase,
    rule_id: ruleId || null,
    revision: diag.diagnosis_revision,
    summary: summary || null,
    duration_ms: duration || 0,
    created_at: nowIso(),
  });
  diag.timings.nodes[node] = (diag.timings.nodes[node] || 0) + (duration || 0);
  logEvent(diag.diagnosis_id, "step", {
    node,
    phase,
    rule_id: ruleId || null,
    summary: summary || null,
    duration_ms: duration ?? null,
  }, diag.diagnosis_revision);
}

const timers = new Map();
function later(diagId, delay, fn) {
  const list = timers.get(diagId) || [];
  const t = setTimeout(() => {
    const current = diagnoses.get(diagId);
    if (!current) return;
    fn(current);
  }, delay);
  list.push(t);
  timers.set(diagId, list);
}

function clearTimers(diagId) {
  for (const t of timers.get(diagId) || []) clearTimeout(t);
  timers.delete(diagId);
}

function setStatus(diag, to, reason, extra = {}) {
  const from = diag.status;
  diag.status = to;
  diag.version += 1;
  if (to === "succeeded" || to === "degraded" || to === "degraded_review" || to === "aborted" || to === "failed" || to === "failed_timeout" || to === "expired") {
    diag.finished_at = nowIso();
    diag.duration_ms = diag.duration_ms || 8400;
    diag.timings.total_ms = diag.duration_ms;
  }
  logEvent(diag.diagnosis_id, "status", { from, to, reason, version: diag.version, ...extra }, diag.diagnosis_revision);
  if (["succeeded", "degraded", "degraded_review", "aborted", "failed", "failed_timeout", "expired"].includes(to)) {
    setTimeout(() => closeSubscribers(diag.diagnosis_id), 80);
  }
}

function attachReviewInterrupt(diag, round, confidence, level) {
  const expires = new Date(Date.now() + TTL_MS).toISOString();
  diag.status = "waiting_human";
  diag.version += 1;
  diag.review_round = round;
  diag.confidence = confidence;
  diag.confidence_level = level;
  diag.interrupt = {
    type: "review",
    expires_at: expires,
    review_round: round,
    version: diag.version,
    payload: {
      created_at: nowIso(),
      primary_type: diag.primary_type,
      secondary_types: diag.secondary_types,
      confidence,
      confidence_level: level,
      confidence_breakdown: diag.confidence_breakdown,
      evidence_refs: diag.evidence_refs,
      reason: round === 2 ? "补充后置信度仍低于发布阈值，需人工确认。" : "刀具磨损值与温度组合仅弱相关，规则证据不唯一。",
      missing_fields: round === 2 ? [] : missingFieldsFor(diag.features.normalized),
      review_round: round,
    },
  };
  logEvent(diag.diagnosis_id, "interrupt", {
    interrupt_type: "review",
    payload: diag.interrupt.payload,
    expires_at: expires,
    review_round: round,
    version: diag.version,
  }, diag.diagnosis_revision);
  logEvent(diag.diagnosis_id, "status", {
    from: "running",
    to: "waiting_human",
    reason: "review_required",
    version: diag.version,
  }, diag.diagnosis_revision);
}

function attachClarificationInterrupt(diag, fields) {
  const expires = new Date(Date.now() + TTL_MS).toISOString();
  diag.status = "waiting_human";
  diag.version += 1;
  diag.interrupt = {
    type: "clarification",
    expires_at: expires,
    review_round: 0,
    version: diag.version,
    payload: {
      created_at: nowIso(),
      missing_fields: fields,
      partial_features: diag.features.normalized,
      device_id: diag.device_id,
    },
  };
  logEvent(diag.diagnosis_id, "interrupt", {
    interrupt_type: "clarification",
    payload: diag.interrupt.payload,
    expires_at: expires,
    review_round: 0,
    version: diag.version,
  }, diag.diagnosis_revision);
  logEvent(diag.diagnosis_id, "status", {
    from: "running",
    to: "waiting_human",
    reason: "clarification_required",
    version: diag.version,
  }, diag.diagnosis_revision);
}

function finishWithReport(diag, forceDegraded = false) {
  addStep(diag, "report", "start", "生成报告", null, "RT-15");
  diag.report_elements_check = forceDegraded
    ? { passed: false, present: ["诊断结论", "置信度与分级", "关键数据特征", "判断依据", "鉴别诊断", "维修与处置建议", "免责声明与知识边界"], missing: ["数据质量与假设"], report_retry_count: 1 }
    : { passed: true, present: ["诊断结论", "置信度与分级", "关键数据特征", "判断依据", "鉴别诊断", "维修与处置建议", "数据质量与假设", "免责声明与知识边界"], missing: [], report_retry_count: 0 };
  diag.report_retry_count = diag.report_elements_check.report_retry_count;
  diag.report_title = `${diag.device_id} ${diag.primary_type} 诊断报告`;
  diag.report_meta = {
    template_version: "tpl-v1.2",
    prompt_version: "prompt-v1.3",
    kb_version: "kb-v1.0.0",
    model_name: "deepseek-chat",
    auto_review: diag.auto_review,
    generated_at: nowIso(),
    degraded_reasons: diag.report_elements_check.missing,
  };
  diag.report = {
    markdown: buildReport(diag),
    download_url: `${BASE}/diagnoses/${diag.diagnosis_id}/report.md`,
  };
  diag.duration_ms = diag.duration_ms || 8400;
  logEvent(diag.diagnosis_id, "step", {
    node: "report",
    phase: "end",
    rule_id: "RT-15",
    summary: forceDegraded ? "报告缺项，降级发布" : "8 要素齐备",
    duration_ms: 1200,
  }, diag.diagnosis_revision);
  logEvent(diag.diagnosis_id, "report", {
    report_title: diag.report_title,
    report_elements_check: diag.report_elements_check,
    auto_review: diag.auto_review,
    degraded_reasons: diag.report_elements_check.missing,
    download_url: diag.report.download_url,
    report_meta: diag.report_meta,
  }, diag.diagnosis_revision);
  setStatus(diag, forceDegraded ? "degraded" : "succeeded", forceDegraded ? "degraded_release" : "finalize");
  logEvent(diag.diagnosis_id, "snapshot", diag, diag.diagnosis_revision);
}

function runDiagnosisPipeline(diag, opts = {}) {
  const base = opts.baseDelay || 0;
  if (opts.fromSupplement) {
    later(diag.diagnosis_id, base + 80, (d) => addStep(d, "parse_input", "resume", "恢复执行", 120, "RT-02"));
  }
  later(diag.diagnosis_id, base + 120, (d) => addStep(d, "orchestrator", "start", "总控启动", null, "RT-01"));
  later(diag.diagnosis_id, base + 220, (d) => addStep(d, "orchestrator", "end", "流程编排完成", 80, "RT-01"));
  later(diag.diagnosis_id, base + 320, (d) => addStep(d, "parse_input", "start", null, null, "RT-01"));
  later(diag.diagnosis_id, base + 760, (d) => {
    const missing = missingFieldsFor(d.features.normalized);
    addStep(d, "parse_input", "end", missing.length ? `缺少 ${missing.length} 项` : "7 项齐备", 420, "RT-02");
    if (missing.length) {
      attachClarificationInterrupt(d, missing);
      return;
    }
    later(d.diagnosis_id, 120, (x) => addStep(x, "retrieve", "start", null, null, "RT-04"));
    later(d.diagnosis_id, 700, (x) => {
      x.retrieval = {
        coverage: "covered",
        max_score: 0.72,
        top_k: 8,
        retry_used: false,
        hits: [
          { entry_id: "KB-HDF-003", fault_type: "HDF", title: "散热故障机理", snippet: "温差与转速组合导致散热能力下降…", score: 0.72 },
          { entry_id: "KB-PWF-011", fault_type: "PWF", title: "主轴功率异常", snippet: "扭矩波动与功率偏移的关联…", score: 0.61 },
          { entry_id: "KB-OSF-002", fault_type: "OSF", title: "过应力失效边界", snippet: "刀具磨损与扭矩的乘积阈值…", score: 0.58 },
        ],
      };
      addStep(x, "retrieve", "end", "命中 3 条", 580, "RT-04");
      later(x.diagnosis_id, 120, (y) => addStep(y, "diagnose", "start", null, null, "RT-05"));
      later(x.diagnosis_id, 700, (y) => {
        y.primary_type = "HDF";
        y.secondary_types = ["PWF"];
        y.confidence_breakdown = { rule: 0.9, coverage: 0.5, llm_self: 0.6, completeness: 1.0, penalties: 0.1, total: 0.625 };
        y.knowledge_status = "supported";
        y.evidence_refs = [
          { entry_id: "KB-HDF-003", title: "散热故障机理", fault_type: "HDF", feature: "temp_diff", value: 7.2, unit: "K" },
        ];
        addStep(y, "diagnose", "end", "规则命中 HDF，证据不唯一", 580, "RT-06");
        attachReviewInterrupt(y, 1, 0.625, "medium");
      });
    });
  });
}

function createDiagnosis({ inputType, features, deviceId, summary, autoReview = false }) {
  const diag = makeSnapshot({
    diagnosis_id: uid("dx"),
    device_id: deviceId,
    input_type: inputType,
    input_summary: summary,
    status: "running",
    features: {
      normalized: features,
      derived: deriveFeatures(features),
      completeness: (7 - missingFieldsFor(features, true).length) / 7,
      missing_fields: missingFieldsFor(features, true).map((f) => f.field),
      assumptions: [],
      data_quality_flags: [],
    },
    started_at: nowIso(),
    auto_review: autoReview,
    timings: { total_ms: 0, nodes: {} },
  });
  diagnoses.set(diag.diagnosis_id, diag);
  eventLogs.set(diag.diagnosis_id, []);
  if (allFeaturesPresent(features)) {
    fingerprints.set(fingerprintOf(features), diag.diagnosis_id);
  }
  runDiagnosisPipeline(diag);
  return diag;
}

/* ------------------------------ seed data ------------------------------ */

function seedReportDiagnosis(overrides) {
  const diag = makeSnapshot({
    diagnosis_id: uid("dx"),
    device_id: overrides.device_id,
    input_type: overrides.input_type || "form",
    status: overrides.status,
    version: 4,
    primary_type: overrides.primary_type || "HDF",
    secondary_types: overrides.secondary_types || ["PWF"],
    confidence: overrides.confidence ?? 0.91,
    confidence_level: overrides.confidence_level || "high",
    confidence_breakdown: { rule: 1, coverage: 1, llm_self: 0.82, completeness: 1, penalties: 0, total: overrides.confidence ?? 0.91 },
    knowledge_status: "supported",
    evidence_refs: [
      { entry_id: "KB-HDF-003", title: "散热故障机理", fault_type: "HDF", feature: "temp_diff", value: 7.2, unit: "K" },
      { entry_id: "KB-PWF-011", title: "主轴功率异常", fault_type: "PWF", feature: "power_w", value: 3927, unit: "W" },
    ],
    features: {
      normalized: {
        device_id: overrides.device_id,
        product_type: "M",
        air_temp_k: 298.1,
        process_temp_k: 305.3,
        rotational_speed_rpm: 1250,
        torque_nm: 30,
        tool_wear_min: 100,
      },
      derived: { temp_diff: 7.2, power_w: 3927, wear_torque: 3000 },
      completeness: 1,
      missing_fields: [],
      assumptions: [],
      data_quality_flags: [],
    },
    retrieval: {
      coverage: "covered",
      max_score: 0.72,
      top_k: 8,
      retry_used: true,
      hits: [
        { entry_id: "KB-HDF-003", fault_type: "HDF", title: "散热故障机理", snippet: "温差与转速组合导致散热能力下降…", score: 0.72 },
        { entry_id: "KB-PWF-011", fault_type: "PWF", title: "主轴功率异常", snippet: "扭矩波动与功率偏移的关联…", score: 0.61 },
      ],
    },
    auto_review: overrides.auto_review || false,
    retry_count: 1,
    report_elements_check: overrides.report_elements_check || {
      passed: true,
      present: ["诊断结论", "置信度与分级", "关键数据特征", "判断依据", "鉴别诊断", "维修与处置建议", "数据质量与假设", "免责声明与知识边界"],
      missing: [],
      report_retry_count: 0,
    },
    report_retry_count: 0,
    duration_ms: overrides.duration_ms || 8400,
    trace_steps: [
      { step_id: uid("stp"), node: "parse_input", event: "end", rule_id: "RT-01", revision: 1, summary: "7 项齐备", duration_ms: 420, created_at: nowIso() },
      { step_id: uid("stp"), node: "retrieve", event: "end", rule_id: "RT-04", revision: 1, summary: "命中 3 条", duration_ms: 820, created_at: nowIso() },
      { step_id: uid("stp"), node: "diagnose", event: "end", rule_id: "RT-06", revision: 1, summary: "规则命中 HDF", duration_ms: 1900, created_at: nowIso() },
      { step_id: uid("stp"), node: "report", event: "end", rule_id: "RT-15", revision: 1, summary: "8 要素齐备", duration_ms: 1200, created_at: nowIso() },
    ],
    timings: { total_ms: overrides.duration_ms || 8400, nodes: { parse_input: 420, retrieve: 820, diagnose: 1900, report: 1200 } },
    report_title: `${overrides.device_id} ${overrides.primary_type || "HDF"} 诊断报告`,
    report_meta: {
      template_version: "tpl-v1.2",
      prompt_version: "prompt-v1.3",
      kb_version: "kb-v1.0.0",
      model_name: "deepseek-chat",
      auto_review: overrides.auto_review || false,
      generated_at: nowIso(),
      degraded_reasons: overrides.report_elements_check?.missing || [],
    },
    created_at: overrides.created_at || nowIso(),
    started_at: overrides.created_at || nowIso(),
    finished_at: nowIso(),
  });
  diag.report = { markdown: buildReport(diag), download_url: `${BASE}/diagnoses/${diag.diagnosis_id}/report.md` };
  diagnoses.set(diag.diagnosis_id, diag);
  eventLogs.set(diag.diagnosis_id, []);
  return diag;
}

function seedAll() {
  const base = Date.now();
  seedReportDiagnosis({ device_id: "3号机", status: "succeeded", confidence: 0.91, confidence_level: "high", created_at: new Date(base - 8 * 60000).toISOString() });
  seedReportDiagnosis({
    device_id: "7号机",
    status: "degraded",
    confidence: 0.78,
    confidence_level: "medium",
    primary_type: "PWF",
    created_at: new Date(base - 26 * 60000).toISOString(),
    report_elements_check: { passed: false, present: ["诊断结论", "置信度与分级", "关键数据特征", "判断依据", "鉴别诊断", "维修与处置建议", "免责声明与知识边界"], missing: ["数据质量与假设"], report_retry_count: 1 },
  });
  seedReportDiagnosis({
    device_id: "9号机",
    status: "degraded_review",
    confidence: 0.58,
    confidence_level: "medium",
    auto_review: true,
    created_at: new Date(base - 47 * 60000).toISOString(),
    report_elements_check: { passed: false, present: ["诊断结论", "置信度与分级", "关键数据特征", "判断依据", "鉴别诊断", "维修与处置建议", "免责声明与知识边界"], missing: ["数据质量与假设"], report_retry_count: 0 },
  });
  seedReportDiagnosis({ device_id: "30号机", status: "succeeded", confidence: 0.88, confidence_level: "high", created_at: new Date(base - 2 * 3600000).toISOString() });
  fingerprints.set(
    fingerprintOf({ device_id: "30号机", product_type: "M", air_temp_k: 298.1, process_temp_k: 305.3, rotational_speed_rpm: 1250, torque_nm: 30, tool_wear_min: 100 }),
    [...diagnoses.values()].find((d) => d.device_id === "30号机").diagnosis_id,
  );

  const failed = makeSnapshot({
    diagnosis_id: uid("dx"),
    device_id: "2号机",
    input_type: "csv_single",
    input_summary: { file_name: "巡检_10月.csv", row_no: 37, text_excerpt: null },
    status: "failed_timeout",
    version: 5,
    duration_ms: 15000,
    error: { code: "TIMEOUT", message: "本次诊断超过 15 秒上限，系统已熔断，未生成报告。", node: "diagnose", recoverable: true },
    features: {
      normalized: { device_id: "2号机", product_type: "L", air_temp_k: 300.2, process_temp_k: 309.1, rotational_speed_rpm: 1400, torque_nm: 55, tool_wear_min: 210 },
      derived: { temp_diff: 8.9, power_w: 8063, wear_torque: 11550 },
      completeness: 1,
      missing_fields: [],
      assumptions: [],
      data_quality_flags: [],
    },
    trace_steps: [
      { step_id: uid("stp"), node: "parse_input", event: "end", rule_id: "RT-01", revision: 1, summary: "7 项齐备", duration_ms: 420, created_at: nowIso() },
      { step_id: uid("stp"), node: "retrieve", event: "end", rule_id: "RT-04", revision: 1, summary: "命中 2 条", duration_ms: 820, created_at: nowIso() },
      { step_id: uid("stp"), node: "diagnose", event: "timeout", rule_id: "RT-09", revision: 1, summary: "超时中断", duration_ms: 13760, created_at: nowIso() },
    ],
    timings: { total_ms: 15000, nodes: { parse_input: 420, retrieve: 820, diagnose: 13760 } },
    created_at: new Date(base - 70 * 60000).toISOString(),
    started_at: new Date(base - 70 * 60000).toISOString(),
    finished_at: nowIso(),
  });
  diagnoses.set(failed.diagnosis_id, failed);
  eventLogs.set(failed.diagnosis_id, []);

  const failedNode = makeSnapshot({
    diagnosis_id: uid("dx"),
    device_id: "5号机",
    input_type: "form",
    status: "failed",
    version: 3,
    duration_ms: 2300,
    error: { code: "INDEX_UNAVAILABLE", message: "知识索引不可读且无法降级，诊断已终止。", node: "retrieve", recoverable: true },
    features: {
      normalized: { device_id: "5号机", product_type: "H", air_temp_k: 297.5, process_temp_k: 306.2, rotational_speed_rpm: 1600, torque_nm: 48, tool_wear_min: 80 },
      derived: { temp_diff: 8.7, power_w: 8042, wear_torque: 3840 },
      completeness: 1,
      missing_fields: [],
      assumptions: [],
      data_quality_flags: [],
    },
    trace_steps: [{ step_id: uid("stp"), node: "retrieve", event: "error", rule_id: "RT-04", revision: 1, summary: "索引不可读", duration_ms: 900, created_at: nowIso() }],
    timings: { total_ms: 2300, nodes: { parse_input: 400, retrieve: 900 } },
    created_at: new Date(base - 95 * 60000).toISOString(),
    started_at: new Date(base - 95 * 60000).toISOString(),
    finished_at: nowIso(),
  });
  diagnoses.set(failedNode.diagnosis_id, failedNode);
  eventLogs.set(failedNode.diagnosis_id, []);

  const aborted = makeSnapshot({
    diagnosis_id: uid("dx"),
    device_id: "6号机",
    input_type: "nl",
    status: "aborted",
    version: 3,
    human_decision: "abort",
    error: { code: "HUMAN_ABORT", message: "用户放弃本次诊断，未生成报告。", node: null, recoverable: true },
    features: { normalized: { device_id: "6号机" }, derived: {}, completeness: 0.14, missing_fields: ["product_type", "air_temp_k", "process_temp_k", "rotational_speed_rpm", "torque_nm", "tool_wear_min"], assumptions: [], data_quality_flags: [] },
    created_at: new Date(base - 120 * 60000).toISOString(),
    started_at: new Date(base - 120 * 60000).toISOString(),
    finished_at: nowIso(),
  });
  diagnoses.set(aborted.diagnosis_id, aborted);
  eventLogs.set(aborted.diagnosis_id, []);

  const expired = makeSnapshot({
    diagnosis_id: uid("dx"),
    device_id: "8号机",
    input_type: "nl",
    status: "expired",
    version: 4,
    interrupt: {
      type: "clarification",
      expires_at: new Date(base - 5 * 60000).toISOString(),
      review_round: 0,
      version: 3,
      payload: {
        created_at: new Date(base - 40 * 60000).toISOString(),
        missing_fields: [
          { field: "air_temp_k", label: "空气温度", unit: "K", example: 298.1, reason: "MISSING" },
          { field: "torque_nm", label: "扭矩", unit: "Nm", example: 42.8, reason: "MISSING" },
        ],
        partial_features: { device_id: "8号机", product_type: "M", rotational_speed_rpm: 1500 },
        device_id: "8号机",
      },
    },
    features: { normalized: { device_id: "8号机", product_type: "M", rotational_speed_rpm: 1500 }, derived: {}, completeness: 0.43, missing_fields: ["air_temp_k", "torque_nm"], assumptions: [], data_quality_flags: [] },
    created_at: new Date(base - 40 * 60000).toISOString(),
    started_at: new Date(base - 40 * 60000).toISOString(),
    finished_at: nowIso(),
  });
  diagnoses.set(expired.diagnosis_id, expired);
  eventLogs.set(expired.diagnosis_id, []);

  const clarify = makeSnapshot({
    diagnosis_id: uid("dx"),
    device_id: "4号机",
    input_type: "nl",
    status: "waiting_human",
    version: 2,
    features: { normalized: { device_id: "4号机", torque_nm: 55, tool_wear_min: 120 }, derived: {}, completeness: 0.43, missing_fields: ["product_type", "air_temp_k", "process_temp_k", "rotational_speed_rpm"], assumptions: [], data_quality_flags: [] },
    interrupt: {
      type: "clarification",
      expires_at: new Date(base + 18 * 60000).toISOString(),
      review_round: 0,
      version: 2,
      payload: {
        created_at: new Date(base - 2 * 60000).toISOString(),
        missing_fields: [
          { field: "product_type", label: "产品类型", unit: null, example: "M", reason: "MISSING" },
          { field: "air_temp_k", label: "空气温度", unit: "K", example: 298.1, reason: "MISSING" },
          { field: "process_temp_k", label: "工艺温度", unit: "K", example: 308.6, reason: "MISSING" },
          { field: "rotational_speed_rpm", label: "转速", unit: "rpm", example: 1551, reason: "MISSING" },
        ],
        partial_features: { device_id: "4号机", torque_nm: 55, tool_wear_min: 120 },
        device_id: "4号机",
      },
    },
    trace_steps: [{ step_id: uid("stp"), node: "parse_input", event: "interrupt", rule_id: "RT-02", revision: 1, summary: "缺少 4 项", duration_ms: 400, created_at: nowIso() }],
    timings: { total_ms: 400, nodes: { parse_input: 400 } },
    created_at: new Date(base - 2 * 60000).toISOString(),
    started_at: new Date(base - 2 * 60000).toISOString(),
  });
  diagnoses.set(clarify.diagnosis_id, clarify);
  eventLogs.set(clarify.diagnosis_id, []);

  const review = makeSnapshot({
    diagnosis_id: uid("dx"),
    device_id: "11号机",
    input_type: "form",
    status: "waiting_human",
    version: 3,
    primary_type: "HDF",
    secondary_types: ["PWF"],
    confidence: 0.62,
    confidence_level: "medium",
    confidence_breakdown: { rule: 1, coverage: 0.5, llm_self: 0.55, completeness: 1, penalties: 0.1, total: 0.62 },
    knowledge_status: "supported",
    evidence_refs: [{ entry_id: "KB-HDF-003", title: "散热故障机理", fault_type: "HDF", feature: "temp_diff", value: 7.2, unit: "K" }],
    features: { normalized: { device_id: "11号机", product_type: "M", air_temp_k: 298.1, process_temp_k: 305.3, rotational_speed_rpm: 1250, torque_nm: 30, tool_wear_min: 100 }, derived: { temp_diff: 7.2, power_w: 3927, wear_torque: 3000 }, completeness: 1, missing_fields: [], assumptions: [], data_quality_flags: [] },
    interrupt: {
      type: "review",
      expires_at: new Date(base + 22 * 60000).toISOString(),
      review_round: 1,
      version: 3,
      payload: {
        created_at: new Date(base - 1 * 60000).toISOString(),
        primary_type: "HDF",
        secondary_types: ["PWF"],
        confidence: 0.62,
        confidence_level: "medium",
        confidence_breakdown: { rule: 1, coverage: 0.5, llm_self: 0.55, completeness: 1, penalties: 0.1, total: 0.62 },
        evidence_refs: [{ entry_id: "KB-HDF-003", title: "散热故障机理", fault_type: "HDF", feature: "temp_diff", value: 7.2, unit: "K" }],
        reason: "刀具磨损值与温度组合仅弱相关，规则证据不唯一。",
        missing_fields: [],
        review_round: 1,
      },
    },
    trace_steps: [{ step_id: uid("stp"), node: "diagnose", event: "interrupt", rule_id: "RT-06", revision: 1, summary: "置信度不足，等待确认", duration_ms: 1900, created_at: nowIso() }],
    timings: { total_ms: 3120, nodes: { parse_input: 420, retrieve: 820, diagnose: 1900 } },
    created_at: new Date(base - 1 * 60000).toISOString(),
    started_at: new Date(base - 1 * 60000).toISOString(),
  });
  diagnoses.set(review.diagnosis_id, review);
  eventLogs.set(review.diagnosis_id, []);
}

seedAll();

/* ------------------------------ evaluations ------------------------------ */

const evalBatch = {
  eval_batch_id: "evb_01J8AI4I2026",
  dataset_version: "ai4i-2020-v1",
  prompt_version: "prompt-v1.3",
  kb_version: "kb-v1.0.0",
  model_name: "deepseek-chat",
  sample_total: 120,
  edge_sample_total: 20,
  report_count: 119,
  failed_timeout_count: 1,
  accuracy: 0.9167,
  completeness_rate: 0.9625,
  timeout_rate: 0.0083,
  fabrication_rate: null,
  latency_sample_count: 118,
  latency_avg_ms: 8420,
  latency_p50_ms: 7900,
  latency_p95_ms: 11400,
  latency_max_ms: 14200,
  created_at: new Date(Date.now() - 30 * 60000).toISOString(),
};

const evalTrend = [
  { eval_batch_id: "evb_01J8AI4I2024", sample_total: 120, accuracy: 0.8917, completeness_rate: 0.9479, latency_avg_ms: 9100, latency_p95_ms: 12800, timeout_rate: 0.025, created_at: new Date(Date.now() - 7 * 86400000).toISOString() },
  { eval_batch_id: "evb_01J8AI4I2025", sample_total: 120, accuracy: 0.9083, completeness_rate: 0.9583, latency_avg_ms: 8800, latency_p95_ms: 12100, timeout_rate: 0.0167, created_at: new Date(Date.now() - 3 * 86400000).toISOString() },
  evalBatch,
];

const confusion = {
  row_labels: ["正常", "TWF", "HDF", "PWF", "OSF", "RNF"],
  predicted_labels: ["正常", "TWF", "HDF", "PWF", "OSF", "RNF", "未覆盖"],
  counts: [
    [30, 0, 0, 0, 0, 0, 0],
    [0, 17, 0, 0, 0, 0, 1],
    [0, 0, 19, 2, 0, 0, 0],
    [0, 0, 1, 20, 0, 0, 0],
    [0, 0, 0, 0, 18, 0, 1],
    [0, 0, 0, 0, 0, 10, 1],
  ],
};

const perClass = [
  { label: "正常", recall: 1, sample_count: 30 },
  { label: "TWF", recall: 0.9444, sample_count: 18 },
  { label: "HDF", recall: 0.9048, sample_count: 21 },
  { label: "PWF", recall: 0.9524, sample_count: 21 },
  { label: "OSF", recall: 0.9474, sample_count: 19 },
  { label: "RNF", recall: 0.9091, sample_count: 11 },
];

const badCases = [
  { sample_no: 61, sample_id: "12345", expected_primary: "HDF", predicted_primary: "PWF", confidence: 0.72, error_category: "rule_misjudge", latency_ms: 4100 },
  { sample_no: 74, sample_id: "EDGE-07", expected_primary: "OSF", predicted_primary: "未覆盖", confidence: 0.41, error_category: "retrieval_miss", latency_ms: 5300 },
  { sample_no: 88, sample_id: "EDGE-12", expected_primary: "TWF", predicted_primary: "RNF", confidence: 0.48, error_category: "feature_missing", latency_ms: 6700 },
  { sample_no: 93, sample_id: "12395", expected_primary: "PWF", predicted_primary: "HDF", confidence: 0.66, error_category: "llm_misjudge", latency_ms: 7900 },
  { sample_no: 101, sample_id: "EDGE-18", expected_primary: "HDF", predicted_primary: "OSF", confidence: 0.55, error_category: "report_missing_element", latency_ms: 11200 },
  { sample_no: 108, sample_id: "12410", expected_primary: "TWF", predicted_primary: "TWF", confidence: 0.9, error_category: "latency_exceeded", latency_ms: 12800 },
];

const tuning = [
  { params: { chunk_size: 300, overlap: 50, top_k: 5 }, top5_hit_rate: 0.88, kb_version: "kb-v1.0.0", created_at: new Date(Date.now() - 3 * 86400000).toISOString() },
  { params: { chunk_size: 400, overlap: 60, top_k: 8 }, top5_hit_rate: 0.91, kb_version: "kb-v1.0.0", created_at: new Date(Date.now() - 86400000).toISOString() },
  { params: { chunk_size: 380, overlap: 48, top_k: 8 }, top5_hit_rate: 0.92, kb_version: "kb-v1.0.0", created_at: new Date(Date.now() - 3600000).toISOString() },
];

const badCaseByNo = new Map(badCases.map((item) => [item.sample_no, item]));
const degradedNos = new Set([60, 62, 108]);
const allSamples = Array.from({ length: 120 }, (_, index) => {
  const sampleNo = index + 1;
  if (sampleNo === 120) {
    return {
      eval_sample_id: `evs_${sampleNo}`,
      eval_batch_id: evalBatch.eval_batch_id,
      sample_no: sampleNo,
      sample_id: "EDGE-20",
      dataset_split: "edge",
      expected_primary: "TWF",
      predicted_primary: null,
      correct: false,
      confidence: null,
      elements_present: 0,
      latency_ms: 15000,
      status: "failed_timeout",
      error_category: "latency_exceeded",
    };
  }
  const bad = badCaseByNo.get(sampleNo);
  const degraded = degradedNos.has(sampleNo);
  return {
    eval_sample_id: `evs_${sampleNo}`,
    eval_batch_id: evalBatch.eval_batch_id,
    sample_no: sampleNo,
    sample_id: bad?.sample_id || `UDI-${10000 + sampleNo}`,
    dataset_split: sampleNo > 110 ? "edge" : sampleNo > 100 ? "tuning" : "eval",
    expected_primary: bad?.expected_primary || (degraded ? "HDF" : "正常"),
    predicted_primary: bad ? bad.predicted_primary : degraded ? "PWF" : "正常",
    correct: bad ? false : !degraded,
    confidence: bad?.confidence ?? (degraded ? 0.66 : 0.96),
    elements_present: degraded ? 7 : 8,
    latency_ms: bad?.latency_ms ?? (degraded ? 10400 : 6800 + ((sampleNo * 173) % 3800)),
    status: degraded ? "degraded" : "succeeded",
    error_category: bad?.error_category ?? (degraded ? "retrieval_miss" : null),
  };
});

/* ------------------------------ batch ------------------------------ */

function batchCounts(rows) {
  const counts = { pending: 0, running: 0, succeeded: 0, degraded: 0, degraded_review: 0, failed: 0, failed_timeout: 0, cancelled: 0 };
  for (const row of rows) counts[row.status] += 1;
  return counts;
}

function batchSnapshot(batch) {
  const rows = batchRows.get(batch.batch_task_id) || [];
  const counts = batchCounts(rows);
  const completed = counts.succeeded + counts.degraded + counts.degraded_review + counts.failed + counts.failed_timeout;
  return {
    batch_task_id: batch.batch_task_id,
    file_name: batch.file_name,
    total_rows: batch.total_rows,
    status: batch.status,
    default_device_id: batch.default_device_id,
    counts,
    completed_rows: completed + counts.cancelled,
    progress: Math.min(1, completed / Math.max(1, batch.total_rows)),
    cancel_requested: batch.cancel_requested,
    timeout_deadline: batch.timeout_deadline,
    created_at: batch.created_at,
    started_at: batch.started_at,
    finished_at: batch.finished_at,
    error_code: batch.error_code,
  };
}

function startBatch(batch) {
  const rows = batchRows.get(batch.batch_task_id);
  batch.status = "running";
  batch.started_at = nowIso();
  logEvent(batch.batch_task_id, "batch_snapshot", batchSnapshot(batch), null);
  let index = 0;
  const timer = setInterval(() => {
    if (!batches.has(batch.batch_task_id)) {
      clearInterval(timer);
      return;
    }
    if (batch.cancel_requested) {
      for (const row of rows) {
        if (row.status === "pending") {
          row.status = "cancelled";
          row.error_code = null;
          logEvent(batch.batch_task_id, "row_status", row, null);
        }
      }
      batch.status = "cancelled";
      batch.finished_at = nowIso();
      clearInterval(timer);
      batchTimers.delete(batch.batch_task_id);
      logEvent(batch.batch_task_id, "batch_status", { status: "cancelled", counts: batchCounts(rows), finished_at: batch.finished_at, cancel_requested: true, error_code: null }, null);
      logEvent(batch.batch_task_id, "batch_snapshot", batchSnapshot(batch), null);
      setTimeout(() => closeSubscribers(batch.batch_task_id), 80);
      return;
    }
    if (index >= rows.length) {
      clearInterval(timer);
      batchTimers.delete(batch.batch_task_id);
      const counts = batchCounts(rows);
      const hasFailure = counts.failed + counts.failed_timeout > 0;
      batch.status = hasFailure ? "partially_failed" : "completed";
      batch.finished_at = nowIso();
      logEvent(batch.batch_task_id, "batch_status", { status: batch.status, counts, finished_at: batch.finished_at, cancel_requested: false, error_code: null }, null);
      logEvent(batch.batch_task_id, "batch_snapshot", batchSnapshot(batch), null);
      setTimeout(() => closeSubscribers(batch.batch_task_id), 80);
      return;
    }
    const row = rows[index];
    index += 1;
    row.status = "running";
    logEvent(batch.batch_task_id, "row_status", row, null);
    logEvent(batch.batch_task_id, "batch_progress", { completed_rows: batchSnapshot(batch).completed_rows, total_rows: batch.total_rows, progress: batchSnapshot(batch).progress, counts: batchCounts(rows) }, null);
    const finish = (status, extra = {}) => {
      row.status = status;
      Object.assign(row, extra);
      const autoReview = status === "degraded_review" || extra.auto_review === true;
      if (status === "succeeded" || status === "degraded" || status === "degraded_review") {
        const diag = makeSnapshot({
          diagnosis_id: uid("dx"),
          device_id: row.device_id || batch.default_device_id || "未命名设备",
          input_type: "csv_batch",
          status,
          version: 3,
          primary_type: "HDF",
          secondary_types: ["PWF"],
          confidence: status === "succeeded" ? 0.9 : 0.62,
          confidence_level: status === "succeeded" ? "high" : "medium",
          confidence_breakdown: { rule: 1, coverage: 0.5, llm_self: 0.7, completeness: 1, penalties: 0, total: status === "succeeded" ? 0.9 : 0.62 },
          knowledge_status: "supported",
          features: { normalized: { device_id: row.device_id || batch.default_device_id, product_type: "M", air_temp_k: 298.1, process_temp_k: 305.3, rotational_speed_rpm: 1250, torque_nm: 30, tool_wear_min: 100 }, derived: { temp_diff: 7.2, power_w: 3927, wear_torque: 3000 }, completeness: 1, missing_fields: [], assumptions: [], data_quality_flags: [] },
          auto_review: autoReview,
          batch: { batch_task_id: batch.batch_task_id, row_id: row.row_id, row_no: row.row_no },
          duration_ms: status === "degraded" ? 9800 : 4200,
          report_elements_check: status === "succeeded" ? { passed: true, present: ["诊断结论", "置信度与分级", "关键数据特征", "判断依据", "鉴别诊断", "维修与处置建议", "数据质量与假设", "免责声明与知识边界"], missing: [], report_retry_count: 0 } : { passed: false, present: ["诊断结论", "置信度与分级", "关键数据特征", "判断依据", "鉴别诊断", "维修与处置建议", "免责声明与知识边界"], missing: ["数据质量与假设"], report_retry_count: 0 },
          created_at: nowIso(),
          started_at: nowIso(),
          finished_at: nowIso(),
        });
        diag.report = { markdown: buildReport(diag), download_url: `${BASE}/diagnoses/${diag.diagnosis_id}/report.md` };
        diagnoses.set(diag.diagnosis_id, diag);
        eventLogs.set(diag.diagnosis_id, []);
        row.diagnosis_id = diag.diagnosis_id;
        row.report_summary = autoReview ? "待人工复核（批量模式）：疑似 PWF…" : status === "degraded" ? "缺项降级：疑似 HDF…" : "疑似 HDF，置信度 0.90";
        row.auto_review = autoReview;
        row.duration_ms = diag.duration_ms;
      }
      logEvent(batch.batch_task_id, "row_status", row, null);
      logEvent(batch.batch_task_id, "batch_progress", { completed_rows: batchSnapshot(batch).completed_rows, total_rows: batch.total_rows, progress: batchSnapshot(batch).progress, counts: batchCounts(rows) }, null);
    };
    const n = row.row_no;
    if (n === 4) finish("degraded_review");
    else if (n === 8) finish("degraded", { duration_ms: 8800, auto_review: true });
    else if (n === 10) finish("failed", { error_field: "torque_nm", error_code: "FIELD_INVALID", duration_ms: 120 });
    else if (n === 11) finish("failed_timeout", { error_code: "TIMEOUT", duration_ms: 15000, report_summary: null });
    else finish("succeeded", { duration_ms: 3800 + ((n * 137) % 2400) });
  }, 260);
  batchTimers.set(batch.batch_task_id, timer);
}

/* ------------------------------ SSE ------------------------------ */

function openStream(req, res, streamId, kind, snapshotEvent) {
  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
    "X-Request-Id": `req_${randomUUID().replace(/-/g, "").slice(0, 20)}`,
  });
  res.write("retry: 3000\n\n");

  const lastId = Number(req.headers["last-event-id"] || -1);
  const log = eventLogs.get(streamId) || [];

  if (!Number.isFinite(lastId) || lastId < 0) {
    const currentSeq = log.length;
    writeSse(res, {
      seq: currentSeq,
      stream_kind: kind,
      stream_id: streamId,
      type: snapshotEvent.type,
      revision: snapshotEvent.revision ?? null,
      occurred_at: nowIso(),
      payload: snapshotEvent.payload,
    });
  } else {
    for (const event of log.filter((e) => e.seq > lastId)) writeSse(res, event);
  }

  const entry = subscribers.get(streamId) || { kind, res: new Set(), lastSent: new Map() };
  entry.kind = kind;
  entry.res.add(res);
  subscribers.set(streamId, entry);

  const heartbeat = setInterval(() => {
    if (res.writableEnded) {
      clearInterval(heartbeat);
      return;
    }
    writeSse(res, { seq: null, stream_kind: kind, stream_id: streamId, type: "heartbeat", revision: null, occurred_at: nowIso(), payload: { server_time: nowIso() } });
  }, 15000);

  req.on("close", () => {
    clearInterval(heartbeat);
    entry.res.delete(res);
    if (!entry.res.size) subscribers.delete(streamId);
  });
}

/* ------------------------------ extraction ------------------------------ */

function extractFromText(text) {
  const features = { device_id: null, product_type: null, air_temp_k: null, process_temp_k: null, rotational_speed_rpm: null, torque_nm: null, tool_wear_min: null };
  const device = /([\u4e00-\u9fa5A-Za-z0-9_-]{1,20}号机)/.exec(text);
  if (device) features.device_id = device[1];
  const product = /(?:产品类型|型号)\s*([LMH])(?![A-Za-z])/.exec(text) || /(?:^|[\s，,、])([LMH])\s*型/.exec(text);
  if (product) features.product_type = product[1];
  const num = (re) => {
    const m = re.exec(text);
    return m ? Number(m[1]) : null;
  };
  features.air_temp_k = num(/(?:空气温度|气温)\s*([\d.]+)/);
  features.process_temp_k = num(/(?:工艺温度|加工温度)\s*([\d.]+)/);
  features.rotational_speed_rpm = num(/(?:转速|速度)\s*(?:大概|约)?\s*(\d{2,4})/);
  features.torque_nm = num(/(?:扭矩|转矩)\s*([\d.]+)/);
  features.tool_wear_min = num(/(?:刀具磨损|磨损)\s*([\d.]+)/);
  const missing = missingFieldsFor(features, true);
  const status = missing.length === 0 ? "ok" : missing.length === 7 ? "failed" : "partial";
  return {
    extraction_status: status,
    features,
    missing_fields: missing,
    recommended_action: status === "ok" ? "confirm" : status === "failed" ? "use_form" : "clarify",
  };
}

/* ------------------------------ router ------------------------------ */

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
  const path = url.pathname;
  const method = req.method || "GET";

  if (method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  if (!path.startsWith(BASE)) {
    sendError(res, 404, "NOT_FOUND", "接口不存在");
    return;
  }
  const route = path.slice(BASE.length) || "/";

  try {
    if (route === "/_mock/reset" && method === "POST") {
      sendJson(res, 200, { ok: true });
      return;
    }
    if (route === "/_mock/streams/drop-all" && method === "POST") {
      const dropped = [...subscribers.keys()];
      for (const id of dropped) closeSubscribers(id);
      sendJson(res, 200, { ok: true, dropped });
      return;
    }
    if (route.startsWith("/_mock/streams/") && route.endsWith("/drop") && method === "POST") {
      const id = route.split("/")[3];
      closeSubscribers(id);
      sendJson(res, 200, { ok: true, dropped: id });
      return;
    }

    if (route === "/health" && method === "GET") {
      sendJson(res, 200, {
        status: "ok",
        version: "1.2.0-mock",
        checked_at: nowIso(),
        dependencies: { database: "ok", checkpoint_store: "ok", vector_index: "ok", embedding_model: "ok", llm_config: "ok" },
      });
      return;
    }

    if (route === "/auth/register" && method === "POST") {
      const body = await readJson(req);
      if (!body.username || !/^[A-Za-z0-9_]{3,32}$/.test(body.username)) {
        sendError(res, 422, "VALIDATION_FAILED", "用户名需为 3–32 位字母、数字或下划线");
        return;
      }
      if (!body.password || body.password.length < 8) {
        sendError(res, 422, "WEAK_PASSWORD", "密码至少 8 位，且包含字母与数字");
        return;
      }
      if (body.password !== body.password_confirm) {
        sendError(res, 422, "VALIDATION_FAILED", "两次输入的密码不一致");
        return;
      }
      if (users.has(body.username)) {
        sendError(res, 409, "USERNAME_TAKEN", "用户名已存在");
        return;
      }
      const user = { user_id: uid("usr"), username: body.username, password: body.password, created_at: nowIso() };
      users.set(user.username, user);
      const token = randomUUID();
      sessions.set(token, user);
      res.setHeader("Set-Cookie", `edg_session=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400`);
      sendJson(res, 201, { user: { user_id: user.user_id, username: user.username, created_at: user.created_at, last_login_at: nowIso() } });
      return;
    }

    if (route === "/auth/login" && method === "POST") {
      const body = await readJson(req);
      const key = String(body.username || "");
      const failure = loginFailures.get(key) || { count: 0, until: 0 };
      if (failure.until > Date.now()) {
        const retry = Math.ceil((failure.until - Date.now()) / 1000);
        sendJson(
          res,
          423,
          { error: { code: "AUTH_LOCKED", message: "尝试次数过多，请稍后重试", request_id: `req_${randomUUID().replace(/-/g, "").slice(0, 20)}` } },
          { "Retry-After": String(retry) },
        );
        return;
      }
      const user = users.get(body.username);
      if (!user || user.password !== body.password) {
        failure.count += 1;
        if (failure.count >= 5) {
          failure.until = Date.now() + 300 * 1000;
          failure.count = 0;
          loginFailures.set(key, failure);
          sendJson(
            res,
            423,
            { error: { code: "AUTH_LOCKED", message: "尝试次数过多，请在 05:00 后重试", request_id: `req_${randomUUID().replace(/-/g, "").slice(0, 20)}` } },
            { "Retry-After": "300" },
          );
          return;
        }
        loginFailures.set(key, failure);
        sendError(res, 401, "AUTH_INVALID_CREDENTIALS", "用户名或密码错误");
        return;
      }
      loginFailures.delete(key);
      const token = randomUUID();
      sessions.set(token, user);
      res.setHeader("Set-Cookie", `edg_session=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400`);
      sendJson(res, 200, { user: { user_id: user.user_id, username: user.username, created_at: user.created_at, last_login_at: nowIso() } });
      return;
    }

    const user = requireUser(req, res);
    if (!user) return;

    if (route === "/auth/logout" && method === "POST") {
      const token = parseCookies(req).edg_session;
      if (token) sessions.delete(token);
      res.setHeader("Set-Cookie", "edg_session=; Path=/; Max-Age=0");
      res.writeHead(204);
      res.end();
      return;
    }

    if (route === "/auth/me" && method === "GET") {
      sendJson(res, 200, { user: { user_id: user.user_id, username: user.username, created_at: user.created_at, last_login_at: user.last_login_at || nowIso() } });
      return;
    }

    if (route === "/system/config" && method === "GET") {
      sendJson(res, 200, {
        limits: { upload_max_bytes: 5242880, csv_max_rows: 500, page_size_default: 20, page_size_max: 100, device_id_max_length: 64 },
        timeouts: { global_timeout_seconds: 15, interrupt_ttl_minutes: 30, batch_task_timeout_minutes: 60, llm_call_budget_seconds: 5, llm_connect_timeout_seconds: 2 },
        enums: {
          input_types: ["csv_single", "csv_batch", "form", "nl", "chat"],
          diagnosis_status: ["running", "waiting_human", "succeeded", "degraded", "degraded_review", "aborted", "failed", "failed_timeout", "expired"],
          batch_task_status: ["queued", "running", "completed", "partially_failed", "failed", "cancelled", "timed_out"],
          batch_row_status: ["pending", "running", "succeeded", "degraded", "degraded_review", "failed", "failed_timeout", "cancelled"],
          primary_types: ["正常", "TWF", "HDF", "PWF", "OSF", "RNF", "未覆盖"],
          confidence_levels: ["high", "medium", "low"],
          decisions: ["confirm", "supplement", "abort"],
        },
        features: { evaluation_web: true },
      });
      return;
    }

    if (route === "/uploads" && method === "POST") {
      const buf = await readBody(req);
      const file = parseMultipart(buf, req.headers["content-type"]);
      if (!file) {
        sendError(res, 422, "FILE_EMPTY", "未读取到上传文件，请重新选择 CSV 文件。");
        return;
      }
      if (file.content.length > 5 * 1024 * 1024) {
        sendError(res, 413, "FILE_TOO_LARGE", "文件超过 5MB 上限，请拆分后重试。");
        return;
      }
      if (!/\.csv$/i.test(file.filename)) {
        sendError(res, 415, "FILE_TYPE_NOT_ALLOWED", "仅支持 .csv 文件，请重新选择。");
        return;
      }
      const { headers, rows } = parseCsv(file.content.toString("utf8"));
      if (!headers.length) {
        sendError(res, 422, "FILE_EMPTY", "未识别到有效表头，请确认首行为列名。");
        return;
      }
      if (rows.length > 500) {
        sendError(res, 422, "CSV_ROW_LIMIT_EXCEEDED", "文件超过 500 行上限，请拆分后重试。");
        return;
      }
      const upload = {
        upload_id: uid("up"),
        file_name: file.filename,
        size_bytes: file.content.length,
        encoding: "utf-8",
        row_count: rows.length,
        headers,
        preview_rows: rows.slice(0, 5).map((row) => Object.fromEntries(headers.map((h, i) => [h, row[i] ?? ""]))),
        header_signature: `sha256:${randomUUID().replace(/-/g, "")}`,
        suggested_mapping: suggestMapping(headers),
        matched_scheme: null,
        issues: [],
        rows,
      };
      uploads.set(upload.upload_id, upload);
      sendJson(res, 201, upload);
      return;
    }

    if (route.startsWith("/uploads/") && route.endsWith("/mapping/preview") && method === "POST") {
      const id = route.split("/")[2];
      const upload = uploads.get(id);
      if (!upload) {
        sendError(res, 404, "UPLOAD_NOT_FOUND", "上传记录不存在，请重新上传。");
        return;
      }
      const body = await readJson(req);
      const mapping = body.mapping || {};
      const missing = Object.entries(mapping).filter(([, col]) => !col).map(([key]) => key);
      const rows = upload.rows.map((row, idx) => {
        const n = normalizeRow(upload.headers, row, mapping, body.default_device_id);
        return { row_no: idx + 1, device_id: n.device_id, features: n, derived: deriveFeatures(n), data_quality_flags: [] };
      });
      if (body.mode === "single") {
        const rowNo = Number(body.row_no || 1);
        const target = rows[rowNo - 1];
        if (!target || !target.device_id) {
          sendError(res, 422, "DEVICE_ID_INVALID", "设备标识缺失，请补充批次统一设备标识。");
          return;
        }
        sendJson(res, 200, { valid: missing.length === 0, missing_required: missing, errors: [], preview: [target, ...rows.filter((r) => r.row_no !== rowNo)].slice(0, 3), row_summary: null });
        return;
      }
      const invalid = rows.filter((r) => !r.device_id || r.features.torque_nm === null || r.features.air_temp_k === null);
      sendJson(res, 200, {
        valid: missing.length === 0,
        missing_required: missing,
        errors: invalid.slice(0, 5).map((r) => ({ code: "FIELD_MISSING", message: `第 ${r.row_no} 行缺少必填数据`, column: null, row_no: r.row_no })),
        preview: rows.slice(0, 3),
        row_summary: {
          total: rows.length,
          valid: rows.length - invalid.length,
          invalid: invalid.length,
          first_invalid: invalid.slice(0, 5).map((r) => ({ row_no: r.row_no, field: "device_id", code: "FIELD_MISSING", message: `第 ${r.row_no} 行缺少设备标识` })),
        },
      });
      return;
    }

    if (route.startsWith("/uploads/") && method === "GET") {
      const id = route.split("/")[2];
      const upload = uploads.get(id);
      if (!upload) {
        sendError(res, 404, "UPLOAD_NOT_FOUND", "上传记录不存在，请重新上传。");
        return;
      }
      const { rows, ...rest } = upload;
      sendJson(res, 200, rest);
      return;
    }

    if (route === "/nl/extract" && method === "POST") {
      const body = await readJson(req);
      if (!body.text || String(body.text).length > 2000) {
        sendError(res, 422, "VALIDATION_FAILED", "描述需为 1–2000 字符");
        return;
      }
      const result = extractFromText(String(body.text));
      const message =
        result.extraction_status === "ok"
          ? "已抽取 7 项，请确认后开始诊断"
          : result.extraction_status === "partial"
            ? `已抽取 ${7 - result.missing_fields.length} 项，缺失字段可补充后再提交`
            : "未能识别足够字段，请补充描述或改用表单";
      sendJson(res, 200, {
        ...result,
        text: body.text,
        field_confidence: Object.fromEntries(Object.keys(result.features).map((k) => [k, result.features[k] === null ? 0 : 0.9])),
        source_spans: [],
        qualitative_cues: [],
        message,
      });
      return;
    }

    if (route === "/chat/sessions" && method === "POST") {
      const session = { session_id: uid("cht"), status: "draft", diagnosis_id: null, messages: [], created_at: nowIso(), updated_at: nowIso() };
      chatSessions.set(session.session_id, session);
      sendJson(res, 201, { session_id: session.session_id, status: "draft", created_at: session.created_at });
      return;
    }

    if (route.startsWith("/chat/sessions/") && method === "GET") {
      const id = route.split("/")[3];
      const session = chatSessions.get(id);
      if (!session) {
        sendError(res, 404, "CHAT_SESSION_NOT_FOUND", "会话不存在，请新建对话");
        return;
      }
      sendJson(res, 200, {
        session_id: session.session_id,
        status: session.status,
        diagnosis_id: session.diagnosis_id,
        diagnosis_status: session.diagnosis_id ? diagnoses.get(session.diagnosis_id)?.status || null : null,
        created_at: session.created_at,
        updated_at: session.updated_at || session.created_at,
        messages: session.messages,
      });
      return;
    }

    if (route.startsWith("/chat/sessions/") && route.endsWith("/messages") && method === "POST") {
      const id = route.split("/")[3];
      const session = chatSessions.get(id);
      if (!session) {
        sendError(res, 404, "CHAT_SESSION_NOT_FOUND", "会话不存在，请新建对话");
        return;
      }
      const diag = session.diagnosis_id ? diagnoses.get(session.diagnosis_id) : null;
      if (session.status === "terminal" || (diag && ["succeeded", "degraded", "degraded_review", "aborted", "failed", "failed_timeout", "expired"].includes(diag.status))) {
        sendError(res, 409, "CHAT_SESSION_CLOSED", "本对话已结束，请新建对话");
        return;
      }
      if (diag?.status === "waiting_human" && diag.interrupt?.type === "review") {
        sendError(res, 409, "CHAT_DECISION_REQUIRED", "当前需要确认结论，暂不接受自由文本");
        return;
      }
      if (diag?.status === "running") {
        sendError(res, 409, "DIAGNOSIS_STATE_CONFLICT", "诊断执行中，暂不接受新消息");
        return;
      }
      const body = await readJson(req);
      const text = String(body.text || "").trim();
      if (!text) {
        sendError(res, 422, "VALIDATION_FAILED", "消息内容不能为空");
        return;
      }
      const extraction = extractFromText(text);
      session.messages.push({ message_id: uid("msg"), role: "user", text, payload: null, created_at: nowIso() });
      if (session.status === "draft") {
        const messageId = uid("msg");
        session.messages.push({ message_id: messageId, role: "agent", text: "已抽取数据，请确认后开始诊断", payload: { type: "extraction_card", extraction }, created_at: nowIso() });
        session.updated_at = nowIso();
        sendJson(res, 200, {
          session_id: session.session_id,
          message_id: messageId,
          diagnosis_id: null,
          diagnosis_status: null,
          version: null,
          agent_text: `已抽取 ${7 - extraction.missing_fields.length} 项，请确认后开始诊断`,
          interrupt: null,
          extraction,
          stream_url: null,
        });
        return;
      }
      const messageId = uid("msg");
      const agentText = "已抽取补充值，请确认后继续";
      session.messages.push({ message_id: messageId, role: "agent", text: agentText, payload: { type: "supplement_card", extraction }, created_at: nowIso() });
      session.updated_at = nowIso();
      sendJson(res, 200, {
        session_id: session.session_id,
        message_id: messageId,
        diagnosis_id: diag.diagnosis_id,
        diagnosis_status: diag.status,
        version: diag.interrupt?.version || diag.version,
        agent_text: agentText,
        interrupt: diag.interrupt,
        extraction,
        stream_url: null,
      });
      return;
    }

    if (route.startsWith("/chat/sessions/") && route.endsWith("/confirm") && method === "POST") {
      const id = route.split("/")[3];
      const session = chatSessions.get(id);
      if (!session) {
        sendError(res, 404, "CHAT_SESSION_NOT_FOUND", "会话不存在，请新建对话");
        return;
      }
      if (session.status === "active") {
        sendError(res, 409, "CHAT_SESSION_ALREADY_ACTIVE", "会话已绑定诊断", { diagnosis_id: session.diagnosis_id });
        return;
      }
      if (session.status === "terminal") {
        sendError(res, 409, "CHAT_SESSION_CLOSED", "本对话已结束，请新建对话");
        return;
      }
      const body = await readJson(req);
      const features = body.features || {};
      if (!features.device_id || Object.values(features).some((v) => v === null)) {
        sendError(res, 422, "DEVICE_ID_INVALID", "设备标识必填，且不得提交 null 字段", {
          fields: [{ field: "device_id", label: "设备标识", unit: null, reason: "MISSING", message: "设备标识必填" }],
        });
        return;
      }
      const normalized = {
        device_id: features.device_id,
        product_type: features.product_type ?? null,
        air_temp_k: features.air_temp_k ?? null,
        process_temp_k: features.process_temp_k ?? null,
        rotational_speed_rpm: features.rotational_speed_rpm ?? null,
        torque_nm: features.torque_nm ?? null,
        tool_wear_min: features.tool_wear_min ?? null,
      };
      const complete = allFeaturesPresent(normalized);
      if (complete) {
        const fp = fingerprintOf(normalized);
        const existingId = fingerprints.get(fp);
        const existing = existingId ? diagnoses.get(existingId) : null;
        if (existing) {
          session.status = "terminal";
          session.diagnosis_id = existing.diagnosis_id;
          session.updated_at = nowIso();
          sendJson(res, 200, {
            session_id: session.session_id,
            diagnosis_id: existing.diagnosis_id,
            diagnosis_status: existing.status,
            version: existing.version,
            deduplicated: true,
            stream_url: `${BASE}/diagnoses/${existing.diagnosis_id}/events`,
          });
          return;
        }
      }
      const diag = createDiagnosis({
        inputType: "chat",
        features: normalized,
        deviceId: normalized.device_id,
        summary: { file_name: null, row_no: null, text_excerpt: String(body.text || "").slice(0, 80) },
      });
      session.status = "active";
      session.diagnosis_id = diag.diagnosis_id;
      session.updated_at = nowIso();
      session.messages.push({ message_id: uid("msg"), role: "agent", text: "已创建诊断，正在执行", payload: { type: "process_card", diagnosis_id: diag.diagnosis_id }, created_at: nowIso() });
      sendJson(res, 202, {
        session_id: session.session_id,
        diagnosis_id: diag.diagnosis_id,
        diagnosis_status: diag.status,
        version: diag.version,
        deduplicated: false,
        stream_url: `${BASE}/diagnoses/${diag.diagnosis_id}/events`,
      });
      return;
    }

    if (route === "/diagnoses" && method === "POST") {
      const body = await readJson(req);
      const inputType = body.input_type;
      let normalized = null;
      let summary = { file_name: null, row_no: null, text_excerpt: null };
      if (inputType === "form") {
        normalized = {
          device_id: body.device_id,
          product_type: body.product_type,
          air_temp_k: body.air_temp_k,
          process_temp_k: body.process_temp_k,
          rotational_speed_rpm: body.rotational_speed_rpm,
          torque_nm: body.torque_nm,
          tool_wear_min: body.tool_wear_min,
        };
      } else if (inputType === "nl") {
        normalized = {
          device_id: body.device_id,
          product_type: body.product_type ?? null,
          air_temp_k: body.air_temp_k ?? null,
          process_temp_k: body.process_temp_k ?? null,
          rotational_speed_rpm: body.rotational_speed_rpm ?? null,
          torque_nm: body.torque_nm ?? null,
          tool_wear_min: body.tool_wear_min ?? null,
        };
        summary.text_excerpt = String(body.text || "").slice(0, 80);
      } else if (inputType === "csv_single") {
        const upload = uploads.get(body.upload_id);
        if (!upload) {
          sendError(res, 404, "UPLOAD_NOT_FOUND", "上传记录不存在，请重新上传。");
          return;
        }
        const row = upload.rows[Number(body.row_no) - 1];
        if (!row) {
          sendError(res, 422, "VALIDATION_FAILED", "诊断行号超出文件范围");
          return;
        }
        normalized = normalizeRow(upload.headers, row, body.mapping || {}, body.default_device_id);
        summary = { file_name: upload.file_name, row_no: Number(body.row_no), text_excerpt: null };
      } else {
        sendError(res, 422, "VALIDATION_FAILED", "不支持的 input_type");
        return;
      }
      if (!normalized.device_id || !/^[A-Za-z0-9_\-\u4e00-\u9fff]{1,64}$/.test(normalized.device_id)) {
        sendError(res, 422, "DEVICE_ID_INVALID", "设备标识必填，且仅允许中文、字母、数字、-、_，长度 1–64", {
          fields: [{ field: "device_id", label: "设备标识", unit: null, reason: "MISSING", message: "设备标识必填" }],
        });
        return;
      }
      if (normalized.rotational_speed_rpm === 0 && normalized.torque_nm === 0) {
        sendError(res, 422, "MACHINE_STOPPED", "设备停机（转速与扭矩均为 0），无法诊断。");
        return;
      }
      if (normalized.rotational_speed_rpm === 0 && (normalized.torque_nm ?? 0) > 0) {
        sendError(res, 422, "DATA_CONTRADICTION", "转速与扭矩矛盾，请核对数据。");
        return;
      }
      const complete = allFeaturesPresent(normalized);
      if (complete) {
        const fp = fingerprintOf(normalized);
        const existing = diagnoses.get(fingerprints.get(fp));
        if (existing) {
          sendJson(res, 200, {
            diagnosis_id: existing.diagnosis_id,
            status: existing.status,
            input_type: existing.input_type,
            version: existing.version,
            diagnosis_revision: existing.diagnosis_revision,
            deduplicated: true,
            created_at: existing.created_at,
            stream_url: `${BASE}/diagnoses/${existing.diagnosis_id}/events`,
            snapshot_url: `${BASE}/diagnoses/${existing.diagnosis_id}`,
          });
          return;
        }
      }
      const diag = createDiagnosis({ inputType, features: normalized, deviceId: normalized.device_id, summary });
      sendJson(res, 202, {
        diagnosis_id: diag.diagnosis_id,
        status: diag.status,
        input_type: diag.input_type,
        version: diag.version,
        diagnosis_revision: diag.diagnosis_revision,
        deduplicated: false,
        created_at: diag.created_at,
        stream_url: `${BASE}/diagnoses/${diag.diagnosis_id}/events`,
        snapshot_url: `${BASE}/diagnoses/${diag.diagnosis_id}`,
      }, { Location: `${BASE}/diagnoses/${diag.diagnosis_id}` });
      return;
    }

    if (route === "/diagnoses" && method === "GET") {
      let items = [...diagnoses.values()].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
      const status = url.searchParams.get("status");
      if (status) items = items.filter((d) => status.split(",").includes(d.status));
      const keyword = (url.searchParams.get("keyword") || "").toLowerCase();
      if (keyword) items = items.filter((d) => d.device_id.toLowerCase().includes(keyword) || (d.report_title || "").toLowerCase().includes(keyword));
      const primary = url.searchParams.get("primary_type");
      if (primary) items = items.filter((d) => d.primary_type === primary);
      const page = Number(url.searchParams.get("page") || 1);
      const pageSize = Number(url.searchParams.get("page_size") || 20);
      const slice = items.slice((page - 1) * pageSize, page * pageSize);
      sendJson(res, 200, {
        items: slice.map((d) => ({
          diagnosis_id: d.diagnosis_id,
          device_id: d.device_id,
          report_title: d.report_title,
          input_type: d.input_type,
          status: d.status,
          primary_type: d.primary_type,
          secondary_types: d.secondary_types,
          confidence: d.confidence,
          confidence_level: d.confidence_level,
          knowledge_status: d.knowledge_status,
          auto_review: d.auto_review,
          retry_count: d.retry_count,
          duration_ms: d.duration_ms,
          started_at: d.started_at,
          finished_at: d.finished_at,
          batch_task_id: d.batch?.batch_task_id || null,
          row_no: d.batch?.row_no || null,
        })),
        page,
        page_size: pageSize,
        total: items.length,
        total_pages: Math.ceil(items.length / pageSize),
      });
      return;
    }

    if (route.startsWith("/diagnoses/") && route.endsWith("/events") && method === "GET") {
      const id = route.split("/")[2];
      const diag = diagnoses.get(id);
      if (!diag) {
        sendError(res, 404, "DIAGNOSIS_NOT_FOUND", "诊断不存在或无权访问");
        return;
      }
      openStream(req, res, id, "diagnosis", { type: "snapshot", payload: diag, revision: diag.diagnosis_revision });
      return;
    }

    if (route.startsWith("/diagnoses/") && route.endsWith("/resume") && method === "POST") {
      const id = route.split("/")[2];
      const diag = diagnoses.get(id);
      if (!diag) {
        sendError(res, 404, "DIAGNOSIS_NOT_FOUND", "诊断不存在或无权访问");
        return;
      }
      if (diag.status === "expired") {
        sendError(res, 409, "DIAGNOSIS_EXPIRED", "中断已过期，请以原输入重新发起");
        return;
      }
      if (diag.status !== "waiting_human" || !diag.interrupt) {
        sendError(res, 409, "DIAGNOSIS_STATE_CONFLICT", "当前状态不允许该操作，请刷新快照");
        return;
      }
      const body = await readJson(req);
      if (Number(body.version) !== diag.version && Number(body.version) !== diag.interrupt.version) {
        sendError(res, 409, "VERSION_CONFLICT", "状态已变更，请刷新");
        return;
      }
      const decision = body.decision;
      if (decision === "supplement" && diag.interrupt.type === "clarification") {
        const supplement = body.supplement || {};
        if (!Object.keys(supplement).length) {
          sendError(res, 422, "VALIDATION_FAILED", "至少补充一个有效字段");
          return;
        }
        Object.assign(diag.features.normalized, supplement);
        diag.features.completeness = (7 - missingFieldsFor(diag.features.normalized, true).length) / 7;
        diag.features.missing_fields = missingFieldsFor(diag.features.normalized, true).map((f) => f.field);
        diag.version += 1;
        diag.interrupt = null;
        const remaining = missingFieldsFor(diag.features.normalized);
        logEvent(diag.diagnosis_id, "step", { node: "parse_input", phase: "resume", rule_id: "RT-02", summary: `补充 ${Object.keys(supplement).length} 项`, duration_ms: 120 }, diag.diagnosis_revision);
        if (remaining.length) {
          later(diag.diagnosis_id, 260, (d) => attachClarificationInterrupt(d, remaining));
        } else {
          diag.status = "running";
          logEvent(diag.diagnosis_id, "status", { from: "waiting_human", to: "running", reason: "supplement_resume", version: diag.version }, diag.diagnosis_revision);
          runDiagnosisPipeline(diag, { baseDelay: 200, fromSupplement: true });
        }
        sendJson(res, 200, diag);
        return;
      }
      if (decision === "supplement" && diag.interrupt.type === "review") {
        if (diag.interrupt.review_round >= 2) {
          sendError(res, 409, "DECISION_NOT_ALLOWED", "本次诊断已补充过一次，请确认或放弃");
          return;
        }
        const supplement = body.supplement || {};
        if (!Object.keys(supplement).length) {
          sendError(res, 422, "VALIDATION_FAILED", "至少补充一个有效字段");
          return;
        }
        Object.assign(diag.features.normalized, supplement);
        diag.diagnosis_revision += 1;
        diag.version += 1;
        diag.interrupt = null;
        diag.status = "running";
        logEvent(diag.diagnosis_id, "step", { node: "retrieve", phase: "rebuild", rule_id: "RT-08", summary: "下游重建 · 修订 v2", duration_ms: 200 }, diag.diagnosis_revision);
        logEvent(diag.diagnosis_id, "status", { from: "waiting_human", to: "running", reason: "review_supplement_rebuild", version: diag.version }, diag.diagnosis_revision);
        later(diag.diagnosis_id, 900, (d) => {
          d.confidence = 0.58;
          d.confidence_level = "medium";
          attachReviewInterrupt(d, 2, 0.58, "medium");
        });
        sendJson(res, 200, diag);
        return;
      }
      if (decision === "confirm") {
        if (diag.interrupt.type !== "review") {
          sendError(res, 409, "DECISION_NOT_ALLOWED", "该中断不支持确认结论");
          return;
        }
        diag.human_decision = "confirm";
        diag.version += 1;
        diag.interrupt = null;
        diag.report_title = `${diag.device_id} ${diag.primary_type} 诊断报告`;
        diag.report_meta = {
          template_version: "tpl-v1.2",
          prompt_version: "prompt-v1.3",
          kb_version: "kb-v1.0.0",
          model_name: "deepseek-chat",
          auto_review: false,
          generated_at: nowIso(),
          degraded_reasons: [],
        };
        diag.report_elements_check = { passed: true, present: ["诊断结论", "置信度与分级", "关键数据特征", "判断依据", "鉴别诊断", "维修与处置建议", "数据质量与假设", "免责声明与知识边界"], missing: [], report_retry_count: 0 };
        diag.report = { markdown: buildReport(diag), download_url: `${BASE}/diagnoses/${diag.diagnosis_id}/report.md` };
        addStep(diag, "report", "start", "人工确认后重生成报告", null, "RT-15");
        addStep(diag, "report", "end", "已人工确认", 800, "RT-15");
        logEvent(diag.diagnosis_id, "report", { report_title: diag.report_title, report_elements_check: diag.report_elements_check, auto_review: false, degraded_reasons: [], download_url: diag.report.download_url, report_meta: diag.report_meta }, diag.diagnosis_revision);
        setStatus(diag, "succeeded", "human_confirmed");
        sendJson(res, 200, diag);
        return;
      }
      if (decision === "abort") {
        diag.human_decision = "abort";
        diag.interrupt = null;
        diag.error = { code: "HUMAN_ABORT", message: "用户放弃本次诊断，未生成报告。", node: null, recoverable: true };
        setStatus(diag, "aborted", "human_abort");
        sendJson(res, 200, diag);
        return;
      }
      sendError(res, 422, "VALIDATION_FAILED", "不支持的人工决策");
      return;
    }

    if (route.startsWith("/diagnoses/") && route.endsWith("/report.md") && method === "GET") {
      const id = route.split("/")[2];
      const diag = diagnoses.get(id);
      if (!diag || !diag.report) {
        sendError(res, 409, "REPORT_NOT_AVAILABLE", "当前诊断没有可导出的报告");
        return;
      }
      const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "").replace(/(\d{8})(\d{4})/, "$1_$2");
      const safe = diag.device_id.replace(/[\\/:*?"<>|]/g, "_");
      res.writeHead(200, {
        "Content-Type": "text/markdown; charset=utf-8",
        "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(`诊断报告_${safe}_${stamp}.md`)}`,
        "Cache-Control": "no-store",
      });
      res.end(diag.report.markdown);
      return;
    }

    if (route.startsWith("/diagnoses/") && method === "GET") {
      const id = route.split("/")[2];
      const diag = diagnoses.get(id);
      if (!diag) {
        sendError(res, 404, "DIAGNOSIS_NOT_FOUND", "诊断不存在或无权访问");
        return;
      }
      sendJson(res, 200, diag);
      return;
    }

    if (route.startsWith("/diagnoses/") && method === "DELETE") {
      const id = route.split("/")[2];
      const diag = diagnoses.get(id);
      if (!diag) {
        sendError(res, 404, "DIAGNOSIS_NOT_FOUND", "诊断不存在或无权访问");
        return;
      }
      if (diag.input_type === "csv_batch") {
        sendError(res, 409, "DIAGNOSIS_STATE_CONFLICT", "批量诊断不允许单独删除");
        return;
      }
      diagnoses.delete(id);
      res.writeHead(204);
      res.end();
      return;
    }

    if (route === "/batches" && method === "POST") {
      const body = await readJson(req);
      const upload = uploads.get(body.upload_id);
      if (!upload) {
        sendError(res, 404, "UPLOAD_NOT_FOUND", "上传记录不存在，请重新上传。");
        return;
      }
      const batch = {
        batch_task_id: uid("bch"),
        file_name: upload.file_name,
        total_rows: upload.rows.length,
        status: "queued",
        default_device_id: body.default_device_id || null,
        cancel_requested: false,
        timeout_deadline: new Date(Date.now() + 60 * 60000).toISOString(),
        created_at: nowIso(),
        started_at: null,
        finished_at: null,
        error_code: null,
      };
      const rows = upload.rows.map((row, idx) => {
        const normalized = normalizeRow(upload.headers, row, body.mapping || {}, body.default_device_id);
        return {
          row_id: uid("row"),
          row_no: idx + 1,
          device_id: normalized.device_id,
          status: "pending",
          diagnosis_id: null,
          report_summary: null,
          auto_review: false,
          duration_ms: null,
          error_field: null,
          error_code: null,
        };
      });
      batches.set(batch.batch_task_id, batch);
      batchRows.set(batch.batch_task_id, rows);
      eventLogs.set(batch.batch_task_id, []);
      sendJson(res, 202, {
        batch_task_id: batch.batch_task_id,
        status: "queued",
        total_rows: batch.total_rows,
        created_at: batch.created_at,
        stream_url: `${BASE}/batches/${batch.batch_task_id}/events`,
        snapshot_url: `${BASE}/batches/${batch.batch_task_id}`,
      });
      setTimeout(() => startBatch(batch), 600);
      return;
    }

    if (route === "/batches" && method === "GET") {
      sendJson(res, 200, { items: [...batches.values()].map(batchSnapshot), page: 1, page_size: 20, total: batches.size, total_pages: 1 });
      return;
    }

    if (route.startsWith("/batches/") && route.endsWith("/events") && method === "GET") {
      const id = route.split("/")[2];
      const batch = batches.get(id);
      if (!batch) {
        sendError(res, 404, "BATCH_NOT_FOUND", "批量任务不存在或无权访问");
        return;
      }
      openStream(req, res, id, "batch", { type: "batch_snapshot", payload: batchSnapshot(batch), revision: null });
      return;
    }

    if (route.startsWith("/batches/") && route.endsWith("/rows") && method === "GET") {
      const id = route.split("/")[2];
      const rows = batchRows.get(id) || [];
      const page = Number(url.searchParams.get("page") || 1);
      const pageSize = Number(url.searchParams.get("page_size") || 20);
      sendJson(res, 200, { items: rows.slice((page - 1) * pageSize, page * pageSize), page, page_size: pageSize, total: rows.length, total_pages: Math.ceil(rows.length / pageSize) });
      return;
    }

    if (route.startsWith("/batches/") && route.includes("/rows/") && method === "GET") {
      const parts = route.split("/");
      const batchId = parts[2];
      const rowId = parts[4];
      const row = (batchRows.get(batchId) || []).find((r) => r.row_id === rowId);
      if (!row) {
        sendError(res, 404, "BATCH_NOT_FOUND", "批量行不存在或无权访问");
        return;
      }
      sendJson(res, 200, { row, report_url: row.diagnosis_id ? `${BASE}/diagnoses/${row.diagnosis_id}/report.md` : null, diagnosis_status: row.diagnosis_id ? diagnoses.get(row.diagnosis_id)?.status || null : null });
      return;
    }

    if (route.startsWith("/batches/") && route.endsWith("/cancel") && method === "POST") {
      const id = route.split("/")[2];
      const batch = batches.get(id);
      if (!batch) {
        sendError(res, 404, "BATCH_NOT_FOUND", "批量任务不存在或无权访问");
        return;
      }
      if (["completed", "partially_failed", "failed", "cancelled", "timed_out"].includes(batch.status)) {
        sendError(res, 409, "BATCH_ALREADY_FINISHED", "任务已终态，不能取消");
        return;
      }
      batch.cancel_requested = true;
      sendJson(res, 202, { batch_task_id: id, status: batch.status, cancel_requested: true });
      return;
    }

    if (route.startsWith("/batches/") && route.endsWith("/export.csv") && method === "GET") {
      const id = route.split("/")[2];
      const rows = batchRows.get(id) || [];
      if (!rows.some((r) => ["succeeded", "degraded", "degraded_review", "failed", "failed_timeout"].includes(r.status))) {
        sendError(res, 409, "REPORT_NOT_AVAILABLE", "暂无可导出结果");
        return;
      }
      const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
      const lines = ["row_no,device_id,primary_type,confidence,status,report_summary,duration_ms,error_field,error_code"];
      for (const row of rows) {
        const diag = row.diagnosis_id ? diagnoses.get(row.diagnosis_id) : null;
        lines.push([row.row_no, row.device_id, diag?.primary_type || "", diag?.confidence ?? "", row.status, row.report_summary || "", row.duration_ms ?? "", row.error_field || "", row.error_code || ""].map(esc).join(","));
      }
      res.writeHead(200, {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(`批量汇总_${id}.csv`)}`,
      });
      res.end(`\uFEFF${lines.join("\n")}`);
      return;
    }

    if (route.startsWith("/batches/") && method === "GET") {
      const id = route.split("/")[2];
      const batch = batches.get(id);
      if (!batch) {
        sendError(res, 404, "BATCH_NOT_FOUND", "批量任务不存在或无权访问");
        return;
      }
      sendJson(res, 200, batchSnapshot(batch));
      return;
    }

    if (route === "/evaluations/latest" && method === "GET") {
      sendJson(res, 200, { batch: evalBatch });
      return;
    }

    if (route === "/evaluations" && method === "GET") {
      sendJson(res, 200, { items: evalTrend, page: 1, page_size: 20, total: evalTrend.length, total_pages: 1 });
      return;
    }

    if (route.startsWith("/evaluations/") && route.endsWith("/samples") && method === "GET") {
      const onlyBad = url.searchParams.get("only_bad_cases") !== "false";
      const split = url.searchParams.get("split");
      const page = Number(url.searchParams.get("page") || 1);
      const pageSize = Number(url.searchParams.get("page_size") || 20);
      let items = onlyBad
        ? allSamples.filter((sample) => sample.error_category !== null && sample.status !== "failed_timeout")
        : allSamples;
      if (split) items = items.filter((sample) => sample.dataset_split === split);
      sendJson(res, 200, {
        items: items.slice((page - 1) * pageSize, page * pageSize),
        page,
        page_size: pageSize,
        total: items.length,
        total_pages: Math.ceil(items.length / pageSize),
      });
      return;
    }

    if (route.startsWith("/evaluations/") && method === "GET") {
      sendJson(res, 200, { batch: evalBatch, confusion_matrix: confusion, per_class_recall: perClass, retrieval_tuning: tuning, bad_cases: badCases });
      return;
    }

    sendError(res, 404, "NOT_FOUND", "接口不存在");
  } catch (error) {
    console.error(error);
    sendError(res, 500, "INTERNAL_ERROR", "服务端处理异常，请稍后重试");
  }
});

server.listen(PORT, () => {
  console.log(`[mock] equipment-diagnosis mock API listening on http://localhost:${PORT}${BASE}`);
  console.log("[mock] seed user: zhangsan / Abcd1234");
});
