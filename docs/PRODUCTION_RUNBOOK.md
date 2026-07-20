# RAPID Production Runbook

## Required configuration

Set these through the deployment secret manager, not in source control:

- `JWT_SECRET_KEY`: at least 32 random bytes.
- `RAPID_ENCRYPTION_KEY`: a Fernet key used for encrypted OAuth tokens and local secret references.
- `ALLOWED_ORIGINS`: deployed frontend origins.
- `ALLOWED_HOSTS`: public application and API hostnames.
- One AI provider: an Ollama endpoint or an OpenRouter credential reference configured in the tenant admin portal.

Generate the encryption key with:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Deployment

```bash
docker compose up -d --build
```

Use Qdrant for a shared vector store when API and worker replicas run on different hosts:

```bash
USE_QDRANT=true docker compose --profile qdrant up -d --build
```

The `rapid` service handles HTTP requests. The `worker` service processes RAG indexing, connector sync, and signed webhook jobs. The dedicated `scheduler` service is the only supplied schedule dispatcher; scale it only after replacing it with a leader-elected or managed scheduler.

## Release checks

```bash
curl -fsS https://app.example.com/api/health/live
curl -fsS https://app.example.com/api/health/ready
curl -fsS https://app.example.com/api/metrics
pytest -q
python scripts/portal_e2e.py --base-url https://app.example.com
python scripts/load_smoke.py --base-url https://app.example.com/api --requests 500 --concurrency 50
```

## Backup and restore

Use the authenticated `/backup/run` endpoint or the admin backup page to create an application backup. Copy backups to customer-controlled object storage and test a restore in a non-production environment before each major release. Back up the primary database, organization/workspace databases, encrypted-secret database, job database, audit log, and FAISS data. Qdrant deployments should use Qdrant snapshots.

## Incident response

1. Check `/health/ready` and `/metrics`.
2. Inspect dead-letter jobs through `GET /jobs?status=dead_letter`.
3. Disable the affected tenant connection in the admin portal.
4. Rotate the referenced provider secret and webhook signing key.
5. Replay a dead-letter job only after the underlying provider or payload issue is fixed.
6. Preserve request IDs and audit records for the incident review.

## Scaling notes

- SQLite and FAISS are valid for the single-host product and evaluation environment.
- Use PostgreSQL, Qdrant, customer object storage, and a managed secret manager for multi-host production.
- The included SQLite job queue safely supports separate processes on one shared filesystem. Use a managed queue when workers span hosts or regions.
- Terminate TLS at the ingress or load balancer. The application emits HSTS in production.
