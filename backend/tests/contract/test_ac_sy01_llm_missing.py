"""AC-SY-01：缺 LLM Key 启动 → /health 列缺失项、历史可读、诊断 503、进程继续服务。"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FORM_INPUT
from tests.support import PREFIX, app_client, write_evidence


def test_ac_sy01_missing_llm_key_health_history_and_503(tmp_path: Path):
    with app_client(tmp_path, llm_mode="deepseek", deepseek_api_key="") as client:
        health = client.get(f"{PREFIX}/health")
        assert health.status_code == 200, health.text
        body = health.json()
        assert body["dependencies"]["llm_config"] == "missing"
        assert "EDG_DEEPSEEK_API_KEY" in body["dependencies"]["llm_config_missing"]
        assert body["status"] == "degraded"

        history = client.get(f"{PREFIX}/diagnoses")
        assert history.status_code == 200, history.text
        assert history.json()["total"] == 0

        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        assert created.status_code == 503, created.text
        error = created.json()["error"]
        assert error["code"] == "LLM_NOT_CONFIGURED"
        assert "DeepSeek Key" in error["message"]

        again = client.get(f"{PREFIX}/health")
        assert again.status_code == 200
        assert again.json()["dependencies"]["llm_config"] == "missing"

        write_evidence(
            "AC-SY-01-llm-missing",
            {
                "health_dependencies": body["dependencies"],
                "health_status": body["status"],
                "history_status": history.status_code,
                "history_total": history.json()["total"],
                "diagnosis_status": created.status_code,
                "diagnosis_error": error,
                "health_after_diagnosis": again.status_code,
            },
        )
