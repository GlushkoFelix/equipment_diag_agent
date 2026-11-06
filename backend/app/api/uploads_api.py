"""CSV 上传、映射预览与映射方案端点（ARCH §5.4.3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile

from app import mapping, security, uploads
from app.schemas.api import (
    MappingPreviewRequest,
    MappingPreviewResponse,
    MappingScheme,
    MappingSchemeCreate,
    MappingSchemesResponse,
    UploadPrecheck,
)

router = APIRouter(tags=["uploads"])


@router.post("/uploads", response_model=UploadPrecheck, status_code=201)
async def create_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(security.current_user),
):
    content = await file.read()
    return uploads.save_upload(
        request.app.state.db,
        request.app.state.settings,
        user["user_id"],
        file.filename or "upload.csv",
        content,
    )


@router.get("/uploads/{upload_id}", response_model=UploadPrecheck)
def get_upload(upload_id: str, request: Request, user: dict = Depends(security.current_user)):
    return uploads.get_upload(request.app.state.db, user["user_id"], upload_id)


@router.post("/uploads/{upload_id}/mapping/preview", response_model=MappingPreviewResponse)
def preview_mapping(
    upload_id: str,
    body: MappingPreviewRequest,
    request: Request,
    user: dict = Depends(security.current_user),
):
    return mapping.preview_mapping(
        request.app.state.db, user["user_id"], upload_id, body.model_dump()
    )


@router.get("/mapping-schemes", response_model=MappingSchemesResponse)
def list_mapping_schemes(
    request: Request,
    user: dict = Depends(security.current_user),
    header_signature: str | None = Query(default=None),
):
    return mapping.list_schemes(request.app.state.db, user["user_id"], header_signature)


@router.post("/mapping-schemes", response_model=MappingScheme, status_code=201)
def create_mapping_scheme(
    body: MappingSchemeCreate,
    request: Request,
    response: Response,
    user: dict = Depends(security.current_user),
):
    status_code, payload = mapping.create_scheme(
        request.app.state.db, user["user_id"], body.model_dump()
    )
    response.status_code = status_code
    return payload
