"""OpenAPI 契约：路径、Schema 命名与 oneOf 判别。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

PREFIX = "/api/v1"
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_openapi_contains_required_paths_and_schemas(client: TestClient):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    required = [
        "/auth/register",
        "/auth/login",
        "/auth/logout",
        "/auth/me",
        "/health",
        "/system/config",
        "/uploads",
        "/uploads/{upload_id}",
        "/nl/extract",
        "/chat/sessions",
        "/chat/sessions/{session_id}",
        "/chat/sessions/{session_id}/messages",
        "/chat/sessions/{session_id}/confirm",
        "/diagnoses",
        "/diagnoses/{diagnosis_id}",
        "/diagnoses/{diagnosis_id}/events",
        "/diagnoses/{diagnosis_id}/resume",
        "/diagnoses/{diagnosis_id}/report.md",
        "/diagnoses/{diagnosis_id}",
    ]
    for path in required:
        assert f"{PREFIX}{path}" in paths, path

    schemas = spec["components"]["schemas"]
    assert "ChatExtractionResponse" in schemas
    assert "ChatSupplementResponse" in schemas
    assert "ChatConfirmResponse" in schemas
    assert "DiagnosisSnapshot" in schemas
    assert "DiagnosisCreateResponse" in schemas

    request_schema = paths[f"{PREFIX}/diagnoses"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert "$ref" in request_schema or "oneOf" in request_schema
    body_ref = request_schema.get("$ref")
    if body_ref:
        model = schemas[body_ref.split("/")[-1]]
        assert "oneOf" in model or "anyOf" in model


def test_openapi_diagnosis_create_has_three_variants(client: TestClient):
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    names = set(schemas)
    for name in ("DiagnosisCsvCreate", "DiagnosisFormCreate", "DiagnosisNlCreate"):
        assert name in names, name


def test_docs_openapi_json_in_sync(client: TestClient):
    """docs/openapi.json 必须与代码生成结果一致（CI diff 为空）。"""
    generated = client.get("/openapi.json").json()
    committed = json.loads((REPO_ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    assert committed == generated
