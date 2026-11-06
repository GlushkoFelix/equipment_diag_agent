"""AC-SY-04：一键启动脚本存在且处理端口冲突。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_start_script_exists_with_port_conflict_guidance():
    candidates = [ROOT / "start.ps1", ROOT / "start.bat"]
    script = next((path for path in candidates if path.exists()), None)
    assert script is not None, "缺少 start.ps1 或 start.bat"
    content = script.read_text(encoding="utf-8-sig")
    assert "Port" in content or "PORT" in content
    assert "Get-NetTCPConnection" in content or "netstat" in content
    assert "已被占用" in content or "in use" in content
    assert "-Port 8010" in content or "--port 8010" in content
    assert "uvicorn" in content.lower() or "app.main" in content
    assert "/api/v1/health" in content
