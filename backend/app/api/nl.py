"""自然语言抽取端点（不创建诊断）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import chat_extract, security
from app.schemas.api import NlExtractRequest, NlExtractResponse

router = APIRouter(tags=["nl"])


@router.post("/nl/extract", response_model=NlExtractResponse)
def nl_extract(body: NlExtractRequest, user: dict = Depends(security.current_user)):
    result = chat_extract.extract(body.text, body.device_id_hint)
    return {
        "text": body.text,
        **result,
    }
