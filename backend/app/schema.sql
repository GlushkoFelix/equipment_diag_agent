-- app.db schema v1（逐字对应 docs/DB-数据库设计文档.md §6；禁止在此增删字段）
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    NOT NULL,
    checksum    TEXT    NOT NULL,
    note        TEXT
);

CREATE TABLE users (
    user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL COLLATE NOCASE,
    password_hash   TEXT    NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_login_at   TEXT,
    CHECK (length(username) BETWEEN 1 AND 64),
    CHECK (password_hash LIKE '$2%'),
    CHECK (failed_attempts >= 0),
    CHECK (locked_until IS NULL OR locked_until >= created_at)
);
CREATE UNIQUE INDEX ux_users_username ON users (username);

CREATE TABLE sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at  TEXT NOT NULL,
    revoked_at  TEXT,
    CHECK (expires_at > created_at),
    CHECK (length(token_hash) >= 32),
    CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);
CREATE UNIQUE INDEX ux_sessions_token_hash ON sessions (token_hash);
CREATE INDEX ix_sessions_expires ON sessions (expires_at);

CREATE TABLE uploads (
    upload_id        TEXT PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    original_name    TEXT NOT NULL,
    stored_path      TEXT NOT NULL,
    size_bytes       INTEGER NOT NULL,
    encoding         TEXT NOT NULL,
    row_count        INTEGER NOT NULL,
    headers_json     TEXT NOT NULL,
    header_signature TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (upload_id GLOB 'up_*'
           AND length(upload_id) BETWEEN 13 AND 43
           AND substr(upload_id, 4) NOT GLOB '*[^0-9A-Za-z]*'),
    CHECK (length(original_name) BETWEEN 1 AND 255),
    CHECK (length(stored_path) > 0 AND stored_path NOT LIKE '%..%'),
    CHECK (size_bytes BETWEEN 1 AND 5242880),
    CHECK (encoding IN ('utf-8','gbk')),
    CHECK (row_count BETWEEN 1 AND 500),
    CHECK (json_valid(headers_json) AND json_type(headers_json) = 'array'),
    CHECK (header_signature LIKE 'sha256:%' AND length(header_signature) = 71)
);
CREATE UNIQUE INDEX ux_uploads_stored_path ON uploads (stored_path);
CREATE INDEX ix_uploads_user_created ON uploads (user_id, created_at DESC);
CREATE INDEX ix_uploads_user_sig ON uploads (user_id, header_signature);

CREATE TABLE mapping_schemes (
    mapping_id       TEXT PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    header_signature TEXT NOT NULL,
    mapping_json     TEXT NOT NULL,
    default_device_id TEXT,
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (mapping_id GLOB 'map_*'),
    CHECK (length(name) BETWEEN 1 AND 64),
    CHECK (json_valid(mapping_json) AND json_type(mapping_json) = 'object'),
    CHECK (default_device_id IS NULL OR length(default_device_id) BETWEEN 1 AND 64)
);
CREATE UNIQUE INDEX ux_mapping_user_name ON mapping_schemes (user_id, name);
CREATE INDEX ix_mapping_user_sig ON mapping_schemes (user_id, header_signature);

CREATE TABLE batch_tasks (
    batch_task_id        TEXT PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES users(user_id),
    file_name            TEXT NOT NULL,
    upload_id            TEXT NOT NULL REFERENCES uploads(upload_id),
    total_rows           INTEGER NOT NULL,
    status               TEXT NOT NULL DEFAULT 'queued',
    default_device_id    TEXT,
    pending_rows         INTEGER NOT NULL DEFAULT 0,
    running_rows         INTEGER NOT NULL DEFAULT 0,
    succeeded_rows       INTEGER NOT NULL DEFAULT 0,
    degraded_rows        INTEGER NOT NULL DEFAULT 0,
    degraded_review_rows INTEGER NOT NULL DEFAULT 0,
    failed_rows          INTEGER NOT NULL DEFAULT 0,
    failed_timeout_rows  INTEGER NOT NULL DEFAULT 0,
    cancelled_rows       INTEGER NOT NULL DEFAULT 0,
    timeout_deadline     TEXT NOT NULL,
    cancel_requested_at  TEXT,
    error_code           TEXT,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    started_at           TEXT,
    finished_at          TEXT,
    CHECK (batch_task_id GLOB 'bch_*'),
    CHECK (total_rows BETWEEN 1 AND 500),
    CHECK (status IN ('queued','running','completed','partially_failed','failed','cancelled','timed_out')),
    CHECK (pending_rows >= 0 AND running_rows >= 0 AND succeeded_rows >= 0
           AND degraded_rows >= 0 AND degraded_review_rows >= 0
           AND failed_rows >= 0 AND failed_timeout_rows >= 0 AND cancelled_rows >= 0),
    CHECK (pending_rows + running_rows + succeeded_rows + degraded_rows
           + degraded_review_rows + failed_rows + failed_timeout_rows
           + cancelled_rows = total_rows),
    CHECK (timeout_deadline >= created_at),
    CHECK (started_at IS NULL OR started_at >= created_at),
    CHECK (finished_at IS NULL OR finished_at >= created_at)
);
CREATE INDEX ix_batch_user_created ON batch_tasks (user_id, created_at DESC);
CREATE INDEX ix_batch_status ON batch_tasks (status);
CREATE INDEX ix_batch_upload ON batch_tasks (upload_id);

CREATE TABLE batch_rows (
    row_id         TEXT PRIMARY KEY,
    batch_task_id  TEXT NOT NULL REFERENCES batch_tasks(batch_task_id) ON DELETE CASCADE,
    row_no         INTEGER NOT NULL,
    device_id      TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    diagnosis_id   TEXT REFERENCES diagnoses(diagnosis_id),
    report_summary TEXT,
    auto_review    INTEGER NOT NULL DEFAULT 0,
    duration_ms    INTEGER,
    error_field    TEXT,
    error_code     TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (row_id GLOB 'row_*'),
    CHECK (row_no >= 1),
    CHECK (device_id IS NULL OR length(device_id) BETWEEN 1 AND 64),
    CHECK (status IN ('pending','running','succeeded','degraded','degraded_review',
                      'failed','failed_timeout','cancelled')),
    CHECK (auto_review IN (0,1)),
    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CHECK (status NOT IN ('failed','failed_timeout','cancelled') OR report_summary IS NULL)
);
CREATE UNIQUE INDEX ux_rows_task_no ON batch_rows (batch_task_id, row_no);
CREATE UNIQUE INDEX ux_rows_diagnosis ON batch_rows (diagnosis_id) WHERE diagnosis_id IS NOT NULL;
CREATE INDEX ix_rows_task_status ON batch_rows (batch_task_id, status);

CREATE TABLE diagnoses (
    diagnosis_id               TEXT PRIMARY KEY,
    user_id                    INTEGER NOT NULL REFERENCES users(user_id),
    device_id                  TEXT NOT NULL,
    input_type                 TEXT NOT NULL,
    input_summary_json         TEXT NOT NULL,
    status                     TEXT NOT NULL DEFAULT 'running',
    primary_type               TEXT,
    secondary_types_json       TEXT,
    confidence                 REAL,
    confidence_level           TEXT,
    confidence_breakdown_json  TEXT,
    knowledge_status           TEXT,
    evidence_refs_json         TEXT,
    retry_count                INTEGER NOT NULL DEFAULT 0,
    review_round               INTEGER NOT NULL DEFAULT 0,
    report_retry_count         INTEGER NOT NULL DEFAULT 0,
    diagnosis_revision         INTEGER NOT NULL DEFAULT 1,
    input_fingerprint          TEXT,
    fingerprint_scope          TEXT,
    active_fingerprint_key     TEXT,
    execution_mode             TEXT NOT NULL DEFAULT 'single',
    batch_task_id              TEXT REFERENCES batch_tasks(batch_task_id),
    row_id                     TEXT REFERENCES batch_rows(row_id),
    upload_id                  TEXT REFERENCES uploads(upload_id),
    auto_review                INTEGER NOT NULL DEFAULT 0,
    report_title               TEXT,
    report_md                  TEXT,
    report_meta_json           TEXT,
    report_elements_check_json TEXT,
    human_decision             TEXT,
    interrupt_type             TEXT,
    interrupt_payload_json     TEXT,
    interrupt_expires_at       TEXT,
    error_code                 TEXT,
    duration_ms                INTEGER,
    started_at                 TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_at                 TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at                TEXT,
    version                    INTEGER NOT NULL DEFAULT 1,

    CHECK (diagnosis_id GLOB 'dx_*' AND length(diagnosis_id) BETWEEN 13 AND 43),
    CHECK (length(device_id) BETWEEN 1 AND 64),
    CHECK (input_type IN ('csv_single','csv_batch','form','nl','chat')),
    CHECK (execution_mode IN ('single','batch','eval')),
    CHECK (execution_mode = 'single' OR status NOT IN ('waiting_human','expired')),
    CHECK (interrupt_type IS NULL OR interrupt_type <> 'clarification'
           OR (execution_mode = 'single' AND input_type IN ('nl','chat'))),
    CHECK (json_valid(input_summary_json) AND json_type(input_summary_json) = 'object'),

    CHECK (status IN ('running','waiting_human','succeeded','degraded','degraded_review',
                      'aborted','failed','failed_timeout','expired')),
    CHECK (primary_type IS NULL OR primary_type IN ('正常','TWF','HDF','PWF','OSF','RNF','未覆盖')),
    CHECK (secondary_types_json IS NULL
           OR (json_valid(secondary_types_json) AND json_type(secondary_types_json) = 'array')),
    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CHECK (confidence_level IS NULL OR confidence_level IN ('high','medium','low')),
    CHECK ((confidence IS NULL) = (confidence_level IS NULL)),
    CHECK (confidence IS NULL OR confidence_level IS NULL
           OR confidence_level = CASE
                WHEN confidence >= 0.8 THEN 'high'
                WHEN confidence >= 0.5 THEN 'medium'
                ELSE 'low' END),
    CHECK (confidence_breakdown_json IS NULL
           OR (json_valid(confidence_breakdown_json) AND json_type(confidence_breakdown_json) = 'object')),
    CHECK (knowledge_status IS NULL OR knowledge_status IN ('supported','missing')),
    CHECK (evidence_refs_json IS NULL
           OR (json_valid(evidence_refs_json) AND json_type(evidence_refs_json) = 'array')),

    CHECK (retry_count BETWEEN 0 AND 1),
    CHECK (report_retry_count BETWEEN 0 AND 1),
    CHECK (review_round BETWEEN 0 AND 2),
    CHECK (diagnosis_revision >= 1),

    CHECK (input_fingerprint IS NULL
           OR (input_fingerprint LIKE 'sha256:%' AND length(input_fingerprint) = 71)),
    CHECK (fingerprint_scope IS NULL OR fingerprint_scope IN ('dedupe','trace')),
    CHECK ((input_fingerprint IS NULL) = (fingerprint_scope IS NULL)),
    CHECK (execution_mode = 'eval'
           OR input_type NOT IN ('csv_single','form')
           OR (input_fingerprint IS NOT NULL AND fingerprint_scope = 'dedupe')),
    CHECK (input_type NOT IN ('nl','chat') OR input_fingerprint IS NULL
           OR fingerprint_scope = 'dedupe'),
    CHECK (execution_mode <> 'batch'
           OR (input_fingerprint IS NOT NULL AND fingerprint_scope = 'trace')),
    CHECK (execution_mode <> 'eval'
           OR (input_fingerprint IS NULL AND fingerprint_scope IS NULL
               AND active_fingerprint_key IS NULL)),
    CHECK (active_fingerprint_key IS NULL
           OR (execution_mode = 'single' AND input_fingerprint IS NOT NULL
               AND status IN ('running','waiting_human'))),
    CHECK (active_fingerprint_key IS NULL
           OR active_fingerprint_key = CAST(user_id AS TEXT) || ':' || input_fingerprint),

    CHECK (execution_mode <> 'batch'
           OR (batch_task_id IS NOT NULL AND row_id IS NOT NULL)),
    CHECK (execution_mode = 'batch'
           OR (batch_task_id IS NULL AND row_id IS NULL)),
    CHECK (input_type NOT IN ('csv_single','csv_batch') OR upload_id IS NOT NULL
           OR execution_mode = 'eval'),
    CHECK (input_type <> 'csv_batch' OR execution_mode = 'batch'),
    CHECK (input_type NOT IN ('csv_single','form') OR execution_mode IN ('single','eval')),
    CHECK (input_type NOT IN ('nl','chat') OR execution_mode = 'single'),

    CHECK (auto_review IN (0,1)),
    CHECK (auto_review = 0 OR execution_mode = 'batch'),
    CHECK (auto_review = 0 OR status <> 'succeeded'),
    CHECK (status <> 'degraded_review' OR auto_review = 1),

    CHECK (human_decision IS NULL OR human_decision IN ('confirm','supplement','abort')),

    CHECK (interrupt_type IS NULL OR interrupt_type IN ('clarification','review')),
    CHECK (interrupt_payload_json IS NULL
           OR (json_valid(interrupt_payload_json) AND json_type(interrupt_payload_json) = 'object')),
    CHECK (
        (status IN ('waiting_human','expired')
         AND interrupt_type IS NOT NULL
         AND interrupt_payload_json IS NOT NULL
         AND interrupt_expires_at IS NOT NULL)
        OR
        (status NOT IN ('waiting_human','expired')
         AND interrupt_type IS NULL
         AND interrupt_payload_json IS NULL
         AND interrupt_expires_at IS NULL)
    ),

    CHECK (report_meta_json IS NULL OR (json_valid(report_meta_json) AND json_type(report_meta_json) = 'object')),
    CHECK (report_elements_check_json IS NULL
           OR (json_valid(report_elements_check_json)
               AND json_type(report_elements_check_json) = 'object')),
    CHECK (report_md IS NULL
           OR (status IN ('succeeded','degraded','degraded_review')
               AND report_title IS NOT NULL
               AND report_meta_json IS NOT NULL
               AND report_elements_check_json IS NOT NULL)),
    CHECK (status NOT IN ('succeeded','degraded','degraded_review')
           OR report_md IS NOT NULL),

    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK (version >= 1)
);

CREATE INDEX ix_diagnoses_user_started
    ON diagnoses (user_id, started_at DESC, diagnosis_id DESC);
CREATE INDEX ix_diagnoses_user_status ON diagnoses (user_id, status);
CREATE INDEX ix_diagnoses_user_primary ON diagnoses (user_id, primary_type);
CREATE INDEX ix_diagnoses_user_confidence ON diagnoses (user_id, confidence_level);
CREATE INDEX ix_diagnoses_batch ON diagnoses (batch_task_id) WHERE batch_task_id IS NOT NULL;
CREATE INDEX ix_diagnoses_upload ON diagnoses (upload_id) WHERE upload_id IS NOT NULL;
CREATE INDEX ix_diagnoses_ttl
    ON diagnoses (status, interrupt_expires_at)
    WHERE status = 'waiting_human' AND interrupt_expires_at IS NOT NULL;
CREATE UNIQUE INDEX ux_diagnoses_active_fp
    ON diagnoses (user_id, active_fingerprint_key)
    WHERE active_fingerprint_key IS NOT NULL;
CREATE UNIQUE INDEX ux_diagnoses_row
    ON diagnoses (row_id) WHERE row_id IS NOT NULL;

CREATE TABLE diagnosis_steps (
    step_id      TEXT PRIMARY KEY,
    diagnosis_id TEXT NOT NULL REFERENCES diagnoses(diagnosis_id) ON DELETE CASCADE,
    revision     INTEGER NOT NULL,
    node         TEXT NOT NULL,
    event        TEXT NOT NULL,
    rule_id      TEXT,
    summary      TEXT,
    duration_ms  INTEGER,
    error_code   TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (revision >= 1),
    CHECK (event IN ('start','end','retry','rebuild','interrupt','resume',
                     'degrade','timeout','auto_degrade','user_correct')),
    CHECK (duration_ms IS NULL OR duration_ms >= 0)
);
CREATE INDEX ix_steps_diag_rev_time
    ON diagnosis_steps (diagnosis_id, revision, created_at, step_id);

CREATE TABLE diagnosis_events (
    event_id     TEXT PRIMARY KEY,
    diagnosis_id TEXT NOT NULL REFERENCES diagnoses(diagnosis_id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    type         TEXT NOT NULL,
    revision     INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (seq >= 1),
    CHECK (revision >= 1),
    CHECK (json_valid(payload_json) AND json_type(payload_json) = 'object')
);
CREATE UNIQUE INDEX ux_events_diag_seq ON diagnosis_events (diagnosis_id, seq);

CREATE TABLE batch_events (
    event_id      TEXT PRIMARY KEY,
    batch_task_id TEXT NOT NULL REFERENCES batch_tasks(batch_task_id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    type          TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (seq >= 1),
    CHECK (json_valid(payload_json) AND json_type(payload_json) = 'object')
);
CREATE UNIQUE INDEX ux_batch_events_seq ON batch_events (batch_task_id, seq);

CREATE TABLE chat_sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    diagnosis_id TEXT REFERENCES diagnoses(diagnosis_id) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT 'draft',
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (session_id GLOB 'cht_*'),
    CHECK (status IN ('draft','active','terminal')),
    CHECK ((status = 'draft'   AND diagnosis_id IS NULL)
        OR (status = 'active'  AND diagnosis_id IS NOT NULL)
        OR (status = 'terminal'))
);
CREATE UNIQUE INDEX ux_chat_diagnosis
    ON chat_sessions (diagnosis_id) WHERE diagnosis_id IS NOT NULL;
CREATE INDEX ix_chat_user_created ON chat_sessions (user_id, created_at DESC);

CREATE TABLE chat_messages (
    message_id  TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    text        TEXT NOT NULL,
    payload_json TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (message_id GLOB 'msg_*'),
    CHECK (role IN ('user','agent')),
    CHECK (payload_json IS NULL OR (json_valid(payload_json) AND json_type(payload_json) = 'object'))
);
CREATE INDEX ix_messages_session_time ON chat_messages (session_id, created_at, message_id);

CREATE TABLE knowledge_versions (
    kb_version    TEXT PRIMARY KEY,
    entry_count   INTEGER NOT NULL,
    chunk_size    INTEGER NOT NULL,
    overlap       INTEGER NOT NULL,
    model_name    TEXT NOT NULL,
    model_version TEXT NOT NULL,
    built_at      TEXT NOT NULL,
    status        TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    CHECK (entry_count >= 1),
    CHECK (chunk_size > 0),
    CHECK (overlap >= 0 AND overlap < chunk_size),
    CHECK (status IN ('active','archived')),
    CHECK (length(manifest_path) > 0 AND manifest_path NOT LIKE '%..%')
);
CREATE UNIQUE INDEX ux_knowledge_active
    ON knowledge_versions (status) WHERE status = 'active';
CREATE UNIQUE INDEX ux_knowledge_manifest ON knowledge_versions (manifest_path);
CREATE INDEX ix_knowledge_status_built ON knowledge_versions (status, built_at DESC);

CREATE TABLE eval_batches (
    eval_batch_id         TEXT PRIMARY KEY,
    dataset_version       TEXT NOT NULL,
    prompt_version        TEXT NOT NULL,
    kb_version            TEXT NOT NULL,
    model_name            TEXT NOT NULL,
    sample_total          INTEGER NOT NULL,
    edge_sample_total     INTEGER NOT NULL,
    report_count          INTEGER NOT NULL DEFAULT 0,
    failed_timeout_count  INTEGER NOT NULL DEFAULT 0,
    latency_sample_count  INTEGER NOT NULL DEFAULT 0,
    accuracy              REAL,
    completeness_rate     REAL,
    fabrication_rate      REAL,
    timeout_rate          REAL,
    latency_avg_ms        INTEGER,
    latency_p50_ms        INTEGER,
    latency_p95_ms        INTEGER,
    latency_max_ms        INTEGER,
    artifact_path         TEXT,
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (eval_batch_id GLOB 'evb_*'),
    CHECK (sample_total >= 1),
    CHECK (edge_sample_total >= 0 AND edge_sample_total <= sample_total),
    CHECK (report_count BETWEEN 0 AND sample_total),
    CHECK (failed_timeout_count BETWEEN 0 AND sample_total),
    CHECK (latency_sample_count BETWEEN 0 AND sample_total),
    CHECK (accuracy IS NULL OR (accuracy >= 0 AND accuracy <= 1)),
    CHECK (completeness_rate IS NULL OR (completeness_rate >= 0 AND completeness_rate <= 1)),
    CHECK (fabrication_rate IS NULL OR (fabrication_rate >= 0 AND fabrication_rate <= 1)),
    CHECK (timeout_rate IS NULL OR (timeout_rate >= 0 AND timeout_rate <= 1)),
    CHECK (latency_avg_ms IS NULL OR latency_avg_ms >= 0),
    CHECK (latency_p50_ms IS NULL OR latency_p50_ms >= 0),
    CHECK (latency_p95_ms IS NULL OR latency_p95_ms >= 0),
    CHECK (latency_max_ms IS NULL OR latency_max_ms >= 0),
    CHECK (latency_p50_ms IS NULL OR latency_p95_ms IS NULL OR latency_p50_ms <= latency_p95_ms),
    CHECK (latency_p95_ms IS NULL OR latency_max_ms IS NULL OR latency_p95_ms <= latency_max_ms)
);
CREATE INDEX ix_eval_created ON eval_batches (created_at DESC);

CREATE TABLE eval_samples (
    eval_sample_id   TEXT PRIMARY KEY,
    eval_batch_id    TEXT NOT NULL REFERENCES eval_batches(eval_batch_id) ON DELETE CASCADE,
    sample_no        INTEGER NOT NULL,
    sample_id        TEXT NOT NULL,
    dataset_split    TEXT NOT NULL,
    expected_primary TEXT NOT NULL,
    predicted_primary TEXT,
    correct          INTEGER,
    confidence       REAL,
    elements_present INTEGER,
    latency_ms       INTEGER,
    status           TEXT NOT NULL,
    error_category   TEXT,
    CHECK (eval_sample_id GLOB 'evs_*'),
    CHECK (sample_no >= 1),
    CHECK (dataset_split IN ('eval','tuning','edge')),
    CHECK (expected_primary IN ('正常','TWF','HDF','PWF','OSF','RNF','未覆盖')),
    CHECK (predicted_primary IS NULL
           OR predicted_primary IN ('正常','TWF','HDF','PWF','OSF','RNF','未覆盖')),
    CHECK (correct IS NULL OR correct IN (0,1)),
    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CHECK (elements_present IS NULL OR elements_present BETWEEN 0 AND 8),
    CHECK (latency_ms IS NULL OR latency_ms >= 0),
    CHECK (status IN ('succeeded','degraded','failed','failed_timeout')),
    CHECK (error_category IS NULL OR error_category IN
           ('feature_missing','retrieval_miss','rule_misjudge','llm_misjudge',
            'report_missing_element','latency_exceeded'))
);
CREATE UNIQUE INDEX ux_samples_batch_no ON eval_samples (eval_batch_id, sample_no);
CREATE INDEX ix_samples_batch_status ON eval_samples (eval_batch_id, status);
CREATE INDEX ix_samples_split ON eval_samples (eval_batch_id, dataset_split, sample_id);

CREATE TABLE idempotency_keys (
    user_id       INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    endpoint      TEXT NOT NULL,
    key           TEXT NOT NULL,
    request_hash  TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code   INTEGER NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at    TEXT NOT NULL,
    PRIMARY KEY (user_id, endpoint, key),
    CHECK (length(endpoint) BETWEEN 1 AND 64),
    CHECK (length(key) BETWEEN 1 AND 128),
    CHECK (request_hash LIKE 'sha256:%'),
    CHECK (json_valid(response_json) AND json_type(response_json) = 'object'),
    CHECK (status_code BETWEEN 200 AND 599),
    CHECK (expires_at > created_at)
);
CREATE INDEX ix_idem_expires ON idempotency_keys (expires_at);

CREATE TRIGGER trg_diagnoses_version_monotonic
BEFORE UPDATE ON diagnoses
WHEN NEW.version < OLD.version
   OR (NEW.version = OLD.version AND NEW.status <> OLD.status)
BEGIN
    SELECT RAISE(ABORT, 'DIAGNOSIS_VERSION_MUST_INCREASE_WITH_STATUS_CHANGE');
END;

CREATE TRIGGER trg_diagnoses_terminal_immutable
BEFORE UPDATE OF status ON diagnoses
WHEN OLD.status IN ('succeeded','degraded','degraded_review','aborted',
                    'failed','failed_timeout','expired')
 AND NEW.status <> OLD.status
BEGIN
    SELECT RAISE(ABORT, 'DIAGNOSIS_TERMINAL_IMMUTABLE');
END;

CREATE TRIGGER trg_diagnoses_no_delete_batch
BEFORE DELETE ON diagnoses
WHEN OLD.execution_mode = 'batch'
BEGIN
    SELECT RAISE(ABORT, 'BATCH_DIAGNOSIS_DELETE_FORBIDDEN');
END;

CREATE TRIGGER trg_chat_sessions_status_transition
BEFORE UPDATE OF status ON chat_sessions
WHEN NOT (
    (OLD.status = 'draft' AND NEW.status IN ('draft','active'))
 OR (OLD.status = 'active' AND NEW.status IN ('active','terminal'))
 OR (OLD.status = 'terminal' AND NEW.status = 'terminal')
)
BEGIN
    SELECT RAISE(ABORT, 'CHAT_SESSION_STATUS_INVALID');
END;

CREATE TRIGGER trg_chat_sessions_no_rebind
BEFORE UPDATE OF diagnosis_id ON chat_sessions
WHEN OLD.diagnosis_id IS NOT NULL
 AND NEW.diagnosis_id IS NOT NULL
 AND NEW.diagnosis_id <> OLD.diagnosis_id
BEGIN
    SELECT RAISE(ABORT, 'CHAT_SESSION_REBIND_FORBIDDEN');
END;

CREATE TRIGGER trg_diagnosis_steps_no_update
BEFORE UPDATE ON diagnosis_steps
BEGIN
    SELECT RAISE(ABORT, 'DIAGNOSIS_STEPS_APPEND_ONLY');
END;

CREATE TRIGGER trg_diagnosis_events_no_update
BEFORE UPDATE ON diagnosis_events
BEGIN
    SELECT RAISE(ABORT, 'DIAGNOSIS_EVENTS_APPEND_ONLY');
END;

CREATE TRIGGER trg_batch_events_no_update
BEFORE UPDATE ON batch_events
BEGIN
    SELECT RAISE(ABORT, 'BATCH_EVENTS_APPEND_ONLY');
END;

CREATE TRIGGER trg_chat_messages_no_update
BEFORE UPDATE ON chat_messages
BEGIN
    SELECT RAISE(ABORT, 'CHAT_MESSAGES_APPEND_ONLY');
END;
