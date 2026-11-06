"""评测（只读 API + 离线执行器）：AI4I 2020 样本 → 图执行 → KPI 指标（ARCH §5.4.8）。"""

from __future__ import annotations

import csv
import json
import math
import random
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app import services
from app.config import Settings
from app.db import Database, new_id, utcnow
from app.errors import ApiError

SAMPLE_TOTAL = 120
EDGE_TOTAL = 20
EVAL_SEED = 20261024
PRIMARY_LABELS = ("正常", "TWF", "HDF", "PWF", "OSF", "RNF")
PREDICTED_LABELS = PRIMARY_LABELS + ("未覆盖",)
# FR-EV-01：多重标签按 OSF > HDF > PWF > TWF > RNF 取主类型
LABEL_PRIORITY = ("OSF", "HDF", "PWF", "TWF", "RNF")
# FR-EV-01 / ARCH §3.10.1：120 条冻结集配额
EVAL_QUOTA = (
    ("正常", 30),
    ("HDF", 20),
    ("PWF", 20),
    ("OSF", 20),
    ("TWF", 20),
    ("RNF", 10),
)
BAD_CASE_LIMIT = 20

# PRD §3.10.1：edge 为独立描述样本（EDGE-xx），不复用 AI4I 行、不计入 KPI-01
EDGE_DESCRIPTIONS = (
    "设备启动后出现间歇性异响，伴随轻微温升，未提供完整运行参数。",
    "主轴在低速段振动明显，声音呈周期性冲击，负载数据缺失。",
    "联轴器区域有金属摩擦声，停机后手动盘车阻力偏大。",
    "润滑系统压力波动，轴承温度时高时低，未记录功率。",
    "冷却液流量不足，加工面出现轻微烧伤，转速数据未采集。",
    "设备在换刀后出现短时抖动，随后恢复正常，缺乏扭矩记录。",
    "电机电流偶发尖峰，伴随异味，未提供温度与转速。",
    "皮带传动处有打滑声，负载升高时异响加剧。",
    "液压站噪声增大，压力表指针抖动，未上传完整工艺参数。",
    "导轨润滑不良，进给时出现爬行现象，缺少刀具磨损数据。",
    "轴承座手感发热，运行声音沉闷，未记录空气温度。",
    "设备在夜间班次频繁报警，白天正常，缺少全部数值特征。",
    "齿轮箱出现低频嗡鸣，随转速升高而增强。",
    "气动夹具动作迟滞，伴随漏气声，未采集扭矩。",
    "刀柄锥面磨损，加工尺寸漂移，缺少转速与功率。",
    "设备运行中偶发急停，复位后可继续，无完整过程数据。",
    "丝杠反向间隙增大，定位精度下降，温度记录缺失。",
    "主轴轴承出现高频啸叫，轻载时更明显。",
    "设备基础螺栓松动，整机振动加大，缺少磨损记录。",
    "多台同型号设备中仅此台异响，负载与温升数据不完整。",
)


def _expected_primary(row: dict[str, str]) -> str:
    """AI4I 故障标记 → 主类型（FR-EV-01：OSF > HDF > PWF > TWF > RNF）。"""
    for label in LABEL_PRIORITY:
        if (row.get(label) or "0").strip() == "1":
            return label
    return "正常"


def validate_sample_exclusivity(samples: list[dict[str, Any]]) -> None:
    """UDI 行级互斥校验（PRD §3.10.1）：重复、eval/edge、tuning/eval 重叠均直接报错。"""
    seen: dict[str, set[str]] = {"eval": set(), "edge": set(), "tuning": set()}
    for sample in samples:
        split = sample["dataset_split"]
        sample_id = sample["sample_id"]
        if split not in seen:
            raise RuntimeError(f"未知 dataset_split：{split}")
        if sample_id in seen[split]:
            raise RuntimeError(f"UDI 重复（{split}）：{sample_id}")
        seen[split].add(sample_id)
    overlap = seen["eval"] & seen["edge"]
    if overlap:
        raise RuntimeError(f"eval/edge UDI 重叠：{sorted(overlap)[:10]}")
    overlap = seen["tuning"] & seen["eval"]
    if overlap:
        raise RuntimeError(f"tuning/eval UDI 重叠：{sorted(overlap)[:10]}")


def load_samples(settings: Settings) -> list[dict[str, Any]]:
    """构造冻结评测集：eval 120 条（FR-EV-01 配额）+ edge 20 条独立描述样本。"""
    path = Path(settings.dataset_path)
    if not path.exists():
        raise RuntimeError(f"AI4I 数据集不存在：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    by_label: dict[str, list[dict[str, str]]] = {label: [] for label in PRIMARY_LABELS}
    for row in rows:
        by_label[_expected_primary(row)].append(row)

    rng = random.Random(EVAL_SEED)
    selected: list[tuple[dict[str, str], str]] = []
    used: set[str] = set()
    for label, count in EVAL_QUOTA:
        pool = [row for row in by_label[label] if _udi(row) not in used]
        rng.shuffle(pool)
        chosen = pool[:count]
        if len(chosen) < count:
            if label != "RNF":
                raise RuntimeError(
                    f"评测集配额不足：{label} 需要 {count} 条，可用 {len(chosen)} 条"
                )
            # PRD §3.10.1：纯 RNF 不足时以正常类补足，总数固定 120
            shortage = count - len(chosen)
            normal_pool = [row for row in by_label["正常"] if _udi(row) not in used]
            rng.shuffle(normal_pool)
            if len(normal_pool) < shortage:
                raise RuntimeError(f"正常类不足以补足 RNF 缺口 {shortage} 条")
            selected.extend((row, label) for row in chosen)
            selected.extend((row, "正常") for row in normal_pool[:shortage])
            used.update(_udi(row) for row in chosen)
            used.update(_udi(row) for row in normal_pool[:shortage])
            continue
        selected.extend((row, label) for row in chosen)
        used.update(_udi(row) for row in chosen)

    if len(selected) != SAMPLE_TOTAL:
        raise RuntimeError(f"评测集必须为 {SAMPLE_TOTAL} 条，实际 {len(selected)} 条")

    samples: list[dict[str, Any]] = []
    for index, (row, _label) in enumerate(selected, start=1):
        samples.append(
            {
                "sample_no": index,
                "sample_id": _udi(row),
                "dataset_split": "eval",
                "expected_primary": _expected_primary(row),
                "raw_input": _raw_input(row),
            }
        )

    # edge：独立描述样本，编号 EDGE-xx，不复用 AI4I 行，不计入 KPI-01
    for index, description in enumerate(EDGE_DESCRIPTIONS, start=1):
        samples.append(
            {
                "sample_no": SAMPLE_TOTAL + index,
                "sample_id": f"EDGE-{index:02d}",
                "dataset_split": "edge",
                "expected_primary": "未覆盖",
                "raw_input": {
                    "device_id": f"EDGE-{index:02d}",
                    "product_type": "M",
                    "air_temp_k": 298.1,
                    "process_temp_k": 308.6,
                    "rotational_speed_rpm": 1500.0,
                    "torque_nm": 40.0,
                    "tool_wear_min": 100.0,
                },
                "text": description,
            }
        )

    validate_sample_exclusivity(samples)
    return samples


def _udi(row: dict[str, str]) -> str:
    return (row.get("UDI") or "").strip()


def _raw_input(row: dict[str, str]) -> dict[str, Any]:
    return {
        "device_id": (row.get("Product ID") or "").strip(),
        "product_type": (row.get("Type") or "M").strip(),
        "air_temp_k": float(row["Air temperature [K]"]),
        "process_temp_k": float(row["Process temperature [K]"]),
        "rotational_speed_rpm": float(row["Rotational speed [rpm]"]),
        "torque_nm": float(row["Torque [Nm]"]),
        "tool_wear_min": float(row["Tool wear [min]"]),
    }


def ensure_eval_user(db: Database) -> int:
    conn = db.connection()
    row = conn.execute("SELECT user_id FROM users WHERE username='evaluator'").fetchone()
    if row is not None:
        return int(row["user_id"])
    import bcrypt

    password_hash = bcrypt.hashpw(b"EvalOnly#2026", bcrypt.gensalt(rounds=12)).decode("utf-8")
    cursor = conn.execute(
        "INSERT INTO users (username, password_hash) VALUES ('evaluator', ?)", (password_hash,)
    )
    return int(cursor.lastrowid)


def _percentile(values: list[int], ratio: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(math.ceil(ratio * len(ordered))) - 1))
    return int(ordered[index])


async def run_evaluation(
    db: Database, settings: Settings, runner, knowledge, user_id: int
) -> str:
    """离线执行评测并落库；返回 eval_batch_id。"""
    from app import features as features_domain

    samples = load_samples(settings)
    eval_batch_id = new_id("evb")
    version = knowledge.kb_version
    results: list[dict[str, Any]] = []

    for sample in samples:
        payload = dict(sample["raw_input"])
        result = features_domain.normalize_input("form", payload)
        if not result.ok:
            results.append(
                {
                    **sample,
                    "predicted_primary": None,
                    "correct": 0,
                    "confidence": None,
                    "elements_present": None,
                    "latency_ms": None,
                    "status": "failed",
                    "error_category": "feature_missing",
                }
            )
            continue
        diagnosis_id, state = services.insert_diagnosis_from_result(
            db,
            settings,
            user_id,
            input_type="form",
            result=result,
            raw_input=payload,
            execution_mode="eval",
            input_summary={"text_excerpt": sample.get("text")},
            fingerprint_scope=None,
        )
        await runner.run_inline(diagnosis_id, state)
        diagnosis = db.connection().execute(
            "SELECT * FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)
        ).fetchone()
        status = diagnosis["status"]
        predicted = diagnosis["primary_type"]
        correct = 1 if status in ("succeeded", "degraded") and predicted == sample["expected_primary"] else 0
        check = json.loads(diagnosis["report_elements_check_json"]) if diagnosis["report_elements_check_json"] else None
        check = check or {}
        elements_present = len(check.get("present") or []) if check else None
        breakdown = (
            json.loads(diagnosis["confidence_breakdown_json"])
            if diagnosis["confidence_breakdown_json"]
            else {}
        )
        llm_used = bool((breakdown or {}).get("llm_used"))
        llm_decided = bool((breakdown or {}).get("llm_decided"))
        results.append(
            {
                **sample,
                "predicted_primary": predicted,
                "correct": correct,
                "confidence": diagnosis["confidence"],
                "elements_present": elements_present,
                "latency_ms": diagnosis["duration_ms"],
                "status": status if status in ("succeeded", "degraded", "failed", "failed_timeout") else "failed",
                "llm_used": llm_used,
                "knowledge_status": diagnosis["knowledge_status"],
                "error_category": _error_category(
                    sample,
                    predicted,
                    status,
                    check,
                    llm_used,
                    llm_decided,
                    diagnosis["knowledge_status"],
                ),
            }
        )

    # KPI-01/02/03 分母只取 eval 120 条；edge 20 条仅用于 KPI-05/鲁棒性观察
    eval_results = [r for r in results if r["dataset_split"] == "eval"]
    report_count = sum(1 for r in eval_results if r["status"] in ("succeeded", "degraded"))
    failed_timeout_count = sum(1 for r in eval_results if r["status"] == "failed_timeout")
    correct_count = sum(r["correct"] for r in eval_results)
    elements_sum = sum(
        (r["elements_present"] or 0) for r in eval_results if r["status"] in ("succeeded", "degraded")
    )
    latencies = [
        r["latency_ms"]
        for r in eval_results
        if r["status"] in ("succeeded", "degraded") and r["latency_ms"] is not None
    ]
    if len(eval_results) != SAMPLE_TOTAL:
        raise RuntimeError(f"KPI-01 分母必须为 {SAMPLE_TOTAL}，实际 {len(eval_results)}")
    accuracy = correct_count / SAMPLE_TOTAL
    completeness_rate = elements_sum / (report_count * 8) if report_count else None
    timeout_rate = failed_timeout_count / SAMPLE_TOTAL

    model_name = settings.deepseek_model if settings.llm_mode == "deepseek" else settings.llm_mode
    prompt_version = _reporter_version(settings)
    artifact_path = _write_artifact(settings, eval_batch_id, results)

    conn = db.connection()
    conn.execute(
        "INSERT INTO eval_batches (eval_batch_id, dataset_version, prompt_version, kb_version, model_name,"
        " sample_total, edge_sample_total, report_count, failed_timeout_count, latency_sample_count,"
        " accuracy, completeness_rate, fabrication_rate, timeout_rate, latency_avg_ms, latency_p50_ms,"
        " latency_p95_ms, latency_max_ms, artifact_path, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            eval_batch_id,
            "AI4I-2020",
            prompt_version,
            version,
            model_name,
            SAMPLE_TOTAL,
            EDGE_TOTAL,
            report_count,
            failed_timeout_count,
            len(latencies),
            accuracy,
            completeness_rate,
            None,
            timeout_rate,
            int(sum(latencies) / len(latencies)) if latencies else None,
            _percentile(latencies, 0.5),
            _percentile(latencies, 0.95),
            max(latencies) if latencies else None,
            artifact_path,
            utcnow(),
        ),
    )
    for result in results:
        conn.execute(
            "INSERT INTO eval_samples (eval_sample_id, eval_batch_id, sample_no, sample_id, dataset_split,"
            " expected_primary, predicted_primary, correct, confidence, elements_present, latency_ms,"
            " status, error_category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_id("evs"),
                eval_batch_id,
                result["sample_no"],
                result["sample_id"],
                result["dataset_split"],
                result["expected_primary"],
                result["predicted_primary"],
                result["correct"],
                result["confidence"],
                result["elements_present"],
                result["latency_ms"],
                result["status"],
                result["error_category"],
            ),
        )
    return eval_batch_id


def _error_category(
    sample: dict[str, Any],
    predicted: str | None,
    status: str,
    check: dict,
    llm_used: bool,
    llm_decided: bool,
    knowledge_status: str,
) -> str | None:
    if status == "failed_timeout":
        return "latency_exceeded"
    if status == "failed":
        return "feature_missing"
    if predicted == sample["expected_primary"]:
        return None
    if not check.get("passed"):
        return "report_missing_element"
    if knowledge_status == "missing":
        return "retrieval_miss"
    if llm_used and llm_decided:
        return "llm_misjudge"
    return "rule_misjudge"


def _reporter_version(settings: Settings) -> str:
    from app.prompts import PromptLibrary

    try:
        return PromptLibrary(settings.prompts_dir).version("reporter")
    except Exception:
        return "reporter-v1"


def _write_artifact(settings: Settings, eval_batch_id: str, results: list[dict[str, Any]]) -> str | None:
    """可选：评测明细落盘，便于复核；失败不阻塞指标。"""
    try:
        target = Path(settings.storage_dir) / "eval"
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{eval_batch_id}.json"
        path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
    except Exception:
        return None


# ---------- 只读查询 ----------
def _summary_of(row) -> dict[str, Any]:
    return {
        "eval_batch_id": row["eval_batch_id"],
        "dataset_version": row["dataset_version"],
        "prompt_version": row["prompt_version"],
        "kb_version": row["kb_version"],
        "model_name": row["model_name"],
        "sample_total": row["sample_total"],
        "edge_sample_total": row["edge_sample_total"],
        "report_count": row["report_count"],
        "failed_timeout_count": row["failed_timeout_count"],
        "accuracy": row["accuracy"],
        "completeness_rate": row["completeness_rate"],
        "timeout_rate": row["timeout_rate"],
        "fabrication_rate": row["fabrication_rate"],
        "latency_sample_count": row["latency_sample_count"],
        "latency_avg_ms": row["latency_avg_ms"],
        "latency_p50_ms": row["latency_p50_ms"],
        "latency_p95_ms": row["latency_p95_ms"],
        "latency_max_ms": row["latency_max_ms"],
        "created_at": row["created_at"],
    }


def _sample_of(row) -> dict[str, Any]:
    return {
        "eval_sample_id": row["eval_sample_id"],
        "eval_batch_id": row["eval_batch_id"],
        "sample_no": row["sample_no"],
        "sample_id": row["sample_id"],
        "dataset_split": row["dataset_split"],
        "expected_primary": row["expected_primary"],
        "predicted_primary": row["predicted_primary"],
        "correct": bool(row["correct"]) if row["correct"] is not None else None,
        "confidence": row["confidence"],
        "elements_present": row["elements_present"],
        "latency_ms": row["latency_ms"],
        "status": row["status"],
        "error_category": row["error_category"],
    }


def _batch_row(db: Database, eval_batch_id: str):
    row = db.connection().execute(
        "SELECT * FROM eval_batches WHERE eval_batch_id=?", (eval_batch_id,)
    ).fetchone()
    if row is None:
        raise ApiError(404, "EVAL_NOT_FOUND", "评测批次不存在")
    return row


def latest(db: Database) -> dict[str, Any]:
    row = db.connection().execute(
        "SELECT * FROM eval_batches ORDER BY created_at DESC, eval_batch_id DESC LIMIT 1"
    ).fetchone()
    return {"batch": _summary_of(row) if row else None}


def list_batches(db: Database, page: int, page_size: int) -> dict[str, Any]:
    conn = db.connection()
    total = conn.execute("SELECT COUNT(*) AS c FROM eval_batches").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM eval_batches ORDER BY created_at DESC, eval_batch_id DESC LIMIT ? OFFSET ?",
        (page_size, (page - 1) * page_size),
    ).fetchall()
    return {
        "items": [_summary_of(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def _retrieval_queries(settings: Settings) -> list[dict[str, Any]]:
    """AC-KB-06：固定 50 条检索集；缺失时按知识种子确定性生成并落盘。"""
    path = Path(settings.storage_dir) / "retrieval_queries.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    raw = Path(settings.knowledge_seed_path).read_text(encoding="utf-8-sig").strip()
    entries = json.loads(raw) if raw.startswith("[") else [
        json.loads(line) for line in raw.splitlines() if line.strip()
    ]
    queries: list[dict[str, Any]] = []
    for entry in entries:
        keywords = [str(item) for item in (entry.get("keywords") or []) if str(item).strip()]
        title = str(entry.get("title") or "").strip()
        variants = [
            title,
            " ".join(keywords[:3]),
            " ".join([keywords[0], keywords[-1]]) if len(keywords) > 1 else (keywords[0] if keywords else ""),
            (title + " " + keywords[0]).strip() if keywords else title,
        ]
        for query in variants:
            if query and len(queries) < 50:
                queries.append({"query": query, "expected_fault_type": entry.get("fault_type")})
        if len(queries) >= 50:
            break
    if len(queries) < 50:
        raise RuntimeError(f"固定检索集不足 50 条：{len(queries)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(queries, ensure_ascii=False, indent=2), encoding="utf-8")
    return queries


def _top5_hit_rate(service, queries: list[dict[str, Any]], top_k: int) -> float:
    """固定检索集上“Top-K 内出现期望故障类型”的命中率（实测）。"""
    hits = 0
    for item in queries:
        result = service.retrieve({}, cues=[item["query"]], top_k=top_k)
        if any(hit.get("fault_type") == item["expected_fault_type"] for hit in result.hits):
            hits += 1
    return round(hits / len(queries), 4)


def measure_top5_hit_rate(knowledge, settings: Settings | None = None) -> float:
    """AC-KB-06：固定 50 条检索集的 Top-5 同类型命中率（实测值）。"""
    settings = settings or getattr(knowledge, "settings", None)
    if settings is None:
        raise ValueError("缺少 settings，无法定位固定检索集")
    return _top5_hit_rate(knowledge, _retrieval_queries(settings), 5)


# AC-KB-06：跨参数对比的两组配置（Top-K 参与检索；chunk_size/overlap 参与建库参数）
TUNING_SPECS = (
    {"run": 1, "chunk_size": 400, "overlap": 50, "top_k": 5},
    {"run": 2, "chunk_size": 200, "overlap": 20, "top_k": 8},
)


def _measure_with_params(
    settings: Settings, queries: list[dict[str, Any]], spec: dict[str, Any]
) -> dict[str, Any]:
    """在临时知识集合上按指定 chunk_size/overlap 建索引并实测；结束即删除，不触碰正式库。"""
    from app.knowledge import KnowledgeService

    root = Path(tempfile.mkdtemp(prefix="edg-tuning-"))
    try:
        temp_settings = settings.model_copy(
            update={
                "storage_dir": root,
                "knowledge_dir": root / "knowledge",
                "db_path": root / "tuning.db",
                "checkpoint_path": root / "tuning-checkpoints.db",
            }
        )
        temp_settings.ensure_dirs()
        temp_db = Database(temp_settings.db_path)
        temp_db.migrate()
        try:
            kb_version = f"kb_tuning_c{spec['chunk_size']}_o{spec['overlap']}"
            service = KnowledgeService(temp_settings, temp_db)
            service.build(
                Path(settings.knowledge_seed_path),
                kb_version=kb_version,
                activate=True,
                chunk_size=spec["chunk_size"],
                overlap=spec["overlap"],
            )
            if service.index_status != "ok":
                raise RuntimeError(f"临时知识索引构建失败：{service.index_status}")
            rate = _top5_hit_rate(service, queries, spec["top_k"])
            manifest = json.loads(
                (service.version_dir / "manifest.json").read_text(encoding="utf-8")
            )
            if manifest["chunk_size"] != spec["chunk_size"] or manifest["overlap"] != spec["overlap"]:
                raise RuntimeError(f"临时索引参数未生效：{manifest}")
            return {
                "run": spec["run"],
                "params": {
                    "chunk_size": spec["chunk_size"],
                    "overlap": spec["overlap"],
                    "top_k": spec["top_k"],
                },
                "top5_hit_rate": rate,
                "sample_total": len(queries),
                "kb_version": manifest["kb_version"],
                "created_at": manifest["built_at"],
                "backend": manifest.get("backend"),
            }
        finally:
            temp_db.close()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_retrieval_tuning(knowledge, settings: Settings | None = None) -> dict[str, Any]:
    """AC-KB-06：跨参数（chunk_size/overlap/Top-K）前后对比 + 同参数重复一致性。"""
    settings = settings or getattr(knowledge, "settings", None)
    if settings is None:
        raise ValueError("缺少 settings，无法定位固定检索集")
    queries = _retrieval_queries(settings)
    runs = [_measure_with_params(settings, queries, spec) for spec in TUNING_SPECS]
    repeat = _measure_with_params(settings, queries, TUNING_SPECS[0])
    delta = round(float(runs[1]["top5_hit_rate"]) - float(runs[0]["top5_hit_rate"]), 4)
    return {
        "params": runs[0]["params"],
        "top5_hit_rate": runs[0]["top5_hit_rate"],
        "runs": runs,
        "delta": delta,
        "consistent": repeat["top5_hit_rate"] == runs[0]["top5_hit_rate"],
        "repeat": repeat,
        "kb_version": getattr(knowledge, "kb_version", None),
        "created_at": runs[0]["created_at"],
    }


def detail(db: Database, eval_batch_id: str, knowledge=None) -> dict[str, Any]:
    batch = _batch_row(db, eval_batch_id)
    conn = db.connection()
    rows = conn.execute(
        "SELECT * FROM eval_samples WHERE eval_batch_id=? AND dataset_split='eval' ORDER BY sample_no",
        (eval_batch_id,),
    ).fetchall()
    counts = [[0 for _ in PREDICTED_LABELS] for _ in PRIMARY_LABELS]
    per_class: list[dict[str, Any]] = []
    for label in PRIMARY_LABELS:
        expected_rows = [row for row in rows if row["expected_primary"] == label]
        hits = 0
        for row in expected_rows:
            predicted = row["predicted_primary"]
            row_index = PRIMARY_LABELS.index(label)
            if predicted in PREDICTED_LABELS:
                counts[row_index][PREDICTED_LABELS.index(predicted)] += 1
            if predicted == label:
                hits += 1
        per_class.append(
            {
                "label": label,
                "recall": (hits / len(expected_rows)) if expected_rows else None,
                "sample_count": len(expected_rows),
            }
        )
    bad_cases = [
        {
            "sample_no": row["sample_no"],
            "sample_id": row["sample_id"],
            "expected_primary": row["expected_primary"],
            "predicted_primary": row["predicted_primary"],
            "confidence": row["confidence"],
            "error_category": row["error_category"],
            "latency_ms": row["latency_ms"],
        }
        for row in conn.execute(
            "SELECT * FROM eval_samples WHERE eval_batch_id=? AND dataset_split='eval'"
            " AND (correct=0 OR correct IS NULL)"
            " ORDER BY sample_no LIMIT ?",
            (eval_batch_id, BAD_CASE_LIMIT),
        ).fetchall()
    ]
    retrieval_tuning = []
    if knowledge is not None:
        # AC-KB-06：跨参数两组实测 + 同参数重复一致性（临时索引，测完即删）
        retrieval_tuning.append(run_retrieval_tuning(knowledge))
    return {
        "batch": _summary_of(batch),
        "confusion_matrix": {
            "row_labels": list(PRIMARY_LABELS),
            "predicted_labels": list(PREDICTED_LABELS),
            "counts": counts,
        },
        "per_class_recall": per_class,
        "retrieval_tuning": retrieval_tuning,
        "bad_cases": bad_cases,
    }


def samples(
    db: Database,
    eval_batch_id: str,
    *,
    only_bad_cases: bool,
    split: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    _batch_row(db, eval_batch_id)
    clauses = ["eval_batch_id = ?"]
    values: list[Any] = [eval_batch_id]
    if only_bad_cases:
        clauses.append("(correct = 0 OR correct IS NULL)")
    if split:
        clauses.append("dataset_split = ?")
        values.append(split)
    where = " AND ".join(clauses)
    conn = db.connection()
    total = conn.execute(f"SELECT COUNT(*) AS c FROM eval_samples WHERE {where}", values).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM eval_samples WHERE {where} ORDER BY sample_no LIMIT ? OFFSET ?",
        [*values, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "items": [_sample_of(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }
