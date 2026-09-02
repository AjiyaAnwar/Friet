# FreightCore™ — Team Member 1: Backend Architect
**Role: Backend Architect & Core Platform Engineer**
*Al-Rahim Group / Inter-Fret Consolidators (Pvt.) Ltd. · ARG-SRS-FFMS-2026-001*

---

> [!IMPORTANT]
> You own the **platform foundation** that every other team member builds on. Nothing works without your layer. Your deliverables must be ready before anyone else can begin meaningful work. You are also the **technical authority** — all PRs touching core infrastructure, DB schema changes, API conventions, or security pass through your review.

---

## Your Ownership Map

| Domain | Your Responsibility |
|---|---|
| Cloud Infrastructure | Design, provision, maintain |
| Database Architecture | Schema design, migrations, performance |
| Authentication & RBAC | Auth service, permission matrix, row-level security |
| API Gateway & Standards | Versioning, error formats, pagination, rate limiting |
| Audit Trail | Immutable log, compliance storage |
| Event Bus / Messaging | Broker setup, schema registry, dead-letter handling |
| Security Architecture | OWASP ASVS 4.0, encryption, secrets management |
| Multi-Tenancy | Tenant isolation, schema separation, cross-company |
| State Machine Engine | Generic workflow engine used by all operation modules |
| Configurable Rules Engine | Business rules framework used across all domains |
| Search Infrastructure | Elasticsearch cluster, indexing strategy |
| Performance & Scalability | Load testing, autoscaling, caching strategy |
| SLA Engine | SLA clock framework shared by all teams |

---

## Phase 1 — Foundation & Core Architecture
**Your Duration:** 6–8 weeks | **Priority: CRITICAL — blocks all other team members**

### 1.1 Cloud Infrastructure (Week 1–2)

**Tasks:**
- [ ] Provision AWS accounts: `dev`, `staging`, `production` with proper IAM role separation
- [ ] Write Terraform modules for all infrastructure (no manual console clicks):
  - VPC with public/private subnets across 3 AZs
  - EKS cluster (Kubernetes) with node groups: `api`, `workers`, `monitoring`
  - RDS PostgreSQL (multi-AZ, encrypted, automated backups)
  - ElastiCache Redis cluster (for sessions and rate caching)
  - S3 buckets: `documents`, `exports`, `backups`, `audit-archive`
  - CloudFront CDN for frontend static assets
  - AWS SQS/SNS or self-hosted RabbitMQ on EKS
  - AWS Secrets Manager for all credentials
- [ ] GitHub Actions CI/CD pipeline:
  - On PR → lint, unit tests, build Docker image
  - On merge to `main` → deploy to `dev`
  - Manual gate → promote to `staging` → `production`
- [ ] Centralized observability stack:
  - Prometheus + Grafana for metrics
  - ELK Stack (or CloudWatch Logs Insights) for structured logs
  - Jaeger or AWS X-Ray for distributed tracing
  - PagerDuty / OpsGenie alerts for P1 incidents
- [ ] SSL/TLS certificates via AWS ACM; enforce TLS 1.3 minimum
- [ ] Secrets rotation policy: all DB passwords, API keys rotated every 90 days

**Acceptance Criteria:**
- All 3 environments are live and independently deployable via CI/CD
- A health-check endpoint returns `200 OK` from `staging` and `production`
- Terraform state is stored in S3 with DynamoDB locking
- Zero credentials in source code (all in Secrets Manager)

---

### 1.2 Database Architecture (Week 1–3)

**Tasks:**
- [ ] Design the master database schema (ERD covering all entities from SRS §34):
  - Tenant / Company / Branch hierarchy tables
  - User, Role, Permission, Role-Permission mapping tables
  - Audit log table (append-only partition)
  - Base entity conventions: `id UUID`, `created_at`, `updated_at`, `created_by`, `tenant_id`
- [ ] Implement database migration framework (Alembic for Python / Flyway / Liquibase)
  - All schema changes via versioned migration files — no manual DDL on production
  - Migration applied automatically on deployment
- [ ] Configure PostgreSQL for production:
  - Synchronous replication to hot standby (`synchronous_commit = on`)
  - Async replication to 2 read replicas for reporting queries
  - `SERIALIZABLE` isolation for financial transactions; `READ COMMITTED` for operational reads
  - WAL archiving to S3 (continuous); RPO < 1 minute
  - Point-in-time recovery tested and documented
- [ ] Implement time-based partitioning:
  - `tracking_events`: monthly partitions by `event_time`
  - `audit_log`: monthly partitions by `created_at`
  - `eta_history`: monthly partitions by `recorded_at`
  - `financial_entries`: yearly partitions by `entry_date`
- [ ] Indexing strategy (document and implement):
  - Composite: `(tenant_id, status)` on all major entities
  - Composite: `(shipment_id, event_type, timestamp)` on tracking events
  - Composite: `(carrier_id, origin_id, destination_id, effective_date)` on rates
  - `GIN` index for full-text search columns
- [ ] Encryption:
  - AES-256 at rest (AWS RDS encryption)
  - Column-level encryption for PII fields: `email`, `phone`, `tax_id`, `passport_number`
  - Column-level encryption for financial fields: `amount`, `credit_limit`
  - Encryption key rotation policy documented
- [ ] Data retention policy implementation:
  - Active data: current + 2 years in hot storage
  - Archive: 7 years in S3 Glacier (regulatory compliance)
  - Audit: 10 years (write-once S3 with Object Lock)

**Acceptance Criteria:**
- ERD reviewed and signed off by all team members
- Migration from empty DB to full schema runs in < 60 seconds
- Failover to hot standby tested: RTO < 1 hour, RPO < 1 minute
- All PII columns confirmed encrypted at column level

---

### 1.3 Authentication & Authorization Service (Week 2–4)

**Tasks:**
- [ ] Implement Authentication Service (separate microservice or module):
  - OAuth 2.0 Authorization Server + OIDC discovery endpoint
  - Local password auth (bcrypt, min 12 rounds)
  - JWT access tokens (15-minute expiry) + refresh tokens (7-day expiry, rotating)
  - Token blacklist for forced logout / account suspension
  - MFA support: TOTP (Google Authenticator compatible)
  - Account lockout after 5 failed attempts; configurable
- [ ] Multi-tenant architecture:
  - Every request must carry `tenant_id` (from JWT claims)
  - Schema-separated per company: `company_{id}_` prefix or separate schema per tenant
  - Tenant provisioning API: create company → auto-create schema + seed data
  - Cross-tenant data access strictly prohibited at DB level (Row Level Security policies)
- [ ] RBAC Permission Matrix — implement all roles from SRS §25:
  - 15 roles: `SUPER_ADMIN`, `BRANCH_MANAGER`, `SALES`, `PRICING`, `CUSTOMER_SERVICE`, `OPS_SEA`, `OPS_AIR`, `DOCUMENTATION`, `COMPLIANCE_DGR`, `CUSTOMS`, `FINANCE_AR`, `FINANCE_AP`, `FINANCE_CONTROLLER`, `MANAGEMENT`, `CUSTOMER_PORTAL`, `AGENT_PORTAL`
  - Permission model: `resource:action` (e.g., `shipment:read`, `quotation:approve`, `rate:create`)
  - Role-permission mapping stored in DB (not hardcoded) — configurable by `SUPER_ADMIN`
  - Branch-level permissions: a user may have different roles in different branches
- [ ] PostgreSQL Row Level Security (RLS):
  - Every table has RLS policy: `WHERE tenant_id = current_setting('app.tenant_id')`
  - Customer portal users: `WHERE customer_id = current_setting('app.customer_id')`
  - Enforced at DB level — even raw SQL connections are isolated
- [ ] API middleware:
  - JWT validation middleware (every protected endpoint)
  - Permission check middleware (resource + action per endpoint)
  - Audit log middleware (every write operation)
  - Tenant injection middleware (set `app.tenant_id` on DB connection)

**Acceptance Criteria:**
- Login/logout/refresh token flow works end-to-end
- User with `SALES` role cannot access finance endpoints (returns 403)
- Customer portal user cannot see another customer's data (row-level test)
- Tenant A data is completely invisible to Tenant B users

---

### 1.4 API Gateway & Standards (Week 3–4)

**Tasks:**
- [ ] Define and enforce API conventions (written as a developer standards doc):
  - Base URL: `https://api.freightcore.io/api/v1/`
  - URL naming: plural nouns, kebab-case (`/shipments`, `/quote-requests`, `/carrier-rates`)
  - HTTP methods: GET (read), POST (create), PUT (full update), PATCH (partial), DELETE (soft delete)
  - All responses: `{ data: ..., meta: { page, total, ... }, errors: [] }`
  - Error format: RFC 7807 Problem Details `{ type, title, status, detail, instance }`
  - Pagination: cursor-based with `Link: <next_url>; rel="next"` header
  - Sorting: `?sort=created_at:desc`
  - Filtering: `?status=active&customer_id=123`
  - Idempotency: all POST operations accept `Idempotency-Key` header (prevent duplicates on retry)
  - Versioning: URL-based `/v1/`, `/v2/` — backward-compatible changes only within version
- [ ] Rate limiting:
  - Per-user: 1000 req/min for internal users; 100 req/min for portal users
  - Per-IP for unauthenticated endpoints: 20 req/min (login, register)
  - Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
  - Exceeded → HTTP 429 with `Retry-After` header
- [ ] OpenAPI 3.0 specification:
  - Auto-generated from code annotations (FastAPI auto-generates; NestJS Swagger)
  - Published at `/api/v1/docs` (Swagger UI) and `/api/v1/openapi.json`
  - All endpoints documented: parameters, request body, response schemas, error codes
- [ ] API key management for external integrations (carrier adapters, customs APIs):
  - Key generation, rotation, scoping (read-only vs. full access)
  - API key usage logged in audit trail

**Acceptance Criteria:**
- All API endpoints follow the standards (enforced by linter/test)
- OpenAPI spec is valid and complete (all endpoints documented)
- Rate limiting verified: 1001st request returns 429

---

### 1.5 Audit Trail (Week 4)

**Tasks:**
- [ ] Implement generic audit middleware:
  - Intercepts all `POST`, `PUT`, `PATCH`, `DELETE` operations
  - Records: `entity_type`, `entity_id`, `action`, `previous_value` (JSON), `new_value` (JSON), `user_id`, `user_role`, `tenant_id`, `ip_address`, `timestamp_utc`, `user_agent`
  - Writes to `audit_log` table (append-only partition) — synchronous write before API response
- [ ] Immutability enforcement:
  - No `UPDATE` or `DELETE` on `audit_log` — enforced via PostgreSQL trigger that raises exception
  - Write-once S3 bucket for audit archive exports (Object Lock: COMPLIANCE mode, 10-year retention)
  - Audit records also published to event bus for real-time compliance monitoring
- [ ] Audit search API: `GET /api/v1/audit?entity_type=shipment&entity_id=xxx&from=&to=`
  - Only accessible by `SUPER_ADMIN`, `FINANCE_CONTROLLER`, `BRANCH_MANAGER`
  - Results paginated, exportable to CSV

**Acceptance Criteria:**
- Every write operation creates an audit record (verified by test suite)
- No code path exists to modify or delete audit records
- Audit records survive DB restore (stored in S3 as well)

---

### 1.6 Event Bus & Domain Events (Week 4–5)

**Tasks:**
- [ ] Set up message broker (RabbitMQ on Kubernetes or AWS SQS/SNS):
  - Exchanges/Topics per domain: `commercial`, `sea-ops`, `air-ops`, `finance`, `compliance`, `tracking`, `notifications`
  - Dead-letter queues for all consumers with configurable retry policy (3 retries, exponential backoff)
  - Message persistence: all messages durable, surviving broker restart
- [ ] AsyncAPI specification for all domain events:
  - Document every event: `shipment.created`, `quotation.accepted`, `booking.confirmed`, `shipment.departed`, `invoice.generated`, `exception.raised`, etc.
  - Event schema: `{ event_id, event_type, timestamp_utc, tenant_id, payload, correlation_id, source_service }`
- [ ] Event publisher base class (used by all team members):
  - Transactional outbox pattern: event written to `outbox` table in same DB transaction as the operation → relay process publishes to broker
  - Guarantees at-least-once delivery; consumers must be idempotent
- [ ] Event sourcing for critical entities:
  - `ShipmentStateChanged` event stream for full shipment lifecycle audit
  - `FinancialEntryCreated` event stream for financial audit trail
- [ ] Dead-letter monitoring: alert when DLQ depth > 0; automatic retry-replay tool

**Acceptance Criteria:**
- 10,000 events/minute throughput tested without message loss
- Consumer failure → message goes to DLQ, not lost
- Transactional outbox: if DB transaction rolls back, no event is published

---

### 1.7 Generic State Machine Engine (Week 5–6)

*This engine is used by Operations Team for sea/air workflows, and Commercial Team for RFQ/quotation lifecycles.*

**Tasks:**
- [ ] Design and implement a generic, DB-driven state machine:
  - State machine defined in DB tables (not hardcoded): `state_machine`, `state`, `transition`, `guard`, `action`
  - Transition rules: `from_state`, `to_state`, `guard_conditions` (JSON rules), `required_fields` (JSON list), `automated_actions` (event list), `notifications` (list)
  - Guard evaluation: pluggable guard functions registered by name (e.g., `credit_check_passed`, `documents_complete`)
  - Transition API: `POST /api/v1/shipments/{id}/transition` `{ to_state, actor_id, notes }`
  - On transition: validate guards → check required fields → execute automated actions → publish event → record in audit
- [ ] State machine definitions to configure (configured, not coded):
  - RFQ lifecycle (10 states)
  - Booking lifecycle (9 states)
  - Shipment Common (15 states)
  - Sea FCL specific extensions
  - Air Direct specific extensions
  - Document lifecycle (7 states)
  - Financial entry lifecycle (8 states)
  - Claims lifecycle (11 states)

**Acceptance Criteria:**
- Unauthorized state transition returns 422 with clear error
- Transition with missing required fields is blocked with field-level errors
- All state machine definitions are in DB (zero business logic hardcoded)

---

### 1.8 Configurable Rules Engine (Week 5–6)

**Tasks:**
- [ ] Implement declarative rules engine:
  - Rule definition: `IF [conditions] THEN [actions]` stored in DB as JSON
  - Conditions: field comparisons, aggregations, lookups, boolean combinators (AND/OR/NOT)
  - Actions: raise exception, block transition, notify user, create task, apply value
  - Rule domains: `margin_rules`, `credit_rules`, `dgr_rules`, `sla_rules`, `escalation_rules`, `notification_triggers`
  - Rule versioning and audit trail
  - Rule evaluation engine: fast in-process evaluation (< 5ms per evaluation)
  - Admin UI (built by Frontend team): rule definition interface without code changes

**Acceptance Criteria:**
- New margin rule added via admin UI takes effect immediately without deployment
- Rule evaluation adds < 5ms to API response time (p99)

---

## Phase 2 — Your Contributions
*Master data schema design + search infrastructure*

- [ ] Review and approve all master data schema designs created by Commercial Team
- [ ] Set up **Elasticsearch cluster**: indices, mappings, and indexing pipeline for global search
  - Indices: `shipments`, `customers`, `vendors`, `carriers`, `rates`, `invoices`, `documents`
  - Sync strategy: DB → event bus → Elasticsearch consumer (near-real-time)
  - Search API: `GET /api/v1/search?q=MOCK123` → results < 500ms
  - Result filtering by tenant + user permissions enforced at Elasticsearch query level
- [ ] Build rate versioning infrastructure (immutable rate version records)
- [ ] Implement SLA clock engine (used by all operation modules):
  - SLA definition table per stage/mode/service type
  - SLA clock: start on state entry, pause on configurable events, stop on exit
  - Breach detection cron job: runs every 5 minutes, publishes `sla.breached` events
- [ ] Review and approve Rules Engine configurations from all teams

---

## Phase 3–4 — Your Contributions
*Architecture governance + cross-cutting concerns*

- [ ] Review all new API endpoints from Commercial and Operations teams (PR reviewer)
- [ ] Implement **financial transaction isolation**: ensure all financial writes use `SERIALIZABLE` isolation
- [ ] Implement **distributed locking** for concurrent booking scenarios (Redis-based lock on `customer_id + booking_window`)
- [ ] Implement **idempotency store**: deduplication layer for all POST operations (Redis with 24-hour TTL)
- [ ] Performance baselines: establish load test suite (k6 or Locust); run after each phase completion
  - Target: p95 < 200ms for all operational API calls
- [ ] Database query performance review: explain-analyze all slow queries (> 100ms); add indexes as needed

---

## Phase 5 — Your Contributions
*Financial integrity architecture*

- [ ] Implement **financial ledger immutability**: financial entries are never updated — only reversed with counter-entries
- [ ] Implement **double-entry accounting checks**: debit/credit balance validation at transaction boundary
- [ ] Build **reconciliation engine** infrastructure: compare `revenue_lines` vs `invoice_lines` vs `payment_lines`
- [ ] Data archival pipeline: move shipments older than 2 years to archive schema; maintain accessibility for audit queries

---

## Phase 7 — Your Contributions
*Analytics data pipeline architecture*

- [ ] Design **data warehouse schema** (star schema on PostgreSQL read replica or separate DWH):
  - Fact tables: `fact_shipments`, `fact_financial_entries`, `fact_tracking_events`
  - Dimension tables: `dim_customers`, `dim_carriers`, `dim_routes`, `dim_time`
- [ ] ETL pipeline: operational DB → data warehouse (nightly full refresh + hourly incremental)
- [ ] Query optimization for BI dashboards: materialized views for common aggregations
- [ ] Implement **database connection pooling** (PgBouncer) for scale

---

## Phase 8 — Your Contributions
*Multi-tenancy expansion + scale hardening*

- [ ] Provision second tenant (IFCL Saudi Arabia) with complete schema isolation
- [ ] Implement **intercompany transaction framework**: cross-tenant accounting entries with automated elimination
- [ ] Load testing at production scale: 500 concurrent users, 10,000 shipments/day — fix all bottlenecks
- [ ] Kubernetes HPA (Horizontal Pod Autoscaler) rules for all services
- [ ] Database read replica routing: all SELECT queries from reporting → read replica; writes → primary
- [ ] GDPR/PDPA compliance review: data export (right to access), deletion (right to erasure) for PII

---

## Your Ongoing Responsibilities (All Phases)

- **PR Reviews:** All PRs touching DB schema, API conventions, security, or shared libraries require your approval
- **Architecture Decision Records (ADRs):** Document every major architectural decision in `/docs/adr/`
- **Dependency updates:** Monthly review of all third-party library versions; security patches applied within 72 hours of CVE disclosure
- **Penetration testing:** Coordinate external pentest before Phase 4 go-live and before Phase 8 launch
- **On-call:** Primary on-call for all infrastructure and database incidents

---

## Tech Stack You Own

| Tool | Purpose |
|---|---|
| **PostgreSQL 16** | Primary database |
| **Redis 7** | Session store, rate limiting, idempotency, distributed locks |
| **Elasticsearch 8** | Full-text search, audit search |
| **RabbitMQ / AWS SQS** | Event bus, domain events |
| **Kubernetes (EKS)** | Container orchestration |
| **Terraform** | Infrastructure as Code |
| **GitHub Actions** | CI/CD pipeline |
| **Prometheus + Grafana** | Metrics and dashboards |
| **AWS Secrets Manager** | Credentials management |
| **AWS S3 + Object Lock** | Audit archive, document storage |
| **PgBouncer** | Database connection pooling |
| **k6 / Locust** | Load testing |

---

*Document: FC-TEAM-001 · Backend Architect · FreightCore™*
