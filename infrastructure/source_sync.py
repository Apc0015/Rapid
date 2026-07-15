"""Connector-neutral source sync with a working local sandbox adapter."""
from __future__ import annotations

from typing import Any

from infrastructure.organization_data_store import OrganizationDataError, get_organization_data_store
from infrastructure.job_queue import get_job_queue


class SourceSyncError(ValueError):
    pass


class SourceSyncService:
    async def run(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = str(payload.get("source_id") or "")
        store = get_organization_data_store()
        source = store.get_source(tenant_id, source_id)
        connector = source["connector_type"]
        if connector not in {"manual", "local_demo", "sandbox"}:
            raise SourceSyncError(f"Connector adapter '{connector}' requires customer configuration")
        if source["source_type"] == "structured":
            records = payload.get("records") or []
            if records:
                updated = store.add_structured_records(tenant_id, source_id, records)
                return {"source_id": source_id, "status": "completed", "records_synced": updated["record_count"]}
            return {"source_id": source_id, "status": "completed", "records_synced": 0}
        documents = payload.get("documents") or []
        created = []
        for document in documents:
            saved = store.add_document(tenant_id, source_id, str(document["name"]), str(document["content"]), "connector_sync")
            created.append(saved)
            get_job_queue().enqueue(
                tenant_id, "organization.rag.index_document",
                {"document_id": saved["document_id"], "department": source["department"]},
                idempotency_key=f"index:{saved['document_id']}",
            )
        return {"source_id": source_id, "status": "completed", "documents_synced": len(created), "documents": created}


def get_source_sync_service() -> SourceSyncService:
    return SourceSyncService()
