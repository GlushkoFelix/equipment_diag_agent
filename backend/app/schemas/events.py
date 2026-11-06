"""SSE 事件封套（ARCH §5.5.2）。"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SseEventType(str, Enum):
    snapshot = "snapshot"
    step = "step"
    status = "status"
    interrupt = "interrupt"
    report = "report"
    expired = "expired"
    error = "error"
    heartbeat = "heartbeat"
    # 批量流（ARCH §5.5.6）
    batch_snapshot = "batch_snapshot"
    batch_progress = "batch_progress"
    row_status = "row_status"
    batch_status = "batch_status"


class SseEvent(BaseModel):
    seq: int | None
    stream_kind: Literal["diagnosis", "batch"]
    stream_id: str
    type: SseEventType
    revision: int | None
    occurred_at: str
    payload: dict[str, Any] = Field(default_factory=dict)

    def data_line(self) -> str:
        body = {
            "seq": self.seq,
            "stream_kind": self.stream_kind,
            "stream_id": self.stream_id,
            "type": self.type.value,
            "revision": self.revision,
            "occurred_at": self.occurred_at,
            "payload": self.payload,
        }
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))

    def render(self) -> str:
        lines: list[str] = []
        if self.seq is not None:
            lines.append(f"id: {self.seq}")
        lines.append(f"event: {self.type.value}")
        lines.append(f"data: {self.data_line()}")
        return "\n".join(lines) + "\n\n"
