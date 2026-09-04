# FreightCore™ — Team Member 3: Backend Developer (Operations & Finance)
**Role: Backend Developer — Shipment Operations, Finance & Compliance**
*Al-Rahim Group / Inter-Fret Consolidators (Pvt.) Ltd. · ARG-SRS-FFMS-2026-001*

---

> [!IMPORTANT]
> You own the **operational heart** of FreightCore™ — every shipment that moves through the company runs through your code. You also own the **financial integrity layer** — every rupee of revenue, every cost, every invoice is your responsibility. Errors here have direct operational and financial consequences.

---

## Your Ownership Map

| Domain | Your Responsibility |
|---|---|
| Sea Freight FCL Workflow Engine | 20-state FCL state machine, BL management, D&D, VGM |
| Sea Freight LCL Workflow | Consolidation, deconsolidation, House BL/Master BL hierarchy |
| Air Freight Direct Workflow Engine | 17-state air state machine, AWB management |
| Air Freight Consolidation | HAWB/MAWB hierarchy, consolidation planning, cost allocation |
| Document Management System | Repository, version control, checklist, approval workflow |
| Shipment Tracking & Event Model | ~60 event types, manual entry, timeline |
| ETA/ETD Multi-Version Tracking | Immutable ETA history, deviation alerts |
| Exception Management | Exception taxonomy, escalation, resolution |
| Shipment Financial Profile | Revenue ledger, cost ledger, real-time P&L |
| Customer Invoicing | Invoice generation, multi-currency, tax, PDF, AR |
| Vendor Bill Processing | Three-way matching, variance detection, AP |
| Accounts Receivable | Aging, dunning, payment allocation |
| Accounts Payable | Vendor aging, payment scheduling, batch |
| DGR Compliance Engine | Configurable rules, validation, documentation |
| Customs Module | Declaration data, jurisdictional rules, clearance tracking |
| Claims Management | Damage/loss claims, investigation, settlement |
| Automated Reconciliation | Revenue vs. invoice vs. payment variance detection |
| Vendor & Agent Settlement | Agent financial models, intercompany |

---

## Phase 1 — Your Contributions
**Duration:** Week 1–2 (parallel setup)

- [ ] Review and contribute to ERD for all operational and financial entities:
  - `shipments`, `shipment_legs`, `containers`, `cargo_lines`, `packages`
  - `tracking_events`, `eta_history`, `exceptions`
  - `documents`, `document_versions`, `document_checklists`
  - `financial_entries` (revenue + cost combined with type flag), `invoices`, `invoice_lines`, `payments`
  - `dgr_items`, `dgr_rules`, `customs_declarations`
  - `claims`, `claim_events`
- [ ] Define base API contracts for all operational and financial endpoints
- [ ] Set up Operations and Finance service modules (bounded contexts)
- [ ] Establish unit test suite for all workflow business logic (TDD)

---

## Phase 4 — Shipment Execution Engine (MVP)
**Your Duration:** 8–10 weeks | **SRS Sections:** 10, 11, 14, 15, 16, 17, 53

*This is your heaviest phase — the core of the platform.*

### 4.1 Shipment Workspace API

**Tasks:**
- [ ] `GET /api/v1/shipments/{job_number}` — Master shipment record (hub for all sub-resources):
  - Overview: job number, mode, direction, status, route summary, key dates, assigned team, customer
  - Expandable sub-resources: cargo, containers, documents, tracking, financial, tasks, exceptions, audit
  - Role-based data filtering: `FINANCE_AR` sees full financial; `CUSTOMER_PORTAL` sees tracking + documents only
- [ ] `GET /api/v1/shipments` — Paginated shipment list with rich filters:
  - `?status=IN_TRANSIT&mode=AIR&customer_id=123&assigned_to=ops_team&from_date=&to_date=`
  - Includes RAG (Red/Amber/Green) status per shipment (calculated from SLA engine)
  - Sortable by: ETD, ETA, created_at, priority, RAG
- [ ] `POST /api/v1/shipments/{id}/cargo` — Cargo detail entry:
  - Commodity, HS code, packages (with per-package dimensions), gross weight, net weight, volume
  - For FCL: container details (container number, seal number, VGM, stuffing date, gate-in confirmation)
  - For Air: cargo accepted at warehouse (piece count, condition, screening status)
- [ ] Task management API:
  - `GET /api/v1/shipments/{id}/tasks` — list all tasks for the shipment
  - `PATCH /api/v1/shipments/{id}/tasks/{task_id}` — update task status, notes, completion
  - Tasks auto-created at each state transition (defined in state machine configuration)
  - SLA clock per task (from Architect's SLA engine)

### 4.2 Sea Freight FCL Workflow Engine

**Tasks:**
- [ ] Configure FCL state machine (using Architect's state machine engine — JSON configuration, not code):
  ```
  ENQUIRY → QUOTED → CONFIRMED → CONTAINER_ORDERED → CONTAINER_DELIVERED →
  CARGO_RECEIVED_CY → STUFFED → VGM_SUBMITTED → SHIPPED_ON_BOARD →
  DOCUMENTATION_COMPLETE → DEPARTED → IN_TRANSIT → TRANSSHIPPED → ARRIVED →
  DISCHARGED → CUSTOMS_IN_PROGRESS → CUSTOMS_CLEARED → DO_ISSUED →
  OUT_FOR_DELIVERY → DELIVERED → POD_CONFIRMED → FINANCIALLY_SETTLED → CLOSED
  ```
  - Each transition: entry criteria, mandatory fields, automated actions (events to publish), notifications (who gets notified)

- [ ] **Bill of Lading Management:**
  - BL types: Original BL, Seaway Bill, Express Release, Telex Release
  - House BL / Master BL hierarchy:
    - `POST /api/v1/shipments/{id}/bills-of-lading` — create BL record
    - `master_bl_id` → `[house_bl_id_1, house_bl_id_2, ...]` one-to-many
    - One Master BL per container/vessel booking; one House BL per shipper for LCL
  - BL draft → amendment workflow → final BL approval
  - BL amendment post-sailing: telex release, correction (audited separately with amendment reason)
  - `GET /api/v1/shipments/{id}/bills-of-lading/{bl_id}/pdf` — generate BL PDF
  - `POST /api/v1/bills-of-lading/{id}/release` — issue seaway bill / express release

- [ ] **VGM (Verified Gross Mass) Management:**
  - VGM entry per container: method 1 (certified weighing), method 2 (shipper calculation)
  - VGM cut-off deadline from vessel schedule → alert 24 hours before
  - `POST /api/v1/shipments/{id}/containers/{container_id}/vgm` — record VGM
  - VGM submission tracking: submitted / carrier-confirmed / rejected
  - VGM rejection handling: flag as exception, block departure transition

- [ ] **Demurrage, Detention & Storage Management:**
  - Free-time rules: configurable per `(carrier_id, port_id, container_type)` with default fallback
  - Tables: `free_time_rules`, `free_time_overrides` (per-shipment override with Finance approval)
  - Automatic free-time expiry calculation:
    - Demurrage clock: starts from **discharge** date at destination port
    - Detention clock: starts from **gate-out** (empty pickup) date
    - Terminal storage: starts from **discharge** date (separate from demurrage — different vendor)
  - Proactive alerts (configurable): 3-day, 2-day, 1-day, expired → notify Operations
  - Accruing charge calculation: runs daily cron job, updates `demurrage_accrual` on financial profile
  - SOC vs. COC: SOC (Shipper-Owned Container) → no demurrage applies; COC → carrier's rules apply
  - `GET /api/v1/shipments/{id}/demurrage-status` → real-time D&D position per container

- [ ] Container tracking events:
  - Gate-in, Loaded on Vessel, Gate-Out Empty, Returned to Depot
  - `POST /api/v1/shipments/{id}/containers/{container_id}/events`

### 4.3 Air Freight Direct Workflow Engine

**Tasks:**
- [ ] Configure Air Direct state machine:
  ```
  ENQUIRY → QUOTED → CONFIRMED → CARGO_READY → PICKED_UP → RECEIVED_AT_WAREHOUSE →
  SCREENED → DOCUMENTATION_COMPLETE → MAWB_ISSUED → BOOKED_ON_FLIGHT →
  ACCEPTED_BY_AIRLINE → DEPARTED → IN_TRANSIT → ARRIVED → CARGO_BREAKDOWN →
  CUSTOMS_CLEARED → OUT_FOR_DELIVERY → DELIVERED → POD_CONFIRMED →
  FINANCIALLY_SETTLED → CLOSED
  ```

- [ ] **Air Waybill (AWB) Management:**
  - House AWB (HAWB) / Master AWB (MAWB) hierarchy
  - AWB issuance: sequential AWB number from airline prefix (e.g., `071-` for Ethiopian Airlines)
  - `POST /api/v1/shipments/{id}/awbs` — create AWB record
  - AWB amendment workflow: reason for amendment, amended by, carrier confirmation
  - AWB cancellation workflow
  - Shipper's Letter of Instruction (SLI) linked to each HAWB
  - `GET /api/v1/shipments/{id}/awbs/{awb_id}/label` — IATA barcode label PDF

- [ ] Cargo acceptance checklist API:
  - `POST /api/v1/shipments/{id}/cargo-acceptance` — record warehouse receipt
  - Fields: pieces received, pieces accepted, condition (OK/Damaged/Short), screening status (Screened/X-Ray/Not Required)
  - Discrepancy between booked and received → auto-create `SHORT_SHIPMENT` exception

- [ ] Flight manifest management:
  - `GET /api/v1/flights/{flight_id}/manifest` — all AWBs on this flight with total weight/volume
  - ULD build-up tracking: which AWBs in which ULD

### 4.4 Document Management System

**Tasks:**
- [ ] Document repository API:
  - `POST /api/v1/shipments/{id}/documents` — upload document (multipart, S3 backend)
  - Document types from master (BL, AWB, Commercial Invoice, Packing List, COO, LC, Phytosanitary, DGR Declaration, POD, etc.)
  - Every upload: new version record (`document_id`, `version_number`, `uploaded_by`, `uploaded_at`, `file_path`, `file_size`, `status`)
  - Previous versions immutable — never overwritten
- [ ] Document checklist auto-generation:
  - On booking creation (triggered by Commercial Team's acceptance flow): generate required documents list
  - Rules: mode (Sea/Air) + service type (FCL/LCL/Direct/Consol) + commodity (DGR/Perishable/General) + Incoterm + destination country + LC flag
  - Example: Air + DGR → add "Shipper's Declaration for DGR" + "DGR Checklist" + "Emergency Response"
  - Example: Sea + LC → add "Original BL (3 originals)" + "Certificate of Origin" + "Packing Certificate"
  - `GET /api/v1/shipments/{id}/document-checklist` → list with status (REQUIRED / UPLOADED / APPROVED / MISSING)
- [ ] Document approval workflow (configurable per document type):
  - Draft BL → Operations review → approve/request correction
  - DGR Declaration → Compliance Officer mandatory approval
  - Customs Declaration → Customs team approval
  - `POST /api/v1/documents/{id}/approve` / `reject` / `request-revision`
- [ ] Missing document alerts:
  - On each state transition: check if mandatory documents for that stage are all `APPROVED`
  - If missing: block transition (configurable per doc type as hard/soft block) + send alert
- [ ] Access control enforcement:
  - `CUSTOMER_PORTAL` users: only see documents belonging to their shipments and their company
  - `CARRIER_PORTAL` users: only see transport documents (BL, AWB, manifest)
  - All document actions logged: view, download, upload, approve, reject, share (user + timestamp + IP)
- [ ] Document expiry management:
  - Insurance certificates, permits, licenses have expiry dates
  - Daily job: alert 30 days before expiry, again at 14 days, again at 7 days

### 4.5 Shipment Tracking & Event Model

**Tasks:**
- [ ] Tracking event API:
  - `POST /api/v1/shipments/{id}/events` — record tracking event (manual entry)
  - Event record: `event_type` (from ~60-type taxonomy), `location`, `event_time` (original + UTC normalized), `description`, `source` (MANUAL / CARRIER_API / AGENT / TERMINAL), `created_by`
- [ ] Event taxonomy (implement all ~60 event types from SRS §15.2):
  - **BOOKING:** Requested, Confirmed, Amended, Cancelled, Rolled
  - **CARGO:** Ready, Picked Up, Received at Origin, Stuffed, Screened, Warehouse In, Built Up
  - **TRANSPORT:** Gate In, Loaded, Departed, In Transit, Transshipped, Arrived, Discharged, Gate Out
  - **CUSTOMS:** Declaration Filed, Under Examination, Assessed, Duty Paid, Cleared, Held, Released
  - **DELIVERY:** DO Issued, Out for Delivery, Attempted Delivery, Delivered, POD Received
  - **EXCEPTION:** Delay, Roll, Hold, Missing Document, DGR Issue, Damage, Loss, Short Shipment
- [ ] Event timeline API: `GET /api/v1/shipments/{id}/timeline` → chronological events, most recent first, filterable by category

### 4.6 ETA/ETD Multi-Version Tracking

**Tasks:**
- [ ] ETA/ETD never overwritten — each change appends new record:
  - Table `eta_history`: `shipment_id`, `leg_id`, `type` (ETD/ETA), `version`, `value` (datetime), `source` (QUOTATION / BOOKING / CARRIER_API / MANUAL / TERMINAL), `reason`, `recorded_by`, `recorded_at`
- [ ] Multi-leg cascade: if Leg 1 ETA changes → recalculate connection time at T/S port → update Leg 2 ETD automatically, with `source = AUTO_CASCADE`
- [ ] ETA deviation alert engine (cron job every hour):
  - Compare latest ETA version vs. original planned ETA
  - Deviation > 1 day → `INFO` alert to Operations
  - Deviation > 3 days → `WARNING` alert to Operations + Customer Service
  - Deviation > 7 days → `CRITICAL` alert to Ops Manager → trigger customer notification event
  - Any deviation on shipment with `has_firm_delivery_commitment = true` → immediate `CRITICAL` escalation
- [ ] `GET /api/v1/shipments/{id}/eta-history/{leg_id}` → full ETA version history per leg

### 4.7 Exception Management

**Tasks:**
- [ ] Exception taxonomy (configurable, not hardcoded):
  - Types: DELAY, VESSEL_ROLL, CARGO_HOLD, CUSTOMS_HOLD, MISSING_DOCUMENT, DGR_ISSUE, CARGO_DAMAGE, CARGO_LOSS, SHORT_SHIPMENT, WRONG_DELIVERY, RETURNED
  - Severity: `INFO`, `WARNING`, `CRITICAL`
  - Domain: `BOOKING`, `DOCUMENTATION`, `CUSTOMS`, `CARRIER`, `OPERATIONAL`
- [ ] Exception record:
  - `shipment_id`, `exception_type`, `severity`, `domain`, `status`, `description`, `financial_impact_estimated`, `owner_id` (assigned to), `opened_at`, `acknowledged_at`, `resolved_at`, `resolution_notes`
- [ ] Auto-escalation rules (via Rules Engine):
  - Not acknowledged within 1 hour → escalate to team lead (`sla.breach` event)
  - Not assigned within 2 hours → escalate to department manager
  - SLA breached → escalate to Ops Manager + publish `customer.notification` event
  - CRITICAL unresolved → escalate to Branch Head
  - Financial impact > threshold → notify Finance Controller
- [ ] Exception APIs:
  - `POST /api/v1/shipments/{id}/exceptions` — create exception
  - `PATCH /api/v1/shipments/{id}/exceptions/{exception_id}` — update status, notes, owner
  - `GET /api/v1/exceptions?status=OPEN&severity=CRITICAL` — exception register
  - `GET /api/v1/exceptions/summary` — aggregated counts for Operations Control Tower

---

## Phase 5 — Finance, Invoicing & Compliance
**Your Duration:** 6–8 weeks | **SRS Sections:** 18, 19, 20, 12, 13, 43, 55

### 5.1 Shipment Financial Profile

**Tasks:**
- [ ] Revenue Ledger API:
  - Pre-populated from quotation acceptance (done by Commercial Team's booking flow)
  - `GET /api/v1/shipments/{id}/revenue-ledger` — all revenue lines with status
  - `POST /api/v1/shipments/{id}/revenue-ledger` — add additional charge line (e.g., unexpected surcharge)
  - Status lifecycle: `ESTIMATED → QUOTED → INVOICED → PAID`
  - Any new revenue line not in original quotation: flagged with `is_additional = true`
- [ ] Cost Ledger API (mirrors revenue):
  - `GET /api/v1/shipments/{id}/cost-ledger` — all cost lines with status
  - `POST /api/v1/shipments/{id}/cost-ledger` — add cost line (unexpected cost, e.g., storage, examination)
  - Status lifecycle: `ESTIMATED → ACCRUED → BILLED → VERIFIED → APPROVED → PAID`
  - Any cost not in original quotation: flagged with `is_additional = true`, immediately impacts margin
- [ ] Real-time P&L calculation:
  - `GET /api/v1/shipments/{id}/profitability` — per-shipment P&L
  - Gross Revenue (sum of revenue lines), Direct Cost (sum of cost lines), Gross Profit, Gross Margin %
  - Variance: Quoted Revenue vs. Actual Revenue, Quoted Cost vs. Actual Cost
  - Negative-margin shipment: auto-create `FINANCIAL` exception with `CRITICAL` severity
- [ ] Financial entry immutability:
  - Financial entries are never updated; errors are corrected by reversing entry + creating correct entry
  - All reversals audit-logged with reason and approver

### 5.2 Customer Invoicing

**Tasks:**
- [ ] `POST /api/v1/invoices` — generate invoice from shipment revenue ledger:
  - Sources: approved revenue lines only (no manual charge entry)
  - Invoice references: job number, BL/AWB number, customer PO, quotation reference
  - Multi-currency: invoice in customer's preferred currency; exchange rate locked at invoice date
  - Tax calculation: GST/Sales Tax (Pakistan) or VAT (Saudi/UAE) based on jurisdiction + service type + customer tax profile
  - Invoice line items: each charge code as separate line
- [ ] Invoice approval workflow:
  - Below configurable value threshold → auto-approved
  - Above threshold → requires `FINANCE_AR` approval before sending
- [ ] `GET /api/v1/invoices/{id}/pdf` — branded invoice PDF
- [ ] `POST /api/v1/invoices/{id}/send` — email invoice to customer with PDF attachment; post to customer portal
- [ ] Credit note / debit note workflow:
  - `POST /api/v1/invoices/{id}/credit-note` — reverse full or partial invoice
  - `POST /api/v1/invoices/{id}/debit-note` — add additional charge to existing invoice
  - Both linked back to original invoice for complete AR trail

### 5.3 Vendor Bill Processing (AP)

**Tasks:**
- [ ] `POST /api/v1/vendor-bills` — enter vendor invoice:
  - Link to shipment + cost ledger line
  - Three-way matching: Rate Reference → Service Delivered (shipment event) → Vendor Invoice
  - Variance detection: vendor bill amount vs. estimated cost
  - Within 5% tolerance → auto-approve for payment
  - Outside tolerance → flag for review, create `FINANCIAL_VARIANCE` exception
- [ ] Vendor aging: `GET /api/v1/vendors/{id}/aging` → current, 30, 60, 90, 120+ days outstanding
- [ ] Payment scheduling: honour vendor payment terms; `GET /api/v1/ap/payment-schedule?week=2026-W38`
- [ ] Payment batch: `POST /api/v1/ap/payment-batches` — group multiple vendor bills for single payment run

### 5.4 Accounts Receivable

**Tasks:**
- [ ] Customer aging report: `GET /api/v1/ar/aging` → buckets: current, 30, 60, 90, 120+ days
- [ ] Payment allocation:
  - `POST /api/v1/payments` — record customer payment (amount, date, bank reference)
  - `POST /api/v1/payments/{id}/allocate` — allocate payment against invoice(s)
  - Auto-allocation: oldest invoice first (configurable FIFO/LIFO)
- [ ] Dunning workflow (scheduled job):
  - 7 days overdue → automated reminder email
  - 14 days → second reminder
  - 30 days → Finance team alert + customer email
  - 60 days → Finance Controller alert + customer letter

### 5.5 DGR Compliance Engine

**Tasks:**
- [ ] DGR item data capture API (linked to shipment):
  - `POST /api/v1/shipments/{id}/dgr-items`
  - Fields: UN number, proper shipping name, DG class/division, subsidiary risk, packing group, quantity per package, net quantity, number of packages, packaging instruction, ERG code, technical name (if required)
- [ ] DGR rules database (configurable, not hardcoded — Compliance Admin manages):
  - `POST /api/v1/admin/dgr-rules` — create/update rules
  - Rule types: QUANTITY_LIMIT, COMPATIBILITY, PACKAGING, CARRIER_RESTRICTION, COUNTRY_VARIATION, DOCUMENT_REQUIREMENT
  - Rules tagged by: mode (AIR/SEA), aircraft type (PAX/CAO), carrier (or ALL)
  - Rule versioning: IATA DGR annual update → new rule set version activated
- [ ] DGR validation engine:
  - `POST /api/v1/shipments/{id}/dgr-items/validate` — run validation against active rules
  - Step-by-step validation:
    1. UN number lookup → valid/invalid
    2. Quantity per package ≤ rule limit (PAX vs. CAO)
    3. Packaging instruction compliance
    4. Compatibility check vs. other DG on same shipment/container/ULD
    5. Carrier-specific restrictions
    6. Country/operator variations
  - Response: checklist with PASS/FAIL per rule, failed rules create `DGR_EXCEPTION`
- [ ] DGR document generation:
  - Shipper's Declaration for DGR (IATA format for air, IMO format for sea)
  - DGR checklist per carrier requirements
  - Emergency response information sheet
  - Container/Vehicle Packing Certificate (sea FCL with DGR)
- [ ] Compliance Officer approval:
  - Failed DGR validations block state machine transition until Compliance Officer approves
  - `POST /api/v1/shipments/{id}/dgr-items/{item_id}/approve` — requires `COMPLIANCE_DGR` role
  - Approved DGR record permanently linked to shipment with full audit trail

### 5.6 Customs Module

**Tasks:**
- [ ] Customs declaration data model:
  - `POST /api/v1/shipments/{id}/customs-declarations`
  - Fields: HS code, customs value (amount + currency), country of origin, incoterm, duty rate applied, declaration type (EXPORT/IMPORT), declaration reference (GD number), duty amount, tax amount, total assessable value
- [ ] Configurable jurisdictional rules (Customs Admin manages):
  - Country-specific documentation requirements (Pakistan Form E for exports)
  - Permit requirements (phytosanitary, DRAP, agricultural)
  - FTA preferential rates (SAFTA, PTA) — HS code + country of origin matching
  - Sanctions list per jurisdiction (weekly update scheduled job)
  - Dual-use goods flags
- [ ] Clearance status tracking linked to tracking event model:
  - DECLARATION_FILED → UNDER_EXAMINATION → DUTY_ASSESSED → DUTY_PAID → CLEARED / HELD

### 5.7 LCL Sea Consolidation / Deconsolidation

**Tasks:**
- [ ] Consolidation management:
  - `POST /api/v1/consolidations` — create consolidation (group of LCL shipments into one container)
  - Consolidation planning: `GET /api/v1/consolidations/suggestions?destination=SAJED&date=2026-09-15` — suggests which LCL shipments to group
  - Weight/CBM utilization per consolidation (links to cargo calculator)
- [ ] House BL / Master BL hierarchy enforcement:
  - Each LCL shipment: one House BL (per shipper)
  - Each container: one Master BL (covers all House BLs in that container)
  - One Master BL → many House BLs (one-to-many)
  - Each House BL tracked independently; Master BL managed as unit
- [ ] Financial separation:
  - Each HAWB has own revenue ledger
  - Master BL carries carrier cost → allocated across HAWBs by chargeable weight
  - `GET /api/v1/consolidations/{id}/cost-allocation` — shows cost per HAWB

### 5.8 Air Consolidation / Deconsolidation

**Tasks:**
- [ ] HAWB/MAWB hierarchy: same pattern as LCL (one MAWB → many HAWBs)
- [ ] `GET /api/v1/consolidations/air/planning?destination=JED&flight_date=2026-09-15` — suggest optimal groupings
- [ ] Airline cost → allocated across HAWBs by chargeable weight ratio
- [ ] Break-bulk at destination: `POST /api/v1/consolidations/{id}/deconsolidate` — split into individual HAWB delivery tracking

### 5.9 Claims Management

**Tasks:**
- [ ] `POST /api/v1/claims` — file new claim:
  - Claim types: CARGO_DAMAGE, CARGO_LOSS, SHORT_SHIPMENT, DELAY, WRONG_DELIVERY
  - Fields: claimed amount, currency, description, shipment reference, carrier reference
- [ ] Claims workflow state machine:
  - `REPORTED → ACKNOWLEDGED → DOCUMENTS_COLLECTED → UNDER_INVESTIGATION → LIABILITY_ASSESSED → SETTLEMENT_PROPOSED → CARRIER_CLAIM_FILED → INSURANCE_CLAIM_FILED → RECOVERY_IN_PROGRESS → SETTLED → CLOSED`
- [ ] Financial impact:
  - Claim amount linked to shipment profitability as additional cost
  - Insurance recovery tracked as revenue credit
  - Net loss calculation: total claim - carrier recovery - insurance recovery
- [ ] Claims history feeds into carrier performance score (carrier reliability metric)

### 5.10 Automated Reconciliation

**Tasks:**
- [ ] Weekly reconciliation job:
  - Revenue billed > revenue quoted → overbilling flag
  - Cost billed > cost accrued (threshold configurable, default 5%) → margin impact flag
  - `status = DELIVERED` but no invoice raised → revenue leakage flag
  - Vendor bill received but no corresponding cost ledger entry → unregistered cost flag
  - Payment received but no matching invoice → suspense flag
- [ ] `GET /api/v1/reconciliation/report?week=2026-W38` — weekly exception list
- [ ] Auto-close: variances within tolerance → auto-resolved; outside tolerance → create reconciliation task

---

## Phase 6 — Your Contributions

- [ ] Shipment tracking events consumed and exposed via customer portal API (coordinate with Frontend team)
- [ ] POD (Proof of Delivery) API: `POST /api/v1/shipments/{id}/pod` — record delivery confirmation, GPS location, signature (base64), photos (S3 URLs), delivered pieces, condition
- [ ] Agent portal: `GET /api/v1/agent-portal/my-jobs` — jobs assigned to calling agent

---

## Phase 7 — Your Contributions
*Operations & Finance analytics*

- [ ] `GET /api/v1/analytics/operations` — on-time departure/arrival %, exception rate per 100 shipments
- [ ] `GET /api/v1/analytics/financial` — revenue/cost/GP by period/customer/lane; margin distribution; AR/AP aging
- [ ] `GET /api/v1/analytics/demurrage` — D&D cost by customer, carrier, port
- [ ] `GET /api/v1/analytics/carrier-performance` — on-time %, booking reliability, claims frequency

---

## Phase 8 — Your Contributions
*AI + Advanced workflows*

- [ ] **Tracking Anomaly Detection** integration: consume AI alerts for idle shipments → auto-create exception
- [ ] **Exception Prediction** integration: AI flags at-risk shipments → surface on Operations Control Tower
- [ ] EDI/EDIFACT event ingestion: `CUSREP` (customs status), `BAPLIE` (bay plan), `COPARN` (container order) → parsed into tracking events
- [ ] Partial delivery tracking: `POST /api/v1/shipments/{id}/partial-delivery` — record partial POD, track remaining quantity

---

## Tech Stack You Own

| Tool | Purpose |
|---|---|
| **FastAPI / NestJS** | Operations and Finance service API |
| **Celery / BullMQ** | Async: D&D accrual job, SLA breach detection, reconciliation |
| **AWS S3** | Document file storage (versioned bucket) |
| **WeasyPrint / Puppeteer** | AWB label, BL PDF, Invoice PDF generation |
| **APScheduler / node-cron** | ETA deviation checks, D&D accrual, dunning workflows |
| **PyPDF2 / pdf-lib** | DGR document assembly |

---

*Document: FC-TEAM-003 · Backend Developer (Operations & Finance) · FreightCore™*
