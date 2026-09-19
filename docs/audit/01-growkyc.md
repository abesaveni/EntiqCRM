# Repo 1 — GrowKyc  (github.com/abesaveni/GrowKyc)
Local: D:\Grow Entiq Projects\GrowKyc   main @ fd61bce, clean, in sync w/ origin

## Shape
Monorepo, two apps:
- `Growkyc_backend/` — Python FastAPI
- `Growkyc-main/`    — React + Vite + TS frontend
Plus: supabase/ (legacy?), docs/, many one-off .sh migration scripts at root.

## Backend stack
FastAPI 0.104.1 / SQLAlchemy 2.0.23 / Pydantic 2.5 / Alembic
Celery 5.3.6 + Redis (workers: case, comms, document, monitoring, notification, reporting, screening)
APScheduler (doc expiry), slowapi (rate limit), python-jose JWT, passlib/bcrypt, pyotp (MFA)
DB: DATABASE_URL — sqlite default (kyc.db), postgres + mssql branches supported
Storage: pluggable — local | S3 (services/storage/factory.py)
OCR: pluggable — Textract | Azure Form Recognizer | Google DocAI | Tesseract | mock

## Scale
- 68 routers, **697 endpoints**
- 80 model modules, 90+ services
- Frontend: 775 .tsx + 377 .ts

## Multi-tenancy — STRONG (this is the big asset)
- `Tenant` model = one firm/practice. slug, status (pending_approval|active|suspended|
  rejected|cancelled|trial), subscription_plan, approval/suspension audit trail.
- Enforced centrally in `database.py`:
  - global read filter via SQLAlchemy `do_orm_execute` + `with_loader_criteria`
  - cross-tenant **write guard** on `before_flush` -> TenantIsolationError
  - `core/tenant_scope.py` = single source of truth for which tables are scoped
- Exempt (global) tables: users, user_sessions, audit_logs, api_errors
- "Shared row" tables (NULL tenant_id = shared catalogue): screening_datasets, screening_tags
- `TenantContextMiddleware` resolves tenant per request
- **Head Office plane** (routers/head_office.py) = cross-tenant platform admin:
  overview, tenants, onboarded-clients, plans, providers
- `routers/practices.py` = tenant lifecycle: approve/reject/suspend/reactivate + user mgmt

## Auth / RBAC
- JWT (HS256) bearer + cookie (`core/auth_cookie.py`); token blacklist; step-up auth
  (`core/step_up.py`); client_session; session follows person not clock (recent commit)
- Roles (core/enums.UserRole): Admin, User(=Client), Analyst, Compliance_Officer,
  Senior_Compliance_Officer, Head_of_Compliance, MLRO(legacy alias), Auditor
- `models/role_permission.py` + `services/rbac_service.py` + `core/permissions.py`
  + `core/route_policy.py` — permission layer exists beyond bare roles
- `must_change_password` server-side lockout when admin sets a password
- Production safety gate: `verify_production_safety()` refuses boot if prod configured
  with dev toggles (mock payments/screening). Also hard-fails on weak SECRET_KEY / CORS '*'

## ⚠ Tenancy constraint for the CRM hub
`users.email` is **globally unique** and `users` is tenant-EXEMPT.
=> one email = one user = one tenant. A person cannot belong to 2 tenants.
This must be resolved before GrowKyc's user table can back a shared Entiq CRM identity.

## Existing CRM module (already present!)  routers/crm.py — 30 endpoints
contacts | client 360 timeline | notes | tasks (assign/complete) | global search |
comms | duplicate detection | parties (+screen) | staff | saved segments (+members) |
bulk client actions | **pipeline** | reviews-due | mark-reviewed | dvs | rescreen |
segments + segment send
Models: `ClientNote`, `ClientTask` (both tenant-scoped, author/assignee attributed)
Plus `models/saved_segment.py`, `models/comms.py`, `services/crm_service.py`, `comms_hub.py`
=> GrowKyc already contains a thin but real CRM core. STRONG candidate for the hub base.

## Existing Training module  routers/training.py — 3 endpoints
GET /courses, GET /completions, POST /completions + `models/training.py`
=> stub-level only. Real training product is Entiq Academy (separate repo).

## Money modules present
- billing.py (10) — pricing, checkout, practice-pays, billing events, invoice projection
- invoices.py (4) — list/create/payment-link/status
- payments.py + square_payments.py — Square SDK (currently disabled: pydantic pin conflict)
- models: plan.py, billing.py, invoice.py, payment.py
- referrals.py (2) + models/referral.py

## Other major domains (relevant as CRM data sources)
- clients.py (44) — individual + entity (KYB), ownership graph, UBO, trust roles,
  registry extracts, DVS verify, addresses, documents
- onboarding.py (34) — onboarding flows
- cases.py (21) — case mgmt w/ SLA, assignments, comments, events, evidence, snapshots,
  hash-chain integrity (core/case_chain.py, core/hash_chain.py)
- compatibility.py (108) + route_aliases.py (18) — legacy path shims (tech debt)
- AML/AUSTRAC suite: ~30 routers, ~200 endpoints (programme, governance, reporting,
  lodgement, reliance, control testing, personnel, firm risk, SoF, retention, starter kit)
- screening.py + screening_sources.py (37) — OpenSanctions + uploaded sources, tiered screening
- sharing.py (7) — cross-firm share requests + client portal (feature-flagged OFF in prod)
- sar.py, edd.py, risk.py, alerts.py, audit.py, reports.py, reporting_rules.py

## External integrations (services/providers/)
Didit (KYC/IDV) · Equifax (10 modules: SOAP, identity, company enquiry/file, CBO,
digital identity, entity validation, apply, screening, previous enquiry) ·
FrankieOne · Trulioo · ABR ABN lookup · PEXA · Square · OpenAI (compliance bot) ·
push notifications · AWS S3 · Textract/Azure/Google OCR

## Risks / debt noted so far
- `.env` files present in both backend and frontend dirs (check if git-tracked — P0 if so)
- `kyc.db`, `demo_seed.db`, `.db.backup-*` (2MB SQLite files) committed in tree
- 108-endpoint `compatibility.py` + 18 route_aliases = legacy surface to retire
- Square disabled by dependency conflict (pydantic 2.5 pin)
- `tenant_id` still nullable on most tables (Phase 1 of a 4-phase plan, never finished)
- ~13 ad-hoc .sh data-fix scripts at repo root = manual migration history
- Root repo also contains `Growkyc-main/dist/` and `node_modules/` (check .gitignore)

## Open
- Frontend structure — NEXT
- Deployment (docker-compose, Dockerfile) — NEXT
- Test coverage — NEXT

---
# PART 2 — Frontend, deploy, existing platform doctrine

## CORRECTION to earlier note
`.env` and `*.db` are **NOT** git-tracked (verified `git ls-files`). No secret leak. 1947 tracked files.

## Frontend (Growkyc-main)
React 18 · Vite 6 · TS 6 · Tailwind 4 · Radix/shadcn (59 ui files) · react-router 7
recharts · reactflow (ownership graph) · leaflet · framer-motion · react-hook-form + zod
axios · Sentry · jspdf · qrcode.react · react-dnd
Origin: **Figma Make export** (package name `@figma/my-make-file`) — explains the sprawl.
Leftovers: `@supabase/supabase-js` + two `supabase/` dirs (legacy, unused path)
`@aws-sdk/client-s3` in the browser bundle — CHECK for credential exposure.
Routing: single `App.tsx` (1930 lines), route-scoped audiences.

### Component inventory (tsx count / API-wired count)
REAL PRODUCT (wired):
  aml            53 / 50   <- most complete module in the whole frontend
  kyc           124 / 24
  grow-kyc      123 / 16
  case           32 /  7
  admin          21 /  6
  austrac        13 /  4
  onboarding     34 /  2
  crm             7 /  2   <- CRM UI exists but barely wired
PROTOTYPE / NOT WIRED (0 API calls, mock data only):
  grow-accounting 58 / 0   <- FULL accounting practice UI incl. Xero (see below)
  grow-hq         14 / 0   <- platform/hub shell (see below)
  grow-esign       2 / 0
  support          1 / 0
  deals            1 / 0
  onecore 12, pfa 25, imfo 19, ent 10, receivership 8  <- unrelated verticals, dead
  + auction, escrow, settlement, apex-trust, qld-association, govsign, buynow,
    nowwork, ultimate-os — Figma Make prototype debris

### grow-hq/ = the CRM hub already sketched in UI (mock only)
MultiFirmManagement · ModuleConfig · ModuleSettings · SharedBackbone ·
IntegrationArchitecture · IntegrationsHub · AccessControl · BrandingEditor ·
VerticalOnboarding · PlatformSettings · UserManagement · GrowHQDashboard · HelpCenter
=> design intent for the hub exists. Reusable as UX reference, not as code.

### grow-accounting/ = full accounting practice-management UI (mock only)
Workpapers engine (Excel builder/editor/review/signoff), Trial Balance, lead schedules
(Receivables/Payables/Fixed Assets/Inventory/Equity), GST-BAS, Payroll+Super, Tax
reconciliation + worksheet, Division 7A, Cash reconciliation, Binder generator,
Jobs Kanban + JobDetail + RecurringJobs, TimeTracking, ResourceManagement,
ReviewQueue, RiskDashboard, ClientPortal, ClientOnboarding, WorkflowBuilder,
**Xero integration** (XeroIntegration/XeroMapping/XeroAccountMapping/XeroSyncManager/
JournalPushControl/ExcelWorkpaperWithXero)
=> MUST be cross-checked against the GrowAccounting repo (repo #2) — likely
   duplicate/divergent implementations of the same product. Decide one home.

## Deployment (backend)
docker-compose: postgres:15-alpine + redis:7-alpine + kyc_api + celery_worker + celery_beat
API: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker --preload --timeout 120`
Healthchecks on all services; `/health/deep` checks redis.
Frontend: static Vite build served behind the SAME TLS proxy as API (same-origin, no CORS).
Prod host (memory): EC2 52.64.12.42, kyc.growfintec.com.au

## Quality
- **126 pytest files** in tests/ (+ conftest, fixtures) — real coverage
- **53 alembic migrations** + migrations/RUNBOOK.md + idempotent.py
- Frontend: vitest configured + 3 node validation scripts (rbac-lifecycle,
  providers-audit, review-approval-retention) + cypress for integration
- Sentry wired on the frontend

## ★ ENTIQ_PLATFORM_MAP.md — architecture doctrine ALREADY WRITTEN
Root of this repo. States "the one rule":
  ONE PostgreSQL DB. ONE backend API owns it. Every surface is a client of that API.
  Nothing else connects to the DB. Tenancy, permissions, step-up, consent gating and
  hash-chain integrity live in the API; surfaces render state and post actions.
Three deployment units:
  U1 Entiq API      = Growkyc_backend (KYC, onboarding, sharing/consent, money spine,
                      comms hub, CRM endpoints, trust, training, HO, audit, Celery)
  U2 Entiq Web App  = Growkyc-main, one React build / three audiences by route
                      (client onboarding+portal · /compliance/* incl /crm · HO console)
  U3 Entiq Mobile   = separate repo entiq-mobile (= entiq_app, Flutter)
Explicitly NOT separate deployments: **the CRM** ("a module of the API + a route of the
web app. Separating it would duplicate auth/tenancy/audit for zero gain — its power IS
the shared data"), the client flow vs workspace, the HO console.
Envs: dev SQLite/mock · staging AU+Postgres+Square sandbox+Didit test · prod no dev flags.

=> **This doc already answers the hub-vs-federate question for the CRM, and GrowKyc is
   nominated as the core.** Must validate that the other repos can live with it.

## Verdict on repo 1 (provisional — pending other repos)
STRONGEST CANDIDATE FOR THE CRM CORE. It already has: multi-tenancy with enforced
isolation, RBAC + permissions, audit hash-chains, a head-office control plane, a money
spine, a comms hub, a task/notes/segments/pipeline CRM seed, Celery, 126 tests,
53 migrations, and a written architecture doctrine.
Main liabilities: users.email global uniqueness blocks multi-tenant identity;
126-endpoint legacy compat surface; heavy Figma-prototype dead weight in the frontend;
tenant_id still nullable (phase 1 of 4 never completed).
