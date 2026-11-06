"""SSE 事件封套契约测试（ARCH §5.5.2 / §5.5.3）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.events import SseEvent, SseEventType


def test_snapshot_event_matches_schema():
    event = SseEvent.model_validate(
        {
            "seq": 0,
            "stream_kind": "diagnosis",
            "stream_id": "dx_01J8ABCDEF",
            "type": "snapshot",
            "revision": 1,
            "occurred_at": "2026-10-23T10:24:00Z",
            "payload": {"diagnosis_id": "dx_01J8ABCDEF", "status": "running"},
        }
    )
    assert event.type is SseEventType.snapshot
    assert event.data_line().startswith('{"seq":0')


def test_heartbeat_has_no_seq_and_no_id():
    event = SseEvent.model_validate(
        {
            "seq": None,
            "stream_kind": "diagnosis",
            "stream_id": "dx_01J8ABCDEF",
            "type": "heartbeat",
            "revision": 1,
            "occurred_at": "2026-10-23T10:24:18Z",
            "payload": {"server_time": "2026-10-23T10:24:18Z"},
        }
    )
    rendered = event.render()
    assert "id:" not in rendered
    assert "event: heartbeat" in rendered


def test_all_event_types_allowed():
    for type_name in (
        "snapshot",
        "step",
        "status",
        "interrupt",
        "report",
        "expired",
        "error",
        "heartbeat",
    ):
        SseEvent.model_validate(
            {
                "seq": 1,
                "stream_kind": "diagnosis",
                "stream_id": "dx_x",
                "type": type_name,
                "revision": 1,
                "occurred_at": "2026-10-23T10:24:00Z",
                "payload": {},
            }
        )


def test_unknown_event_type_rejected():
    with pytest.raises(ValidationError):
        SseEvent.model_validate(
            {
                "seq": 1,
                "stream_kind": "diagnosis",
                "stream_id": "dx_x",
                "type": "unknown",
                "revision": 1,
                "occurred_at": "2026-10-23T10:24:00Z",
                "payload": {},
            }
        )


def test_render_single_line_json():
    event = SseEvent.model_validate(
        {
            "seq": 42,
            "stream_kind": "diagnosis",
            "stream_id": "dx_x",
            "type": "step",
            "revision": 1,
            "occurred_at": "2026-10-23T10:24:03Z",
            "payload": {
                "node": "retrieve",
                "phase": "end",
                "rule_id": "RT-04",
                "summary": "命中 3 条\n第二行",
            },
        }
    )
    rendered = event.render()
    data_lines = [ln for ln in rendered.splitlines() if ln.startswith("data: ")]
    assert len(data_lines) == 1
    assert "\\n" in data_lines[0]
