# Repo 2 — GrowAccounting  (github.com/abesaveni/GrowAccounting)

Local canonical clone: `D:\New folder (4)\GrowAccounting` (fast-forwarded to origin/main)
HEAD 578abdb (2026-07-08) — 115 commits.
NOTE: last commit 2026-07-08 vs GrowKyc 2026-08-26 => GrowAccounting is the less actively developed.

Other local copies (NOT canonical, ignore): `D:\Grow Accounting\*`, `D:\Download\GrowAccounting*`,
`D:\Download\GrowAccounting_SourceCode` (stale clone, 19 commits, May 2026).
Unrelated but noted: `C:\Users\USER\Complete-accounting-software` -> github.com/growgroups/Complete-accounting-software

## Shape
- `advisory-backend/`   Python FastAPI
- `advisory-frontend/`  **Next.js 16** (NOT the Vite SPA GrowKyc uses)
- `shared-contracts/`   JSON Schema contracts (intake-automation v1)
- `deploy/`, `nginx/`, 3 docker-compose files (production / staging / cicd)

## Backend stack — same family as GrowKyc but NEWER
FastAPI **0.128** (GrowKyc 0.104) · SQLAlchemy **2.0.45** (2.0.23) · Pydantic **2.12** (2.5)
pytest **9** (7.4) · Alembic 1.17 · slowapi · python-jose · passlib/bcrypt · openai
Postgres via **asyncpg** + psycopg2 · storage: boto3 (S3) **+ azure-storage-blob**
**No Celery / no Redis** — a single in-proc `app/workers/workpaper_worker.py`
`app/core/encryption.py` — field-level encryption (Xero tokens)

## Scale
- **468 endpoints** across 82 route modules
- 48 models · 68 services · **52 Alembic migrations** · 28 test files
- Frontend: 325 .tsx + 73 .ts, ~50 console routes

## IDENTITY & TENANCY — INCOMPATIBLE WITH GROWKYC (the #1 integration problem)
**GrowAccounting has NO multi-tenancy.** Verified: the only `tenant_id` anywhere is
**Xero's** organisation id (`xero_tenant_id`). It is a SINGLE-FIRM system.

Hierarchy is customer-shaped, not tenant-shaped:

    User (user_type = "staff" | "client")
      |- StaffRole  [admin, partner, manager, reviewer, senior_preparer,
      |              preparer, bookkeeper, client_coordinator, graduate]
      \- ClientUser --> ClientGroup --> AuthEntity (client_entities: Trust/Company/Individual, ABN/ACN)
                          |- ClientUserEntityAccess (per-entity ACL: read|write|admin)
                          \- ClientUserRole [director, business_owner, finance_manager,
                                             bookkeeper, payroll_contact, read_only, external_adviser]

Also: InviteToken (48h), PasswordResetCode (6-digit, sha256, 10min, 5 attempts),
UserSession (refresh tokens), RevokedToken (jti denylist).

### Clash matrix vs GrowKyc
| dimension      | GrowKyc                    | GrowAccounting            |
|----------------|----------------------------|---------------------------|
| tenancy        | multi-tenant (Tenant=firm) | **single-firm, none**     |
| PK type        | Integer                    | **UUID** (44/45 models)   |
| customer model | Client (+ entity profiles) | ClientGroup -> AuthEntity |
| user roles     | 8 compliance roles         | 9 accounting staff roles  |
| client access  | client_session + PIN       | ClientUser + entity ACL   |
| DB layout      | single public schema       | **11 Postgres schemas**   |
| async          | sync SQLAlchemy            | asyncpg                   |
| bg jobs        | Celery + Redis + beat      | in-proc worker            |
| frontend       | Vite SPA, React 18, Radix  | Next.js 16, React 19      |

=> These two cannot be merged by simply importing one into the other.

## Postgres multi-schema design (GOOD — reusable idea for the CRM)
Schemas in use: `auth`, `core`, `audit`, `ai`, `comms`, `intray`, `packs`, `portal`,
`review`, `rules`, `sources`.
A clean module boundary inside one database — directly applicable to a modular CRM and
arguably a better fit than GrowKyc's single flat public schema.

## Domain coverage (the real value here)
Australian tax/accounting engine:
BAS · CGT · Div7A · FBT · PSI · SMSF · Trust · Rental · Loss · Depreciation ·
GST health · tax_engine · tax_reconciliation · lodgment · journals · ledger ·
reconciliation · standard_workpaper · workpaper (+ workpaper_audit)

Practice ops:
clients · groups · company · tasks · notes · meetings · proposals · engagements ·
recurring_jobs · checklist · doc_checklist · document_requests · documents ·
document_folders · intray · activity · audit_log · analytics · insights · reports ·
search · custom_fields · notifications · actions · workflow_rules · automation

**Xero integration**: xero_import, xero_webhooks, xero_token_service (encrypted),
xero_request_queue, xero_health_monitor — the real, working Xero link.

**AI/agent layer (22 bot routers)** — the biggest differentiator:
advisory_opportunity · client_approval · client_response_interpreter ·
compliance_rules_engine · entity_structure_mapping · evidence_sufficiency ·
exception_triage · exception_handling_resolution · job_orchestrator ·
learning_governance · lodgment · lodgment_readiness · missing_information_hunter ·
ml_coding_model_by_client · post_lodgment · prior_year_intelligence · reconciliation ·
review_point_resolution · reviewer_simulation · smart_coding_recoding ·
self_healing_workflow_engine · tax_position_support
plus event_driven_agent_router, agents, ai_memory, agent_handoff, agent_profile, handoff_v1

## OVERLAPS with other planned CRM modules (must be resolved, not duplicated)
1. **Accounting UI duplicated**: GrowKyc's frontend carries 58 mock-only accounting
   components (workpapers, Xero, trial balance, BAS, Div7A, jobs kanban...).
   THIS repo is the real, wired implementation => GrowKyc's copy is dead weight; delete.
2. **E-Sign**: `routes/esignature.py` (6 endpoints) + `ESignatureRequest` model.
   Basic internal sign/decline only — not a full e-sign product. Compare with the real
   E-Sign repo before deciding which survives.
3. **Client Portal**: `routes/portal.py` + `client_portal.py` + PortalOnboardingSession /
   OnboardingEntity / OnboardingPerson / OnboardingDocument.
   Overlaps BOTH GrowKyc's onboarding (34 endpoints) AND the standalone ClientPortal repo.
   => THREE implementations of client onboarding. Biggest duplication in the estate.
4. **CRM surface**: clients, groups, tasks, notes, meetings, activity, search,
   notifications, proposals — overlaps GrowKyc's crm router (30 endpoints).

## Deployment
docker-compose.production.yml: postgres:16-alpine + `migrate` (alembic upgrade head) +
api + frontend, images tagged `${BUILD_SHA}`. nginx confs for app.growfintec.com.au +
staging.growfintec.com.au. deploy/: setup-server.sh, deploy.sh, start.sh, backup.sh,
restore.sh, DEPLOYMENT_CHECKLIST.md. Prod host (memory): EC2 13.236.185.56, seed_admin.
NOTE: postgres **16** here vs **15** in GrowKyc.

## Quality
- 28 test files (vs GrowKyc's 126) — thinner coverage on a comparable endpoint count
- Playwright e2e smoke + `lint:ctas` dead-CTA checker + `test:health` composite gate
- audit_middleware + `audit` schema + audit_log model
- correlation-id middleware, rate limiter, RBAC middleware, field-level encryption

## Verdict on repo 2 (provisional)
The accounting DOMAIN engine is strong and genuinely production-wired (Xero, tax engines,
workpapers, 22 AI agents). But its IDENTITY/TENANCY model is the opposite of GrowKyc's and
its stack is a generation ahead (FastAPI 0.128 / Next 16 / React 19 / UUID / async / multi-schema).

The central architectural decision of this programme is therefore:
  (a) absorb Accounting into the GrowKyc API (must add UUID/tenancy bridging, lose async,
      lose Next.js), or
  (b) keep Accounting as its own service behind a shared identity + CRM hub, or
  (c) build the CRM hub NEW on the better (Accounting) foundations, GrowKyc becomes a spoke.
Do not decide until all repos are read.
