# Startup 9/10 Release Bar

RAPID launches first for startups as a weekly operating-review workspace. A
score is earned only with working product behavior and recorded validation
evidence. It is not a marketing claim.

## Product And UX

- A founder can create a tenant, choose an AI data boundary, and enter a useful
  sample startup workspace without connecting production systems.
- The first customer outcome is concrete: identify the current delivery,
  customer, pipeline, decision, and owner risks for an accountable weekly review.
- The common portal covers operating context, decisions, actions, product work,
  customers, documents, reports, and chat on desktop and mobile.
- RAPID Chat answers orientation questions from scoped workspace data, shows
  confidence and evidence when available, and never presents an internal error
  as an answer.
- Accessibility checks pass with no serious or critical WCAG violations across
  onboarding, workspace, administration, and mobile navigation.

## AI And RAG Trust

- Every source, document, chunk, and answer is tenant and department scoped.
- Optional source allow-lists restrict retrieval to approved roles or named users;
  the same permission scope applies to the data API and RAPID Chat evidence.
- Ingestion applies PII detection/redaction, source classification, durable
  indexing, and permission-filtered retrieval.
- Private and on-prem tenants block cloud model providers and live cloud
  connections. Sandbox data remains available for evaluation.
- Retrieval quality is measured on a representative customer-approved test set
  before a production deployment is approved.

## Integrations And Automation

- A startup administrator can configure sandbox connections without credentials
  and live connections with only secret-manager references.
- OAuth uses state, PKCE, short-lived state records, and tenant-scoped token
  references. Webhooks are signed, replay-protected, idempotent, and queued.
- Each supported provider has a documented permission set, sync boundary,
  failure mode, retry policy, and disconnect path.
- An integration-triggered action enters a governed playbook and stops for human
  approval when the action is consequential.

## Security And Operations

- Tenant isolation, authorization, request limits, content-security policy,
  secret references, audit trails, queue health, dead-letter handling, and safe
  backup restore path validation are covered by automated tests.
- Production deployment has managed secrets, encrypted backups, monitored
  alerts, restore-drill evidence, dependency scanning, and a tested incident
  response runbook.
- An independent penetration test and customer-required legal/compliance review
  are completed before any regulated or enterprise security claim.

## Release Evidence Required

1. Full unit, integration, security, browser, mobile, accessibility, and load
   suites pass in CI on the release candidate.
2. Three to five startup design partners complete onboarding using their own
   approved data configuration.
3. Each pilot demonstrates a measurable outcome: time saved, decision cycle
   reduced, risk caught, or operating task completed with an accountable owner.
4. No unresolved critical or high-severity authorization, data boundary, or
   cross-tenant findings remain.
