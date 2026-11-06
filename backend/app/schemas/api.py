"""API 请求/响应 DTO（Pydantic v2，OpenAPI 3.1 唯一来源）。"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ---------- 枚举（ARCH §5.6，作为命名 Schema 暴露给前端） ----------
class InputType(str, Enum):
    csv_single = "csv_single"
    csv_batch = "csv_batch"
    form = "form"
    nl = "nl"
    chat = "chat"


class DiagnosisStatus(str, Enum):
    running = "running"
    waiting_human = "waiting_human"
    succeeded = "succeeded"
    degraded = "degraded"
    degraded_review = "degraded_review"
    aborted = "aborted"
    failed = "failed"
    failed_timeout = "failed_timeout"
    expired = "expired"


class BatchTaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    partially_failed = "partially_failed"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"


class BatchRowStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    degraded = "degraded"
    degraded_review = "degraded_review"
    failed = "failed"
    failed_timeout = "failed_timeout"
    cancelled = "cancelled"


class PrimaryType(str, Enum):
    normal = "正常"
    TWF = "TWF"
    HDF = "HDF"
    PWF = "PWF"
    OSF = "OSF"
    RNF = "RNF"
    uncovered = "未覆盖"


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Decision(str, Enum):
    confirm = "confirm"
    supplement = "supplement"
    abort = "abort"


# ---------- 认证与系统配置（ARCH §5.4.1 / §5.4.2） ----------
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class User(BaseModel):
    user_id: str
    username: str
    created_at: str | None = None
    last_login_at: str | None = None


class AuthResponse(BaseModel):
    """ARCH §5.4.1：登录/注册/当前用户统一返回 {"user": User}。"""

    user: User


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    checked_at: str
    dependencies: dict[str, str]


class LimitsOut(BaseModel):
    upload_max_bytes: int
    csv_max_rows: int
    page_size_default: int
    page_size_max: int
    device_id_max_length: int


class TimeoutsOut(BaseModel):
    global_timeout_seconds: int
    interrupt_ttl_minutes: int
    batch_task_timeout_minutes: int
    llm_call_budget_seconds: int
    llm_connect_timeout_seconds: int


class EnumsOut(BaseModel):
    input_types: list[str]
    diagnosis_status: list[DiagnosisStatus]
    batch_task_status: list[BatchTaskStatus]
    batch_row_status: list[BatchRowStatus]
    primary_types: list[str]
    confidence_levels: list[str]
    decisions: list[str]


class SystemConfig(BaseModel):
    limits: LimitsOut
    timeouts: TimeoutsOut
    enums: EnumsOut
    features: dict[str, bool]


# ---------- 上传与映射（ARCH §5.4.3） ----------
class UploadIssue(BaseModel):
    code: str
    message: str
    column: str | None = None
    row_no: int | None = None


class Mapping(BaseModel):
    """ARCH §5.4.3：7 个标准键必须出现，值可为 null。"""

    model_config = ConfigDict(extra="forbid")

    device_id: str | None = None
    product_type: str | None = None
    air_temp_k: str | None = None
    process_temp_k: str | None = None
    rotational_speed_rpm: str | None = None
    torque_nm: str | None = None
    tool_wear_min: str | None = None


class MappingScheme(BaseModel):
    mapping_id: str
    name: str
    header_signature: str
    mapping: Mapping
    default_device_id: str | None = None
    updated_at: str


class UploadPrecheck(BaseModel):
    upload_id: str
    file_name: str
    size_bytes: int
    encoding: str
    row_count: int
    headers: list[str]
    preview_rows: list[dict[str, str]]
    header_signature: str
    suggested_mapping: Mapping
    matched_scheme: MappingScheme | None = None
    issues: list[UploadIssue] = Field(default_factory=list)


class MappingPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapping: Mapping
    default_device_id: str | None = Field(default=None, max_length=64)
    mode: Literal["single", "batch"]
    row_no: int | None = None


class PreviewRow(BaseModel):
    row_no: int
    device_id: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    derived: dict[str, Any] = Field(default_factory=dict)
    data_quality_flags: list[str] = Field(default_factory=list)


class RowSummary(BaseModel):
    total: int
    valid: int
    invalid: int
    first_invalid: list[dict[str, Any]] = Field(default_factory=list)


class MappingPreviewResponse(BaseModel):
    valid: bool
    missing_required: list[str] = Field(default_factory=list)
    errors: list[UploadIssue] = Field(default_factory=list)
    preview: list[PreviewRow] = Field(default_factory=list)
    row_summary: RowSummary | None = None


class MappingSchemeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    header_signature: str
    mapping: Mapping
    default_device_id: str | None = Field(default=None, max_length=64)
    overwrite: bool = False


class MappingSchemesResponse(BaseModel):
    items: list[MappingScheme] = Field(default_factory=list)


# ---------- 诊断创建（ARCH §5.4.6 / §5.6.2） ----------
class DiagnosisCsvCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_type: Literal["csv_single"]
    upload_id: str
    row_no: int = Field(ge=1)
    mapping: dict[str, str] | None = None
    default_device_id: str | None = Field(default=None, max_length=64)


class DiagnosisFormCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_type: Literal["form"]
    device_id: str = Field(max_length=64)
    product_type: Literal["L", "M", "H"]
    air_temp_k: float
    process_temp_k: float
    rotational_speed_rpm: float
    torque_nm: float
    tool_wear_min: float


class DiagnosisNlCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_type: Literal["nl"]
    text: str = Field(min_length=1, max_length=2000)
    device_id: str = Field(max_length=64)
    product_type: Literal["L", "M", "H"] | None = None
    air_temp_k: float | None = None
    process_temp_k: float | None = None
    rotational_speed_rpm: float | None = None
    torque_nm: float | None = None
    tool_wear_min: float | None = None


DiagnosisCreateRequest = Annotated[
    Union[DiagnosisCsvCreate, DiagnosisFormCreate, DiagnosisNlCreate],
    Field(discriminator="input_type"),
]


class DiagnosisCreateResponse(BaseModel):
    diagnosis_id: str
    status: DiagnosisStatus
    input_type: InputType
    version: int
    diagnosis_revision: int
    deduplicated: bool
    created_at: str
    stream_url: str
    snapshot_url: str


class DiagnosisSummary(BaseModel):
    diagnosis_id: str
    device_id: str
    report_title: str | None = None
    input_type: InputType
    status: DiagnosisStatus
    primary_type: PrimaryType | None = None
    secondary_types: list[PrimaryType] = Field(default_factory=list)
    confidence: float | None = None
    confidence_level: ConfidenceLevel | None = None
    knowledge_status: str | None = None
    auto_review: bool = False
    retry_count: int = 0
    duration_ms: int | None = None
    started_at: str
    finished_at: str | None = None
    batch_task_id: str | None = None
    row_no: int | None = None


class DiagnosisListResponse(BaseModel):
    items: list[DiagnosisSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class ResumeRequest(BaseModel):
    decision: Decision
    supplement: dict[str, Any] | None = None
    version: int
    reason: str | None = None


# ---------- 抽取（ARCH §5.4.3 / §5.4.5 / §5.6.8） ----------
class FeatureValues(BaseModel):
    device_id: str | None = None
    product_type: str | None = None
    air_temp_k: float | None = None
    process_temp_k: float | None = None
    rotational_speed_rpm: float | None = None
    torque_nm: float | None = None
    tool_wear_min: float | None = None


class MissingField(BaseModel):
    field: str
    label: str
    unit: str | None = None
    example: Any = None
    reason: Literal["MISSING", "INVALID", "OUT_OF_RANGE"]


class SourceSpan(BaseModel):
    field: str | None = None
    start: int | None = None
    end: int | None = None
    text: str | None = None


class NlExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    input_type: Literal["nl", "chat"] = "nl"
    device_id_hint: str | None = None


class NlExtractResponse(BaseModel):
    extraction_status: Literal["ok", "partial", "failed"]
    text: str
    features: FeatureValues
    field_confidence: dict[str, float] = Field(default_factory=dict)
    source_spans: list[SourceSpan] = Field(default_factory=list)
    qualitative_cues: list[str] = Field(default_factory=list)
    missing_fields: list[MissingField]
    recommended_action: Literal["confirm", "clarify", "use_form"]
    message: str | None = None


class ChatExtraction(BaseModel):
    extraction_status: Literal["ok", "partial", "failed"] | None = None
    features: FeatureValues | None = None
    missing_fields: list[MissingField] = Field(default_factory=list)
    recommended_action: Literal["confirm", "clarify", "use_form"] | None = None
    field_confidence: dict[str, float] = Field(default_factory=dict)
    source_spans: list[SourceSpan] = Field(default_factory=list)


# ---------- 中断载荷（ARCH §5.6.8） ----------
class ClarificationPayload(BaseModel):
    created_at: str
    missing_fields: list[MissingField] = Field(default_factory=list)
    partial_features: dict[str, Any] = Field(default_factory=dict)
    device_id: str | None = None


class ConfidenceBreakdown(BaseModel):
    model_config = ConfigDict(extra="allow")

    rule: float | None = None
    coverage: float | None = None
    llm_self: float | None = None
    completeness: float | None = None
    penalties: float | None = None
    total: float | None = None


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    entry_id: str | None = None
    title: str | None = None
    fault_type: str | None = None
    feature: str | None = None
    value: float | str | None = None
    unit: str | None = None


class ReviewPayload(BaseModel):
    created_at: str
    primary_type: PrimaryType
    secondary_types: list[PrimaryType] = Field(default_factory=list)
    confidence: float
    confidence_level: ConfidenceLevel
    confidence_breakdown: ConfidenceBreakdown | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    reason: str
    missing_fields: list[MissingField] = Field(default_factory=list)
    review_round: int = 0


class Interrupt(BaseModel):
    type: Literal["clarification", "review"]
    payload: ClarificationPayload | ReviewPayload
    expires_at: str
    review_round: int = 0
    version: int


# ---------- 诊断快照（ARCH §5.6.4） ----------
class ElementsCheck(BaseModel):
    passed: bool
    present: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    report_retry_count: int = 0


class Report(BaseModel):
    markdown: str
    download_url: str


class ReportMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    template_version: str | None = None
    prompt_version: str | None = None
    kb_version: str | None = None
    model_name: str | None = None
    auto_review: bool = False
    generated_at: str | None = None
    degraded_reasons: list[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    step_id: str | None = None
    node: str | None = None
    event: str | None = None
    rule_id: str | None = None
    revision: int | None = None
    summary: str | None = None
    duration_ms: int | None = None
    created_at: str | None = None


class ErrorInfo(BaseModel):
    code: str | None = None
    message: str | None = None
    node: str | None = None
    recoverable: bool | None = None


class BatchRef(BaseModel):
    batch_task_id: str | None = None
    row_id: str | None = None
    row_no: int | None = None


class SnapshotFeatures(BaseModel):
    model_config = ConfigDict(extra="allow")

    normalized: dict[str, Any] = Field(default_factory=dict)
    derived: dict[str, Any] = Field(default_factory=dict)
    completeness: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    data_quality_flags: list[str] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="allow")

    entry_id: str | None = None
    fault_type: str | None = None
    title: str | None = None
    snippet: str | None = None
    score: float | None = None


class SnapshotRetrieval(BaseModel):
    model_config = ConfigDict(extra="allow")

    coverage: str | None = None
    max_score: float | None = None
    top_k: int | None = None
    retry_used: bool | None = None
    hits: list[RetrievalHit] = Field(default_factory=list)


class SnapshotTimings(BaseModel):
    total_ms: int = 0
    nodes: dict[str, int] = Field(default_factory=dict)


class InputSummary(BaseModel):
    file_name: str | None = None
    row_no: int | None = None
    text_excerpt: str | None = None


class DiagnosisSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    diagnosis_id: str
    device_id: str
    input_type: InputType
    input_summary: InputSummary = Field(default_factory=InputSummary)
    report_title: str | None = None
    status: DiagnosisStatus
    version: int
    diagnosis_revision: int
    primary_type: PrimaryType | None = None
    secondary_types: list[PrimaryType] = Field(default_factory=list)
    confidence: float | None = None
    confidence_level: ConfidenceLevel | None = None
    confidence_breakdown: ConfidenceBreakdown | None = None
    knowledge_status: Literal["supported", "missing"] | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    features: SnapshotFeatures | None = None
    retrieval: SnapshotRetrieval | None = None
    retry_count: int = 0
    review_round: int = 0
    report_retry_count: int = 0
    report_elements_check: ElementsCheck | None = None
    duration_ms: int = 0
    interrupt: Interrupt | None = None
    human_decision: Decision | None = None
    auto_review: bool = False
    report: Report | None = None
    report_meta: ReportMeta | None = None
    trace_steps: list[TraceStep] = Field(default_factory=list)
    timings: SnapshotTimings = Field(default_factory=SnapshotTimings)
    error: ErrorInfo | None = None
    batch: BatchRef | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


# ---------- 对话（ARCH §5.4.5） ----------
class ChatSessionCreateResponse(BaseModel):
    session_id: str
    status: Literal["draft"]
    created_at: str


class ChatMessage(BaseModel):
    message_id: str
    role: Literal["user", "agent"]
    text: str
    payload: dict[str, Any] | None = None
    created_at: str


class ChatSessionDetail(BaseModel):
    session_id: str
    status: Literal["draft", "active", "terminal"]
    diagnosis_id: str | None = None
    diagnosis_status: DiagnosisStatus | None = None
    created_at: str
    updated_at: str
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ChatExtractionResponse(BaseModel):
    """draft 首条消息的抽取确认卡（HANDOFF TBD-H 强制命名 Schema）。"""

    session_id: str
    message_id: str
    diagnosis_id: None = None
    diagnosis_status: None = None
    version: None = None
    agent_text: str
    interrupt: None = None
    extraction: ChatExtraction
    stream_url: None = None


class ChatSupplementResponse(BaseModel):
    session_id: str
    message_id: str
    diagnosis_id: str
    diagnosis_status: DiagnosisStatus
    version: int
    agent_text: str
    interrupt: Interrupt
    extraction: ChatExtraction
    stream_url: None = None


class ChatMessageResponse(BaseModel):
    """draft / supplement 两种消息响应的等价命名模型（前端单一引用）。"""

    session_id: str
    message_id: str
    diagnosis_id: str | None = None
    diagnosis_status: DiagnosisStatus | None = None
    version: int | None = None
    agent_text: str
    interrupt: Interrupt | None = None
    extraction: ChatExtraction | None = None
    stream_url: str | None = None


class ChatConfirmRequest(BaseModel):
    message_id: str | None = None
    text: str | None = Field(default=None, max_length=2000)
    features: dict[str, Any]


class ChatConfirmResponse(BaseModel):
    session_id: str
    diagnosis_id: str
    diagnosis_status: DiagnosisStatus
    version: int
    deduplicated: bool
    stream_url: str


# ---------- 批量（ARCH §5.4.7） ----------
class BatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str
    mapping: Mapping
    default_device_id: str | None = Field(default=None, max_length=64)


class BatchCounts(BaseModel):
    pending: int
    running: int
    succeeded: int
    degraded: int
    degraded_review: int
    failed: int
    failed_timeout: int
    cancelled: int


class BatchTaskSummary(BaseModel):
    batch_task_id: str
    file_name: str
    total_rows: int
    status: BatchTaskStatus
    default_device_id: str | None = None
    counts: BatchCounts
    completed_rows: int
    progress: float
    cancel_requested: bool
    timeout_deadline: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None


class BatchCreateResponse(BaseModel):
    batch_task_id: str
    status: BatchTaskStatus
    total_rows: int
    created_at: str
    stream_url: str
    snapshot_url: str


class BatchRowSummary(BaseModel):
    row_id: str
    row_no: int
    device_id: str | None = None
    status: BatchRowStatus
    diagnosis_id: str | None = None
    report_summary: str | None = None
    auto_review: bool = False
    duration_ms: int | None = None
    error_field: str | None = None
    error_code: str | None = None


class BatchRowDetail(BaseModel):
    row: BatchRowSummary
    report_url: str | None = None
    diagnosis_status: DiagnosisStatus | None = None


class CancelResponse(BaseModel):
    batch_task_id: str
    status: BatchTaskStatus
    cancel_requested: bool


class BatchPage(BaseModel):
    items: list[BatchTaskSummary] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    total_pages: int


class BatchRowsPage(BaseModel):
    items: list[BatchRowSummary] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    total_pages: int


# ---------- 评测（ARCH §5.4.8，只读） ----------
class EvalBatchSummary(BaseModel):
    eval_batch_id: str
    dataset_version: str | None = None
    prompt_version: str | None = None
    kb_version: str | None = None
    model_name: str | None = None
    sample_total: int
    edge_sample_total: int
    report_count: int
    failed_timeout_count: int
    accuracy: float | None = None
    completeness_rate: float | None = None
    timeout_rate: float | None = None
    fabrication_rate: float | None = None
    latency_sample_count: int
    latency_avg_ms: int | None = None
    latency_p50_ms: int | None = None
    latency_p95_ms: int | None = None
    latency_max_ms: int | None = None
    created_at: str


class EvalLatest(BaseModel):
    batch: EvalBatchSummary | None = None


class ConfusionMatrix(BaseModel):
    row_labels: list[str] = Field(default_factory=list)
    predicted_labels: list[str] = Field(default_factory=list)
    counts: list[list[int]] = Field(default_factory=list)


class PerClassRecall(BaseModel):
    label: str
    recall: float | None = None
    sample_count: int


class RetrievalParams(BaseModel):
    chunk_size: int | None = None
    overlap: int | None = None
    top_k: int | None = None


class RetrievalRun(BaseModel):
    run: int
    params: RetrievalParams = Field(default_factory=RetrievalParams)
    top5_hit_rate: float | None = None
    sample_total: int | None = None
    kb_version: str | None = None
    created_at: str | None = None
    backend: str | None = None


class RetrievalTuning(BaseModel):
    params: RetrievalParams = Field(default_factory=RetrievalParams)
    top5_hit_rate: float | None = None
    runs: list[RetrievalRun] = Field(default_factory=list)
    delta: float | None = None
    consistent: bool | None = None
    repeat: RetrievalRun | None = None
    kb_version: str | None = None
    created_at: str | None = None


class BadCase(BaseModel):
    sample_no: int
    sample_id: str
    expected_primary: str
    predicted_primary: str | None = None
    confidence: float | None = None
    error_category: str | None = None
    latency_ms: int | None = None


class EvalDetail(BaseModel):
    batch: EvalBatchSummary
    confusion_matrix: ConfusionMatrix
    per_class_recall: list[PerClassRecall] = Field(default_factory=list)
    retrieval_tuning: list[RetrievalTuning] = Field(default_factory=list)
    bad_cases: list[BadCase] = Field(default_factory=list)


class EvalSample(BaseModel):
    eval_sample_id: str
    eval_batch_id: str
    sample_no: int
    sample_id: str
    dataset_split: str
    expected_primary: str
    predicted_primary: str | None = None
    correct: bool | None = None
    confidence: float | None = None
    elements_present: int | None = None
    latency_ms: int | None = None
    status: str
    error_category: str | None = None


class EvalBatchPage(BaseModel):
    items: list[EvalBatchSummary] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    total_pages: int


class EvalSamplesPage(BaseModel):
    items: list[EvalSample] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    total_pages: int


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
