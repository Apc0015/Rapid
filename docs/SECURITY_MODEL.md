# RAPID Security Model

## Boundaries

- Every workspace, job, source, document, connection, meeting, and notification is scoped by `tenant_id`.
- Department retrieval requires an explicit department grant. Executive and administrator roles can access all departments in their tenant.
- External credentials are represented by `env://` or `vault://` references. API responses expose only whether a credential is configured.
- OAuth state is short-lived, PKCE-protected, and single-use. Provider tokens are encrypted at rest.
- Webhooks use HMAC-SHA256 over `timestamp.body`, reject messages outside a five-minute replay window, and enqueue events idempotently.

## Knowledge governance

- Unstructured uploads are extracted from supported file formats before ingestion.
- Email addresses, US phone numbers, SSNs, and valid payment-card numbers are detected and redacted before chunks are stored or indexed.
- PII upgrades an `internal` document to `confidential` classification.
- Vector indexes are separated by tenant and department. Search returns source and document citations plus the active permission scope.
- Production does not silently use development token-hash embeddings. An unavailable configured embedding provider fails the indexing job and enters retry/dead-letter handling.

## HTTP controls

- JWT bearer authentication protects product and admin APIs.
- CORS and trusted hosts are deployment-configured.
- Request size limits, rate limits, request IDs, response timing, CSP, anti-framing, MIME sniffing protection, referrer policy, and HSTS are enabled.
- Liveness, readiness, and Prometheus-format metrics are available for operations.

## Customer deployment responsibilities

- Configure TLS, DNS, outbound network policy, and provider allowlists.
- Supply and rotate SSO, database, AI, OAuth, webhook, storage, and email credentials.
- Select retention periods and backup destinations that satisfy applicable legal and contractual requirements.
- Complete penetration testing, privacy review, disaster-recovery testing, and compliance evidence collection for the target market before public production launch.
