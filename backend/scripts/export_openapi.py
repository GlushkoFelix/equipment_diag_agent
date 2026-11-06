"""导出 OpenAPI 3.1 契约到 docs/openapi.json（CI diff 用）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    app = create_app()
    spec = app.openapi()
    target = REPO_ROOT / "docs" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target} ({len(spec['paths'])} paths)")


if __name__ == "__main__":
    main()
