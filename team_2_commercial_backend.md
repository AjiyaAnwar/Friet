# FreightCore™ — Team Member 2: Backend Developer (Commercial Engine)
**Role: Backend Developer — Commercial, Rate & Quotation Engine**
*Al-Rahim Group / Inter-Fret Consolidators (Pvt.) Ltd. · ARG-SRS-FFMS-2026-001*

---

> [!IMPORTANT]
> You own the **revenue-generating core** of FreightCore™ — every dollar the company earns flows through your code. The rate engine, quotation engine, and booking workflow are the most financially critical parts of the system. A 1% rate error on a high-volume lane means significant annual margin leakage.

---

## Your Ownership Map

| Domain | Your Responsibility |
|---|---|
| Master Data (Geographic + Reference) | All lookup tables, CRUD APIs, import tools |
| Carrier & Network Master | Shipping lines, airlines, schedules, vessel/flight data |
| Customer & Vendor Master | Customer master with credit tier, vendor records |
| Rate / Tariff Engine | Rate CRUD, versioning, approval, expiry, import |
| Automatic Rate Selection Logic | Priority cascade, multi-carrier comparison |
| Cargo Calculation Engine | Chargeable weight, container utilization, W/M rating |
| Route Management Engine | Route data model, comparison, optimization |
| RFQ / Quotation Engine | RFQ capture, multi-option quote generation, margin rules |
| Quotation Approval Workflow | Below-margin triggers, DGR flags, Finance review |
| Customer Acceptance & Booking | Acceptance trigger, pre-booking validations, job creation |
| Customer Credit Control | Credit limit, exposure calculation, booking block |
| Agent Rate Management | Agent rate agreements, rate sharing |

---

## Phase 1 — Your Contributions
**Duration:** Week 1–2 (parallel with Backend Architect)

- [ ] Review and contribute to the ERD for all commercial entities:
  - `customers`, `vendors`, `agents`, `employees`
  - `rfq_requests`, `quotations`, `quotation_lines`, `quotation_options`
  - `rates`, `rate_versions`, `rate_lines`, `rate_surcharges`
  - `shipments` (skeleton — Operations team fills in)
  - `jobs` (accepted quotation → job record)
- [ ] Define base API response contracts for all commercial endpoints (coordinate with Architect)
- [ ] Set up the Commercial service module in the project (bounded context)
- [ ] Write unit test framework for all commercial calculation logic (TDD from Day 1)

---

## Phase 2 — Master Data & Configuration Engine
**Your Duration:** 4–6 weeks | **SRS Sections:** 44, 45, 5.1–5.3, 6.3, 27, 29

### 2.1 Geographic Master Data

**Tasks:**
- [ ] `POST /api/v1/admin/countries` — CRUD for Country Master
  - Fields: ISO 3166 code, name, region, trade zone, `is_sanctioned` flag, `requires_permit` flag
  - Seed data: load all ISO 3166 countries on initial migration
- [ ] `POST /api/v1/admin/locations` — Port/Airport Master
  - Fields: UN/LOCODE, IATA code, name, country, city, type (SEA_PORT / AIRPORT / ICD / CFS), time zone, `is_active`
  - Seed data: all UN/LOCODE ports and IATA airports (from public datasets)
  - Import tool: CSV/Excel bulk upload with validation report
- [ ] `POST /api/v1/admin/zones` — Inland zone master for trucking rating
  - Zone name, country, cities included, `zone_code`
- [ ] Location search API: `GET /api/v1/locations?q=karachi&type=AIRPORT` → typeahead for RFQ form

### 2.2 Carrier & Network Master

**Tasks:**
- [ ] `POST /api/v1/admin/carriers` — Carrier Master (both shipping lines and airlines)
  - Shipping line: SCAC code, name, `is_nvocc`, website, contact
  - Airline: IATA 2-letter code, IATA 3-digit prefix (e.g., `071` for Ethiopian), name, hub airports, cargo contacts
- [ ] `POST /api/v1/admin/vessels` — Vessel Master
  - IMO number, vessel name, flag, owner (FK → carrier), TEU capacity, vessel type
- [ ] `POST /api/v1/admin/flight-schedules` — Flight Schedule Master
  - Airline, route (origin airport → destination airport), flight number, frequency (days of week), scheduled departure, scheduled arrival, cargo cut-off, documentation cut-off
- [ ] `POST /api/v1/admin/vessel-schedules` — Vessel Schedule (Port Rotation)
  - Carrier, service name, vessel, voyage number, port rotation with ETD/ETA per port call, CY cut-off, SI cut-off, VGM cut-off
- [ ] `GET /api/v1/schedules/sea?origin=PKKAR&destination=SAJED&from=2026-09-01` — schedule search for Pricing team

### 2.3 Customer & Vendor Master

**Tasks:**
- [ ] Customer Master API — `POST /api/v1/customers`:
  - Company: name, tax registration, registration number, IATA/FIATA membership
  - Address: registered, billing, operational
  - Credit profile: credit limit (amount + currency), payment terms (days), credit tier (`A`, `B`, `C`, `NEW`, `BLOCKED`)
  - Preferences: preferred carriers (list), preferred trade lanes, preferred service types
  - Contacts: multiple contacts per customer with role (billing, operations, director)
  - `is_active`, `kyc_status`, `onboarding_date`
  - Customer code generation: configurable format (e.g., `CUST-0001`)
- [ ] Customer portal user linkage: customer record → multiple portal user accounts
- [ ] Vendor Master API — `POST /api/v1/vendors`:
  - Vendor type enum: `SHIPPING_LINE`, `AIRLINE`, `NVOCC`, `TRUCKING`, `CFS_OPERATOR`, `CUSTOMS_BROKER`, `TERMINAL`, `GHA`, `INSURANCE`, `SURVEY`, `WAREHOUSE`
  - All fields: company details, tax registration, bank details, payment terms
  - Vendor performance score (calculated field, updated by Operations after Phase 4)
- [ ] Agent Master API — `POST /api/v1/agents`:
  - Coverage: country, city, services provided (CUSTOMS, TRUCKING, WAREHOUSING, DOCUMENTATION, DELIVERY)
  - Certifications, key contacts, settlement model (INVOICE / COMMISSION / NETTING)
  - Rate agreements linked to agent record

### 2.4 Reference / Lookup Tables

**Tasks:**
- [ ] Implement all reference tables with CRUD APIs and seed data:
  - `POST /api/v1/admin/incoterms` — all 11 Incoterms 2020 codes
  - `POST /api/v1/admin/container-types` — 20GP, 40GP, 40HC, 20RF, 40RF, 20OT, 40OT, 20FR, 40FR with CBM and max payload specs
  - `POST /api/v1/admin/commodities` — commodity master with HS code (6-digit), `is_dgr` flag, export/import restrictions
  - `POST /api/v1/admin/currencies` — ISO 4217 codes; daily exchange rate management
  - `POST /api/v1/admin/package-types` — UN/CEFACT codes (CTN, PLT, DRM, BAG, BDL, etc.)
  - `POST /api/v1/admin/uld-types` — ULD type master with volume specs
  - `POST /api/v1/admin/charge-codes` — all charge codes with type, rate basis, applicable mode
  - `POST /api/v1/admin/document-types` — all document type codes
- [ ] Exchange rate management:
  - `PATCH /api/v1/admin/currencies/{code}/exchange-rate` — manual rate entry
  - Scheduled job: daily rate fetch from configurable source (central bank API or manual)
  - Rate locking: exchange rate frozen at quotation time, invoice time, payment time (configurable per setting)
  - Realized/unrealized FX gain/loss calculation logic

### 2.5 Rate / Tariff Engine

**Tasks:**
- [ ] Rate Record CRUD — `POST /api/v1/rates`:
  - All header fields (SRS §5.2.1): Rate ID, Type, Category, Carrier/Provider, Service, Origin, Destination, Via/Routing, Commodity, Effective Date, Expiry Date, Currency, Status
  - Rate basis lines (SRS Table 12): Ocean Freight, Air Freight weight breaks (+45, +100, +250, +500, +1000), Minimum Charge, BAF, FSC, THC Origin/Destination, Documentation Fee, Handling, Customs, Pickup/Delivery, Storage, Demurrage, Detention, DGR Surcharge, PSS, EBS, War Risk, AWB Fee, ULD Surcharge, Screening Fee
- [ ] Rate versioning:
  - Every modification creates a new version record (previous version immutable)
  - Version metadata: version number, modified by, modified date, reason, approval status
  - Active quotations reference specific rate version — not retroactively changed
  - Rate comparison view: current vs. previous version side-by-side
- [ ] Rate approval workflow (state machine via Architect's engine):
  - `DRAFT → PENDING_APPROVAL → APPROVED → ACTIVE → EXPIRED → SUPERSEDED → CANCELLED`
  - Approval thresholds configurable: rates below minimum margin or above cost threshold require Finance approval
  - Email notification to Pricing Manager on new rate awaiting approval
- [ ] Rate import from Excel/CSV:
  - `POST /api/v1/rates/import` — multipart file upload
  - Validation: check all required fields, valid port codes, valid carrier, valid dates, no overlapping rates
  - Import report: success count, error count, per-row error details
  - Preview mode: validate without committing
- [ ] Rate expiry management:
  - Scheduled job (runs daily): check rates expiring in 7 days → notify Pricing team
  - Rates expiring in 3 days → escalate to Pricing Manager
  - Expired rates: auto-transition to `EXPIRED` status
  - Any quotation referencing expired rate: flagged with alert
- [ ] Customer-specific and contract rates:
  - FAK, NAC, Spot, Promotional, Agent rate categories
  - Customer-rate linkage: `customer_id` on contract/spot rates
  - Volume commitment tracking on NAC rates
- [ ] Rate utilization report: which rates are actively used in quotations, which are dormant

---

## Phase 3 — Commercial Engine
**Your Duration:** 6–8 weeks | **SRS Sections:** 4, 5.6–5.8, 7, 8, 9, 20

### 3.1 RFQ Capture API

**Tasks:**
- [ ] `POST /api/v1/rfqs` — Create new RFQ with full dynamic form data:
  - **Party Information** (Table 4): Customer, Shipper, Consignee, Notify Party (up to 3), Buyer
  - **Origin/Destination** (Table 5): Country, City, Port/Airport, Pickup/Delivery address, Place of Receipt/Delivery
  - **Cargo Details** (Table 6): Commodity, HS Code, Packages, Package Type, Gross Weight, Net Weight, Volume, L/W/H per package, Cargo Value, Currency, `is_stackable`, `is_tiltable`
  - **Container Requirements** (Table 7, FCL only): Container Type(s), Qty per type, Weight per container, Temperature (reefer), Genset Required, SOC/COC, OOG dimensions
  - **Service & Shipping** (Table 8): Mode (SEA/AIR), Service Type (FCL/LCL/DIRECT/CONSOL), Incoterm + Place, Movement Type (D2D/P2P/D2P/P2D/A2A), Cargo Readiness Date, Preferred Departure, Required Delivery, Preferred Carrier, Priority
  - **Special Requirements** (Table 9): DGR flag (triggers DGR sub-form), Temperature Controlled, Insurance, Fumigation, Inspection, Special Handling codes, Customs documents required, LC flag + LC number
- [ ] RFQ validation:
  - Mode-specific mandatory fields (e.g., container type mandatory for FCL, dimensions for LCL/Air)
  - DGR flag → validate DGR sub-form fields populated
  - LC flag → LC number required
  - Required Delivery Date ≥ Preferred Departure Date ≥ today
- [ ] RFQ state machine transitions (via Architect's state machine engine):
  - `DRAFT → SUBMITTED → PRICING_IN_PROGRESS → QUOTED → SENT_TO_CUSTOMER → ACCEPTED → REJECTED → EXPIRED → REVISED → CANCELLED`
- [ ] RFQ assignment: `PATCH /api/v1/rfqs/{id}/assign` → assign to Pricing analyst; SLA clock starts
- [ ] RFQ list API with filters: `GET /api/v1/rfqs?status=PRICING_IN_PROGRESS&assigned_to=me`

### 3.2 Cargo Calculation Engine

**Tasks:**
- [ ] **Air Freight Chargeable Weight Calculator:**
  - Input: array of packages with `{gross_weight_kg, length_cm, width_cm, height_cm, quantity}`
  - Volumetric weight per piece: `(L × W × H) / divisor` (default 6,000; configurable per carrier)
  - Total volumetric weight: sum across all pieces
  - Chargeable weight: `MAX(total_gross_weight, total_volumetric_weight)`
  - **Pivot/Break Weight Optimization:**
    - For each rate break above chargeable weight: calculate total charge at that break's per-kg rate
    - If `rate_at_break × break_weight < rate_at_actual × actual_weight` → offer as cheaper option
    - Return both options to pricing analyst with recommendation
  - API: `POST /api/v1/calculations/air-chargeable-weight`

- [ ] **Sea Freight FCL Container Utilization Calculator:**
  - Input: cargo details (CBM, gross weight), container type selected
  - Volume utilization: `(Total CBM / Container CBM capacity) × 100%`
  - Weight utilization: `(Gross Weight / Max payload) × 100%`
  - Effective utilization: `MIN(volume_pct, weight_pct)`
  - Warnings: volume > 95% or weight > 90% (configurable per container type)
  - Suggestions: if 40GP volume > 95%, suggest 40HC; if weight > 90% of 20GP, suggest 40GP
  - API: `POST /api/v1/calculations/container-utilization`

- [ ] **Sea Freight LCL Revenue Ton Calculator:**
  - `Revenue Tons (W/M) = MAX(Gross Weight kg / 1000, CBM)`
  - Minimum charge enforcement: if W/M falls below carrier minimum, apply minimum charge
  - API: `POST /api/v1/calculations/lcl-revenue-tons`

### 3.3 Automatic Rate Selection Engine

**Tasks:**
- [ ] Implement rate selection priority cascade for a given RFQ:
  1. Customer-specific contract rate (NAC) — if exists and valid
  2. Customer-specific spot rate — if exists and valid
  3. NAC rate for customer's trade lane — if exists
  4. Promotional rate — if available for lane/commodity
  5. Best FAK rate (configurable: lowest cost or best margin)
  6. Agent rate — for origin/destination charges
  7. Fallback: `NO_RATE_AVAILABLE` flag → manual pricing required
- [ ] Rate validity check: effective_date ≤ today ≤ expiry_date; status = ACTIVE
- [ ] Surcharge auto-attachment: for each selected base rate, automatically attach applicable surcharges (BAF, FSC, SSC, PSS, EBS — based on origin/destination/commodity/carrier/date)
- [ ] Multi-carrier rate comparison (SRS §5.7):
  - For a given RFQ, find all applicable rates across all carriers on the lane
  - Return side-by-side comparison: carrier, service, transit time, base freight, surcharges, total landed cost, margin at proposed sell, recommendation score
  - API: `GET /api/v1/rfqs/{id}/rate-options`

### 3.4 Route Management Engine

**Tasks:**
- [ ] Route data model:
  - `Route` entity: origin → destination, mode, legs (array)
  - `RouteLeg` entity: from_location, to_location, carrier, vessel/flight, ETD, ETA, transit_time_hours, transshipment_point flag
- [ ] Route discovery: given origin + destination + mode → find all available routes (direct + transshipment combinations)
- [ ] Route comparison engine (SRS Table 16):
  - **Cheapest:** total landed cost (freight + surcharges + local charges)
  - **Fastest:** total transit time hours/days
  - **Lowest-risk:** fewest transshipments, highest carrier reliability score, lowest congestion index
  - **Best margin:** highest gross margin at proposed selling price
  - **Customer preferred:** matches customer's stated carrier/routing preference
  - **Most reliable:** on-time arrival % over trailing 12 months (from tracking history)
- [ ] Route optimization factors:
  - Direct vs. transshipment: transshipment connection reliability (historical missed-connection rate)
  - Seasonal factors: flag if shipment date falls in peak season, Ramadan, Chinese New Year
  - Embargo check: is origin/destination/commodity combination restricted by any carrier?
  - Free-time at transshipment points: flag if free-time is tight given ETA/connection
- [ ] API: `GET /api/v1/rfqs/{id}/route-options` → returns ranked route options with all comparison dimensions

### 3.5 Quotation Engine

**Tasks:**
- [ ] `POST /api/v1/quotations` — Generate quotation from RFQ:
  - Multi-option generation: Option A (cheapest), Option B (fastest), Option C (best value), optional sea vs. air comparison, different carriers on same route
  - Each option: complete charge line breakdown
  - Charge line items per option:
    - Ocean/Air Freight (with rate version reference, weight/container basis, amount)
    - Each surcharge line: BAF, FSC, THC-O, THC-D, SSC, PSS, etc.
    - Local charges: pickup, delivery, customs, documentation, handling
    - Agent charges: origin/destination agent fees
    - Subtotal cost, markup, subtotal sell price, gross margin PKR, margin %
  - Grand total: total sell price (customer pays), total cost (IFCL pays), gross profit, margin %
  - Multi-currency: rate in carrier currency → converted to sell currency using locked exchange rate
- [ ] **Margin Rules Engine:**
  - Load configured minimum margin rules from Rules Engine (Phase 1 Architect):
    - Min margin % per service type (air ≥ 8%, sea FCL ≥ 5%, configurable)
    - Min margin amount per shipment (e.g., min USD 50)
    - Customer-tier overrides (A-tier may accept lower minimum)
    - Lane-specific overrides
  - On quotation save: evaluate all margin rules
  - If any rule fails → quotation status = `BELOW_MARGIN` → requires Pricing Manager approval
- [ ] Quotation approval workflow:
  - Below-margin → Pricing Manager approval
  - High value (> configurable threshold) → Finance Controller approval
  - New/high-risk customer → additional review flag
  - DGR involved → Compliance Officer review flag
  - Manual price override → flagged for review
- [ ] Quotation expiry:
  - Expiry date set on creation (based on rate validity and configurable quotation validity period)
  - Expired quotations cannot be accepted without rate re-validation
  - System auto-sets status to `EXPIRED` on expiry date
- [ ] Revised quotation chain:
  - When quotation is revised → new quotation record with `parent_quotation_id` linkage
  - Full chain traceable for any accepted quotation
- [ ] PDF generation:
  - `GET /api/v1/quotations/{id}/pdf` → branded PDF with IFCL letterhead
  - Configurable template (company logo, contact details, terms and conditions)
  - All charge lines itemized, validity date, reference numbers
- [ ] `POST /api/v1/quotations/{id}/send` → mark as `SENT_TO_CUSTOMER`, log timestamp, trigger notification event

### 3.6 Customer Acceptance & Booking Creation

**Tasks:**
- [ ] `POST /api/v1/quotations/{id}/accept` — Trigger customer acceptance
- [ ] Pre-booking validation sequence (must all pass before job creation):
  1. **Credit Check:**
     - Current exposure = unpaid invoices + estimated value of in-progress shipments + pending bookings
     - New exposure = current exposure + quotation total value
     - If new exposure > credit limit → block, notify Finance, return 422 with `CREDIT_LIMIT_EXCEEDED`
     - If any invoice > `X` days overdue (configurable) → same block
  2. **Rate validity re-check:** all rate versions referenced in quotation still active on today's date
  3. **Document readiness:** minimum required documents flagged (not blocking at acceptance — advisory only for MVP)
  4. **Sanctions screening:** customer, shipper, consignee, notify party names checked against configured sanctions lists (OFAC, UN, EU) — use vendor API or local list
  5. **Embargo check:** origin country + destination country + commodity → no trade restriction active
- [ ] On all validations passing — auto-create records (no manual re-entry):
  - **Job Record** with unique job number format: `{Branch}-{Mode}-{Direction}-{YY}{MM}-{Seq}` e.g., `KHI-AIR-EXP-2609-00147`
  - **Shipment Record** linked to job (Operations team fills in details)
  - **Revenue Ledger** — pre-populate each quotation charge line as revenue entry (status: `ESTIMATED`)
  - **Cost Ledger** — pre-populate each cost line from rate references (status: `ESTIMATED`)
  - **Document Checklist** — auto-generate required documents based on mode/service/commodity/DGR/Incoterm/destination
  - **Task Queue** — create initial tasks and assign to relevant departments
  - Publish `booking.confirmed` domain event
- [ ] Quotation status → `ACCEPTED`; shipment status → `BOOKED`

### 3.7 Customer Credit Control

**Tasks:**
- [ ] `GET /api/v1/customers/{id}/credit-position` — real-time credit exposure:
  - Credit limit, total exposure, available credit, overdue amount, oldest invoice date
- [ ] `POST /api/v1/customers/{id}/credit-overrides` — one-time Finance-approved override for blocked booking:
  - Requires `FINANCE_CONTROLLER` role
  - Override reason, approved by, valid for (date range)
  - Audit-logged
- [ ] `PATCH /api/v1/customers/{id}/credit-limit` — update credit limit (requires Finance Controller)
- [ ] Credit block dashboard: list all customers at/near limit or with overdue invoices

---

## Phase 5 — Your Contributions
*Rate-related financial integrity*

- [ ] Rate expiry check at vendor bill matching: if vendor invoice rate differs from contracted rate, flag
- [ ] Agent settlement rate management: ensure agent rates are correctly applied in cost ledger
- [ ] Quarterly rate review report: compare contracted rates vs. market rates for Pricing Manager

---

## Phase 7 — Your Contributions
*Commercial analytics*

- [ ] Sales analytics data layer:
  - `GET /api/v1/analytics/rfq-funnel` — RFQ count, conversion rate at each stage, avg aging
  - `GET /api/v1/analytics/quotation-win-loss` — win/loss by customer, lane, carrier
  - `GET /api/v1/analytics/revenue` — by customer, trade lane, mode, branch, period
- [ ] Rate competitiveness analysis: compare IFCL rates vs. market average for top lanes
- [ ] Rate utilization heatmap: which lanes have active rates, which have no coverage

---

## Phase 8 — Your Contributions
*AI-assisted pricing*

- [ ] **Pricing Recommendation Agent** integration:
  - Receive AI-suggested sell rate for given RFQ (from AI team)
  - Display recommendation alongside Pricing Analyst's manual rate with confidence score
  - Accept/reject action: analyst can accept AI suggestion or override with reason
  - All AI recommendations audit-logged (separate from operational audit)
- [ ] **RFQ Parsing Agent** integration:
  - Customer emails/WhatsApp → parsed structured RFQ fields
  - Present extracted fields in RFQ form pre-populated for human review + correction
- [ ] Multi-currency expansion: PKR base for Pakistan, SAR base for Saudi (already designed, now activated)

---

## Tech Stack You Own

| Tool | Purpose |
|---|---|
| **FastAPI / NestJS** | Commercial service API endpoints |
| **SQLAlchemy / TypeORM** | ORM for all commercial entities |
| **Celery / BullMQ** | Async tasks: rate expiry checks, import processing, PDF generation |
| **WeasyPrint / Puppeteer** | PDF generation for quotations and rate sheets |
| **Pandas** | Excel/CSV rate import processing and validation |
| **Exchange Rate API** | Daily FX rate fetch (configurable source) |

---

*Document: FC-TEAM-002 · Backend Developer (Commercial Engine) · FreightCore™*
