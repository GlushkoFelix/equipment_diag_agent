"""知识版本管理 CLI（AC-KB-03 / AC-KB-04 / OBS-02）。

用法（backend 目录下）：
    python scripts/kb_versions.py list
    python scripts/kb_versions.py import --file entries.jsonl --version kb_v2 [--activate]
    python scripts/kb_versions.py activate --version kb_v2
    python scripts/kb_versions.py rollback --version kb_v1

导入失败时打印逐条修复项并以退出码 2 结束；未激活索引不会被替换。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.knowledge import (  # noqa: E402
    KnowledgeImportError,
    KnowledgeService,
    load_entries_file,
)


def _service() -> tuple[Settings, Database, KnowledgeService]:
    settings = Settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.migrate()
    knowledge = KnowledgeService(settings, db)
    knowledge.ensure_built()
    return settings, db, knowledge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="知识版本手动激活/回滚")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出版本与状态")

    import_parser = sub.add_parser("import", help="导入新版本（默认不激活）")
    import_parser.add_argument("--file", required=True, help="JSON 数组或 JSONL 条目文件")
    import_parser.add_argument("--version", required=True, help="目标版本，如 kb_v2")
    import_parser.add_argument("--activate", action="store_true", help="导入成功后立即激活")

    activate_parser = sub.add_parser("activate", help="手动激活指定版本")
    activate_parser.add_argument("--version", required=True)

    rollback_parser = sub.add_parser("rollback", help="回滚到指定历史版本")
    rollback_parser.add_argument("--version", required=True)

    args = parser.parse_args(argv)
    _, db, knowledge = _service()
    try:
        if args.command == "list":
            for row in knowledge.list_versions():
                print(
                    f"{row['kb_version']}\t{row['status']}\tentries={row['entry_count']}"
                    f"\tbuilt_at={row['built_at']}"
                )
            return 0
        if args.command == "import":
            try:
                entries = load_entries_file(args.file)
            except KnowledgeImportError as exc:
                _print_repairs(exc)
                return 2
            version = knowledge.import_entries(
                entries, kb_version=args.version, activate=bool(args.activate)
            )
            print(f"imported {version} active={bool(args.activate)}")
            return 0
        if args.command == "activate":
            knowledge.activate(args.version)
            print(f"activated {args.version}")
            return 0
        knowledge.rollback(args.version)
        print(f"rolled back to {args.version}")
        return 0
    except KnowledgeImportError as exc:
        _print_repairs(exc)
        return 2
    finally:
        db.close()


def _print_repairs(exc: KnowledgeImportError) -> None:
    print("知识导入失败，修复项：", file=sys.stderr)
    for item in exc.details:
        print(
            f"  - index={item.get('entry_index')} entry_id={item.get('entry_id')}"
            f" field={item.get('field')} reason={item.get('reason')}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())
