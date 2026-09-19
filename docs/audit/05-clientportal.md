# Repo 5 — ClientPortal  (github.com/abesaveni/ClientPortal)

Local canonical clone: `D:\repos\ClientPortal` — fast-forwarded b3f50cd -> **4d33a3c** (2026-09-18).
Only 7+1 commits (squashed history). Clean tree.
NOTE: newest commit is by **Uday <udayyy556@gmail.com>**, message just "uday" —
a second developer is active in this repo. It landed a schema change
(`w01_rekey_financial_data_to_entity`) touching 24 endpoint files + a new migration.
=> Multi-developer repo with weak commit hygiene; coordinate before any CRM refactor.

## What it is (from its own README)
**"The client-facing operating layer of the Grow Accounting Platform"** —
"your CFO, tax agent and business advisor in your pocket."
Explicitly the companion surface to **GrowAccounting** (repo 2).

Answers four questions for an AU business owner:
1. cash position + event-based forecasts (30/60/90/180/365-day and 3-year)
2. risk-classified alerts with provenance and freshness
3. approved recommendations -> owned actions
4. KPIs vs targets/benchmarks + immutable monthly packs
Grow staff work the same data from staff surfaces: review queues, approval gates,
exception management, advisory prep.

## Stack
Backend: FastAPI **0.141.1** · SQLAlchemy **2.0.53** · Pydantic 2.13 · Alembic 1.20 ·
psycopg2 · **Celery + Redis** · cryptography/Fernet (data at rest) ·
**azure-storage-blob + azure-identity** (prod storage) · reportlab · openpyxl · httpx ·
requests (Xero)
**+ Flask 3.1.3 embedded** — `app.aml.service` exposes a standalone WSGI app inside a
FastAPI project. Mixed-framework wart.
Frontend: React 18 + TS + Vite, **cookie-authenticated** SPA,
**MUI 7 AND Radix/shadcn together** — two component libraries in one app.

⚠ `bcrypt==3.2.2` pinned (passlib 1.7.4 incompatible with bcrypt >= 4). Old crypto lib
held back by an unmaintained dependency — same trap GrowKyc has (passlib+bcrypt 4.1.1).

## Scale
- **205 endpoints** (README says 216 routes) across 37 endpoint modules
- **40 models** / README says **67 tables** · 43 services · 28 migrations
- **43 test files** / README claims **166 backend regression tests**
- frontend/src: 122 files
- root `src/` holds ONE stray tracked PDF — ignore (not a second frontend)

## Tenancy — the SECOND multi-tenant system, but enforced WEAKLY
`Firm` model = "groups users and client profiles under a single multi-tenant practice":
  name · **slug** · timezone (Australia/Sydney) · status · **brand_tokens JSONB
  (white-labelling)** · row_version (optimistic locking) · deleted_at (soft delete)
Hierarchy: Firm -> User / ClientProfile -> ClientGroup -> **Entity** -> Membership
Plus: consent_entitlement, portal_session, refresh_token, permission/role/user_role

### ★ ISOLATION IS FAIL-OPEN (live security weakness)
There is **no central tenant filter** — no `do_orm_execute` / `with_loader_criteria` /
`before_flush` guard anywhere (verified). Scoping is per-endpoint via `_assert_same_firm`.
That helper denies **only when BOTH firm ids are known and differ**. `users.firm_id` is
**nullable and not backfilled**, and `STRICT_FIRM_SCOPING` defaults to **false**
(`backend/.env.example:31`, `core/config.py:52`). When either side is NULL it
**logs a warning and ALLOWS access**.
=> Today, a staff user can reach another firm's entity whenever firm_id is unset.
The author documented this and gated it behind a backfill; the test
`test_security_def_p0.py` only covers the strict path.
**This must be closed before this data joins a shared CRM.** Contrast GrowKyc, which
enforces isolation centrally in the data layer and fails closed.

## Prior memory note — now RESOLVED/UPDATED
Memory recorded "5 P0 security findings" + "21 seeded-Postgres test failures".
HEAD-1 commit b3f50cd is literally *"fix: close P0/P1 security defects, restore a
verifiable build"*, and `backend/tests/test_security_def_p0.py` exists.
=> The P0s were addressed. The fail-open firm scoping above is a REMAINING, known,
flag-gated gap, not one of the closed P0s. (Tests not re-run here — needs a seeded
Postgres; verify separately.)

## Domain (37 endpoint modules)
Financial spine: financials · consolidation (+FX) · cash_flow · forecasting · scenarios ·
reserves · calculations · benchmarks (+admin) · period_control · snapshots · reports
Advisory: goals · client_journey · client_intent · portal_orchestrator · meetings ·
governance (AI governance) · industries · jobs
Ops: clients · users · tasks · documents · notifications · chats · signatures ·
onboarding · settings · compliance · **aml** · webhooks_admin · dashboard
AI: **agents/** + **bots/** packages + `services/ai_orchestrator` ("Ask Grow")

## ★ OVERLAP MAP — this repo collides with almost everything
| capability        | also in                                    |
|-------------------|--------------------------------------------|
| **Xero sync**     | GrowAccounting (`xero_*` suite) — **2nd Xero integration** |
| client onboarding | GrowKyc (34 eps) + GrowAccounting (portal) — **now 4 implementations** |
| e-signatures      | GrowAccounting (esignature) + E-Sign repo   |
| AML/compliance    | GrowKyc (~200 AML/AUSTRAC eps) — **2nd AML impl** |
| tasks/notes/meetings/notifications/documents | GrowKyc crm + GrowAccounting |
| AI agents/bots    | GrowAccounting (22 bot routers)             |
| multi-tenancy     | GrowKyc (Tenant) — **2nd, incompatible, tenancy model** |
| client portal     | GrowAccounting `portal.py` + `client_portal.py` |

## Identity model — a FOURTH variant
UUID PKs · cookie auth (+ CSRF middleware) · refresh_token + portal_session tables ·
role / permission / user_role · `is_superuser` · STAFF_BYPASS_ROLES ·
firm_id nullable on User and ClientProfile.
Four systems now = four `users` tables, four RBAC schemes, two tenancy models
(GrowKyc `Tenant` int-keyed, ClientPortal `Firm` uuid-keyed), three PK conventions.

## Quality
- ARCHITECTURE.md is genuinely good: purpose, roles, data layer, 7 named flows,
  API surface map, verification posture
- CSRF middleware, Fernet at-rest encryption, idempotency, feature flags, MFA
- 166 claimed regression tests across auth/MFA/sessions, cash engine, forecasting,
  onboarding gates, period control, consolidation FX, payroll, AI governance, entitlements
- Known open follow-ons documented in IMPLEMENTATION_REPORT.md §4 (entity-keyed
  financials migration, payroll scopes, Azure OCR, communication record FE, digests)

## Relevance to the CRM programme
- This is the **client-facing half of the accounting product**, not a generic portal.
  It and GrowAccounting are two halves of ONE system that were built as two codebases
  with two identity models and two Xero integrations.
- It is the strongest candidate to *donate* the client-facing UX and the financial/
  advisory domain to the CRM — but it cannot bring its tenancy model, which is weaker
  than GrowKyc's.
- Highest-risk repo to touch: second developer active, squashed history, fail-open
  scoping, mixed frameworks, dual component libraries.

## Actions this repo forces into the plan
1. Close the fail-open firm scoping (backfill users.firm_id, enable STRICT_FIRM_SCOPING,
   or better: adopt GrowKyc's central data-layer filter).
2. Decide ONE Xero integration (this one vs GrowAccounting's).
3. Decide ONE client-onboarding implementation (now four).
4. Decide ONE AML implementation (this vs GrowKyc's AUSTRAC suite).
5. Agree commit/branch hygiene with the second developer before refactoring.
