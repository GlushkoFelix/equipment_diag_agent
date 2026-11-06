"""评测端点（ARCH §5.4.8，只读）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app import evaluation, security
from app.schemas.api import (
    EvalBatchPage,
    EvalDetail,
    EvalLatest,
    EvalSamplesPage,
)

router = APIRouter(tags=["evaluations"])


@router.get("/evaluations", response_model=EvalBatchPage)
def list_evaluations(
    request: Request,
    user: dict = Depends(security.current_user),
    page: int = 1,
    page_size: int = 20,
):
    return evaluation.list_batches(request.app.state.db, page, page_size)


@router.get("/evaluations/latest", response_model=EvalLatest)
def latest_evaluation(request: Request, user: dict = Depends(security.current_user)):
    return evaluation.latest(request.app.state.db)


@router.get("/evaluations/{eval_batch_id}", response_model=EvalDetail)
def evaluation_detail(
    eval_batch_id: str, request: Request, user: dict = Depends(security.current_user)
):
    return evaluation.detail(request.app.state.db, eval_batch_id, request.app.state.knowledge)


@router.get("/evaluations/{eval_batch_id}/samples", response_model=EvalSamplesPage)
def evaluation_samples(
    eval_batch_id: str,
    request: Request,
    user: dict = Depends(security.current_user),
    only_bad_cases: bool = True,
    split: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    return evaluation.samples(
        request.app.state.db,
        eval_batch_id,
        only_bad_cases=only_bad_cases,
        split=split,
        page=page,
        page_size=page_size,
    )
