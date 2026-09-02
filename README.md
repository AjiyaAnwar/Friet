# FreightCore Backend

Enterprise sea and air freight forwarding platform — shared backend foundation (Team Member 1).

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- `cp .env.example .env` and adjust secrets for non-development environments

## Quick start

```bash
cp .env.example .env
docker compose --profile dev up --build -d
docker compose exec api-dev alembic upgrade head
docker compose exec api-dev python -m app.db.seed
docker compose exec api-dev pytest
```

API: http://localhost:8000/api/v1/docs

Default seed admin: `admin@freightcore.local` / `ChangeMe123!` with header `X-Tenant-Code: default`

## Commands

| Task | Command |
|------|---------|
| Migrations | `docker compose exec api-dev alembic upgrade head` |
| New migration | `docker compose exec api-dev alembic revision --autogenerate -m "description"` |
| Tests | `docker compose exec api-dev pytest` |
| Lint | `ruff check app tests` |
| Format | `ruff format app tests` |

## Architecture

Modular monolith: API routes → services → repositories → SQLAlchemy/PostgreSQL.

Cross-cutting: JWT auth + RBAC, tenant isolation (`tenant_id` + RLS-ready session vars), append-only audit, DB-driven workflow engine, versioned rules engine, transactional outbox, Redis idempotency/rate limits, RabbitMQ/Celery workers, Elasticsearch search.

## Database ownership boundary

The SQLAlchemy models, Docker PostgreSQL instance, and existing `initial_schema` migration are
**disposable development/test infrastructure only**. They are not the production source of truth.
The owner-managed PostgreSQL schema will be connected later. Do not generate or modify business
migrations, run these migrations against the owner database, or use `Base.metadata.create_all()`
outside explicitly disposable tests. Services must depend on repositories so production mappings
can be replaced without changing API or domain logic.

RLS connection-context support is prepared, but policies are **awaiting production-schema mapping**
and are not production-verified. The same limitation applies to database-level audit immutability
and transactional outbox guarantees.

### Production database mapping checklist

Before connecting production, map and integration-test these repository contracts:

- Identity/auth: tenants, users, branches, roles, permissions, assignments, customer-portal links,
  refresh-token hashes/revocation/rotation; unique tenant email and token-hash constraints.
- Domain repositories: every read and mutation needs tenant ID, plus customer ID for portal users;
  tenant/customer foreign keys and composite tenant indexes are required.
- Audit: entity/action, before/after JSON, actor/role/tenant/branch, request/correlation metadata,
  network metadata and UTC time; append-only permissions/triggers and time-based partitioning.
- Workflow/rules: versioned definitions, transitions, instances/history, rule versions/evaluations,
  active-version uniqueness, effective-date and tenant/domain/priority indexes.
- Events/SLA: outbox status/attempt/next-at/error fields, event-deduplication keys, SLA definitions
  and clocks; claim/poll indexes and unique idempotency constraints.
- Security: RLS policies for all tenant/customer data, transaction-local connection context with
  reset-on-return, encrypted sensitive columns, and least-privilege application/worker roles.
- Transactions: atomic business+audit+outbox writes; `READ COMMITTED` for ordinary work and row
  locks or optimistic version checks for transitions/claims. Confirm any stricter owner policy.
- Operations: finalize foreign keys, covering indexes, retention/partition policies, trigger
  ownership, backup behavior, and migration procedure from the supplied schema-only export.

No production SQL or Alembic migration should be generated until the exact owner schema and field
mapping are supplied.

## SRS ambiguities

- Production PostgreSQL replication, PITR, and WAL archiving are documented as on-premises targets; local Docker uses single-node PostgreSQL.
- OAuth 2.0/OIDC authorization server is deferred; local JWT login with TOTP MFA is implemented.
- Cloud infrastructure (AWS/EKS/Terraform) is excluded per assignment; Docker Compose provides dev/staging/prod profiles.

## Backend architect review areas

Changes requiring review before merge: Alembic migrations, auth/RBAC, tenant isolation, audit immutability, outbox/event schemas, shared workflow/rules engines, API conventions.

## Troubleshooting

- **API exits before Postgres ready**: Compose healthchecks gate `api-dev`; rerun `docker compose up`.
- **Migration failures**: ensure empty DB or run `alembic downgrade base` in disposable environments only.
- **Redis/ES optional locally**: readiness fails if Redis is down; start full stack with `docker compose --profile dev up`.
