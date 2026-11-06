"""提示词文件加载（ARCH 附录 D / §7.6）。

文件头固定为 YAML 风格的 `version` / `updated_at`，正文从第二个 `---` 之后开始。
提示词只承载表达约束；阈值、规则与知识全部来自运行时输入，不写入文件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
_VERSION = re.compile(r"^version:\s*(.+?)\s*$", re.M)
_UPDATED_AT = re.compile(r"^updated_at:\s*(.+?)\s*$", re.M)


@dataclass(frozen=True)
class PromptDoc:
    name: str
    version: str
    updated_at: str
    body: str


class PromptLibrary:
    """按文件名读取提示词；文件缺失时抛出明确错误，不做静默降级。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._cache: dict[str, PromptDoc] = {}

    def get(self, name: str) -> PromptDoc:
        if name in self._cache:
            return self._cache[name]
        path = self.root / f"{name}.md"
        if not path.exists():
            raise RuntimeError(f"提示词文件不存在：{path}")
        raw = path.read_text(encoding="utf-8")
        match = _FRONT_MATTER.match(raw)
        header = match.group(1) if match else ""
        version = _VERSION.search(header)
        updated_at = _UPDATED_AT.search(header)
        doc = PromptDoc(
            name=name,
            version=version.group(1).strip().strip('"') if version else "unversioned",
            updated_at=updated_at.group(1).strip().strip('"') if updated_at else "",
            body=(raw[match.end() :] if match else raw).strip(),
        )
        self._cache[name] = doc
        return doc

    def version(self, name: str) -> str:
        return self.get(name).version

    def invalidate(self, name: str) -> None:
        self._cache.pop(name, None)
