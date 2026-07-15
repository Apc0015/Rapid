"""Governed organization data source and retrieval API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from infrastructure.organization_data_store import OrganizationDataError, get_organization_data_store
from infrastructure.document_extractor import DocumentExtractionError, extract_document
from infrastructure.job_queue import get_job_queue
from infrastructure.organization_rag import get_organization_rag
from infrastructure.people_ops_store import DEPARTMENTS, PRIVILEGED_ROLES
from routers.deps import get_current_user

router = APIRouter(prefix="/organization/data", tags=["organization-data"])


def _tenant(current_user: dict) -> str:
    return str(current_user.get("tenant_id") or "default")


def _allowed_departments(current_user: dict) -> set[str]:
    if current_user.get("role") in {"admin", "ceo"}:
        return set(DEPARTMENTS)
    return set(current_user.get("depts") or []) & set(DEPARTMENTS)


def _require_department(current_user: dict, department: str) -> None:
    if department not in _allowed_departments(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this department")


def _require_operator(current_user: dict) -> None:
    if current_user.get("role") not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="Department operator role required")


def _raise(error: OrganizationDataError) -> None:
    status = 404 if "not found" in str(error).lower() or "outside" in str(error).lower() else 400
    raise HTTPException(status_code=status, detail=str(error))


class SourceRequest(BaseModel):
    department: str
    name: str = Field(min_length=1, max_length=160)
    source_type: Literal["structured", "unstructured"]
    connector_type: str = Field(default="manual", min_length=1, max_length=80)
    classification: Literal["internal", "confidential", "restricted"] = "internal"
    config: dict[str, Any] = Field(default_factory=dict)


class RecordsRequest(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1, max_length=500)


class DocumentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=2_000_000)


class SearchRequest(BaseModel):
    department: str
    query: str = Field(min_length=2, max_length=1000)
    source_id: Optional[str] = None
    limit: int = Field(default=8, ge=1, le=25)


class SourceSyncRequest(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    documents: list[dict[str, str]] = Field(default_factory=list, max_length=50)
    idempotency_key: str = Field(default="", max_length=255)


def _source_with_access(source_id: str, current_user: dict) -> dict:
    try:
        source = get_organization_data_store().get_source(_tenant(current_user), source_id)
    except OrganizationDataError as error:
        _raise(error)
    _require_department(current_user, source["department"])
    return source


@router.get("/sources")
async def list_sources(department: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if department:
        _require_department(current_user, department)
    sources = get_organization_data_store().list_sources(_tenant(current_user), department)
    allowed = _allowed_departments(current_user)
    return {"sources": [source for source in sources if source["department"] in allowed]}


@router.post("/sources", status_code=201)
async def register_source(body: SourceRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    _require_department(current_user, body.department)
    try:
        return {"source": get_organization_data_store().register_source(_tenant(current_user), body.department, body.name, body.source_type, body.connector_type, body.classification, current_user["sub"], body.config)}
    except OrganizationDataError as error:
        _raise(error)


@router.post("/sources/{source_id}/records")
async def ingest_records(source_id: str, body: RecordsRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    _source_with_access(source_id, current_user)
    try:
        return {"source": get_organization_data_store().add_structured_records(_tenant(current_user), source_id, body.records)}
    except OrganizationDataError as error:
        _raise(error)


@router.get("/sources/{source_id}/records")
async def list_records(source_id: str, limit: int = Query(50, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    _source_with_access(source_id, current_user)
    try:
        return {"records": get_organization_data_store().list_records(_tenant(current_user), source_id, limit)}
    except OrganizationDataError as error:
        _raise(error)


@router.post("/sources/{source_id}/documents", status_code=201)
async def ingest_document(source_id: str, body: DocumentRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    _source_with_access(source_id, current_user)
    try:
        document = get_organization_data_store().add_document(_tenant(current_user), source_id, body.name, body.content)
        source = get_organization_data_store().get_source(_tenant(current_user), source_id)
        job = get_job_queue().enqueue(
            _tenant(current_user), "organization.rag.index_document",
            {"document_id": document["document_id"], "department": source["department"]},
            idempotency_key=f"index:{document['document_id']}",
        )
        return {"document": document, "job": job}
    except OrganizationDataError as error:
        _raise(error)


@router.post("/sources/{source_id}/files", status_code=202)
async def ingest_file(source_id: str, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    source = _source_with_access(source_id, current_user)
    if source["source_type"] != "unstructured":
        raise HTTPException(status_code=400, detail="Only unstructured sources accept files")
    content = await file.read(20_000_001)
    if len(content) > 20_000_000:
        raise HTTPException(status_code=413, detail="Knowledge files must be 20MB or smaller")
    try:
        extracted = extract_document(file.filename or "document.txt", content)
        document = get_organization_data_store().add_document(
            _tenant(current_user), source_id, file.filename or "Uploaded document", extracted.text, extracted.method,
        )
        job = get_job_queue().enqueue(
            _tenant(current_user), "organization.rag.index_document",
            {"document_id": document["document_id"], "department": source["department"]},
            idempotency_key=f"index:{document['document_id']}",
        )
        return {"document": document, "extraction": {"method": extracted.method, "pages": extracted.pages}, "job": job}
    except (DocumentExtractionError, OrganizationDataError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/sources/{source_id}/sync", status_code=202)
async def sync_source(source_id: str, body: SourceSyncRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    _source_with_access(source_id, current_user)
    key = body.idempotency_key or f"manual-sync:{source_id}:{current_user['sub']}"
    job = get_job_queue().enqueue(
        _tenant(current_user), "organization.source.sync",
        {"source_id": source_id, "records": body.records, "documents": body.documents},
        idempotency_key=key,
    )
    return {"job": job}


@router.post("/documents/{document_id}/index", status_code=202)
async def index_document(document_id: str, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    try:
        document = get_organization_data_store().get_document(_tenant(current_user), document_id)
        _require_department(current_user, document["department"])
        job = get_job_queue().enqueue(
            _tenant(current_user), "organization.rag.index_document",
            {"document_id": document_id, "department": document["department"]},
            idempotency_key=f"reindex:{document_id}:{document['content_hash']}",
        )
        return {"job": job}
    except OrganizationDataError as error:
        _raise(error)


@router.post("/search")
async def search_documents(body: SearchRequest, current_user: dict = Depends(get_current_user)):
    _require_department(current_user, body.department)
    try:
        return await get_organization_rag().search(_tenant(current_user), body.department, body.query, body.source_id, body.limit)
    except OrganizationDataError as error:
        _raise(error)
