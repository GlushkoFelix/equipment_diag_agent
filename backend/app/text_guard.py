"""输入文本安全护栏：提示词注入检测与敏感词过滤（AC-SE-01 / AC-SE-03）。

约束：
- 日志只记录模式名、命中数量与文本 sha256，不记录原文，满足脱敏要求。
- 注入指令被替换为空格后继续正常诊断，不改变 API/SSE/状态机契约。
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from app.config import REPO_ROOT

logger = logging.getLogger("edg.security")

SENSITIVE_WORDS_PATH = REPO_ROOT / "config" / "sensitive_words.txt"

# 兜底词表：仅在 config/sensitive_words.txt 缺失时使用，正常路径始终加载文件。
_DEFAULT_SENSITIVE_WORDS = (
    "炸毁",
    "引爆",
    "攻击",
    "杀人",
    "爆炸",
    "投毒",
    "自杀",
    "枪支",
    "弹药",
    "恐怖袭击",
    "病毒制造",
    "危害公共安全",
)

# 提示词注入：覆盖中文指令覆盖、英文指令覆盖、提示词窃取与角色劫持四类。
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions_en",
        re.compile(
            r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:the\s+)?"
            r"(?:previous|prior|above|earlier)\s+(?:instructions?|prompts?|rules?)",
            re.I,
        ),
    ),
    (
        "ignore_instructions_zh",
        re.compile(
            r"(?:忽略|无视|忘记|不要遵守|别管|抛开)\s*(?:以上|之前|前面|上述)?\s*"
            r"(?:所有|全部)?\s*(?:的)?\s*(?:指令|指示|提示词?|规则|要求)"
        ),
    ),
    (
        "prompt_exfiltration_en",
        re.compile(
            r"(?:reveal|show|print|output|repeat|display|leak)\s+(?:the\s+)?"
            r"(?:system\s+prompt|hidden\s+prompt|developer\s+message|instructions?)",
            re.I,
        ),
    ),
    (
        "prompt_exfiltration_zh",
        re.compile(r"(?:输出|显示|打印|泄露|暴露)\s*(?:你的|系统的)?\s*(?:系统提示词|隐藏指令|提示词)"),
    ),
    (
        "role_hijack",
        re.compile(
            r"(?:你现在是|现在你是|从现在开始你是|you\s+are\s+now|act\s+as)\s*"
            r"(?:系统管理员|系统|管理员|developer|root|admin)",
            re.I,
        ),
    ),
    (
        "safety_bypass",
        re.compile(
            r"(?:忽略|绕过|关闭|禁用|disable|bypass|turn\s+off)\s*"
            r"(?:安全|security|safety|限制|规则|rules|filter)",
            re.I,
        ),
    ),
    (
        "delimiter_breakout",
        re.compile(r"</?\s*user_text\s*>|```\s*(?:system|assistant)|<\|(?:system|im_start)\|>", re.I),
    ),
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_prompt_injection(text: str) -> list[str]:
    """返回命中的注入模式名；仅做检测，不修改文本。"""
    if not text:
        return []
    return [name for name, pattern in INJECTION_PATTERNS if pattern.search(text)]


def sanitize_text(
    text: str,
    *,
    scene: str,
    user_id: int | None = None,
    request_id: str | None = None,
) -> tuple[str, list[str]]:
    """拒绝注入指令并继续诊断：命中片段替换为空格，返回清洗后文本与命中模式。"""
    if not text:
        return text, []
    hits: list[str] = []
    cleaned = text
    for name, pattern in INJECTION_PATTERNS:
        if pattern.search(cleaned):
            hits.append(name)
            cleaned = pattern.sub(" ", cleaned)
    if not hits:
        return text, []
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    logger.warning(
        "security_event=prompt_injection scene=%s patterns=%s text_sha256=%s user_id=%s request_id=%s",
        scene,
        ",".join(hits),
        _sha256(text),
        user_id,
        request_id,
    )
    return cleaned, hits


def load_sensitive_words(path: Path | str | None = None) -> list[str]:
    """从 config/sensitive_words.txt 加载词表（忽略空行与 # 注释）。"""
    target = Path(path) if path is not None else SENSITIVE_WORDS_PATH
    if not target.exists():
        return list(_DEFAULT_SENSITIVE_WORDS)
    words: list[str] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        if word not in words:
            words.append(word)
    return words or list(_DEFAULT_SENSITIVE_WORDS)


def mask_sensitive_words(
    text: str,
    words: list[str] | None = None,
    *,
    scene: str = "report",
) -> tuple[str, list[str]]:
    """命中敏感词替换为 ***，并记录脱敏日志（不记录原文）。"""
    vocabulary = words if words is not None else load_sensitive_words()
    hits = [word for word in vocabulary if word and word in text]
    if not hits:
        return text, []
    cleaned = text
    for word in hits:
        cleaned = cleaned.replace(word, "***")
    logger.warning(
        "security_event=sensitive_word_hit scene=%s count=%s words=%s text_sha256=%s",
        scene,
        len(hits),
        ",".join(hits),
        _sha256(text),
    )
    return cleaned, hits
