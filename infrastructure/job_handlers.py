"""Default durable-job handlers for RAG and integration processing."""
from __future__ import annotations

from infrastructure.job_queue import register_job_handler


async def _index_document(job: dict):
    from infrastructure.organization_rag import get_organization_rag
    payload = job["payload"]
    return await get_organization_rag().index_document(job["tenant_id"], payload["department"], payload["document_id"])


async def _process_webhook(job: dict):
    from infrastructure.integration_hub import get_integration_hub
    payload = job["payload"]
    return get_integration_hub().process_webhook_job(job["tenant_id"], payload)


async def _sync_source(job: dict):
    from infrastructure.source_sync import get_source_sync_service
    return await get_source_sync_service().run(job["tenant_id"], job["payload"])


def register_default_job_handlers() -> None:
    register_job_handler("organization.rag.index_document", _index_document)
    register_job_handler("integration.webhook", _process_webhook)
    register_job_handler("organization.source.sync", _sync_source)
