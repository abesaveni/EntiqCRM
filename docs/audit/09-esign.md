# Repo 9 — Esign  (github.com/abesaveni/Esign)  "Grow E-Sign"

Local canonical clone: `D:\Grow Entiq Projects\Esign` — main @ ab40b0e (2026-09-18),
clean, in sync with origin. **101 commits**.
Prod (memory): esign.entiq.com.au, EC2 3.106.103.23, deploy via `update.sh`.

## What it is
**"A multi-tenant electronic signature and agreement platform"** — upload a document,
place fields, route to signers, verify identity, seal the executed PDF, and produce an
**independently verifiable evidence package**.

This is the REAL e-sign product. The other three implementations found earlier
(GrowAccounting `esignature.py` 6 eps, ClientPortal `signatures.py`, EntiqStart's
pluggable eSign driver) are stubs or drivers by comparison.

## Stack — aligns with GrowKyc's frontend, NEWER backend
| Part | Stack |
|---|---|
| API + worker | **Python 3.12, FastAPI, SQLAlchemy (async), Alembic** |
| Web | **React 18, TypeScript, Vite, Tailwind, Radix/shadcn** (same as GrowKyc + EntiqStart) |
| DB | **PostgreSQL 16** (SQLite local only) |
| Cache/rate-limit | Redis (optional single-instance, required multi-instance) |
| Storage | local filesystem or **S3** |
| Anti-virus | **ClamAV — required in production** |

README carries an unusually honest note: earlier revisions described a
Cognito/Lambda/API-Gateway/EventBridge/SQS/KMS architecture and a `server/` directory —
"None of that was ever built… That description has been removed rather than kept as
aspiration." Good documentation hygiene; treat this README as trustworthy.

## Scale
- **177 endpoints** across 27 routers
- **50+ tables** (single `app/models/domain.py`)
- 34 services · 7 Alembic migrations
- **70 backend test files** (2nd best in the estate after GrowKyc's 126)
- **225 frontend .tsx** (3rd largest frontend)
- `E2E_TEST_REPORT.md` (27 KB) · `loadtest/` directory

Routers: agreements · agreement_editing · ai_review · api_keys · audit · auth ·
authority · company_roles · dashboard · documents · email_content · emails · entity ·
identity · integrations · notifications · organizations · profile · search · settings ·
signer · staff · super_admin · template · users · verify · webhooks · workflow

## Domain model (50+ tables) — genuinely complete
Tenancy/identity: **Organization** · OrganizationSettings · **CompanyRole** · User ·
  Invitation · EmailVerificationToken · PasswordResetToken · RevokedToken ·
  **SuperAdminStaff** · **PlatformAuditEvent**
Signing core: Agreement · DocumentVersion · File · Signer · DocumentField ·
  SignerToken · SignerSession · **OTPChallenge** · **ConsentRecord** ·
  **CompletionCertificate** · **EvidencePackage** · **IdentityCheck** · AgreementExecution
Compliance/records: AuditEvent · **MonitoringCase** · **ComplianceAlert** ·
  **LegalHold** · **RetentionLog**
Entities: **Entity** · **EntityRelationship**
Automation: Workflow · WorkflowRun · WorkflowRunStep · Template · BulkSendJob ·
  BulkSendItem · ReminderSchedule · Form
Comms: Notification · UserNotification · EmailTemplate · EmailMessage
Platform: APIKey · WebhookEndpoint · WebhookDelivery · Integration · IntegrationSync ·
  IntegrationToken · **AccountingContact** · AIReview

## Tenancy — the THIRD multi-tenant system, and bound CORRECTLY
- `Organization` = tenant. `organization_id` appears **70 times** in domain.py.
- No central data-layer filter (per-query scoping, like ClientPortal) —
  BUT the org is taken from the **authenticated principal**, never from request input:
  `dependencies.py` builds `AuthPrincipal(organization_id=...)` from the user record or
  the API key record.
- Special `organization_id == "PLATFORM"` for super-admin/platform staff.
- Permission-based RBAC via `CompanyRole` + `require_permission(...)`, plus an
  `check_authority_bypass_permission` authority/delegation model.
=> Correct binding (contrast RequestIQ, which trusts a `?tenant=` query param).
=> Weaker than GrowKyc (no central fail-closed filter) but materially safer than
   ClientPortal (which fails OPEN on NULL firm ids).

Now THREE multi-tenant models in the estate, all incompatible:
  GrowKyc `Tenant` (int PK) · ClientPortal `Firm` (uuid PK) · Esign `Organization` (str id)

## Security depth — the strongest of any repo
`app/core/`: av_scanner (ClamAV) · distributed_lock · encryption · hashing · keys ·
rate_limit · **security_headers** · signer_session · tokens · error_reporting
Plus: MFA service, OTP challenges, consent records, identity checks, evidence packages,
completion certificates, legal holds, retention log, platform audit events.
This is the only repo with **anti-virus scanning as a production requirement** and a
**legal-hold / retention** implementation.

## ★★ INTEGRATIONS — the first REAL cross-system wiring in the estate
`backend/app/integrations/` = **`bas`**, **`client_portal`**, **`xero`**

`integrations/client_portal/adapter.py` is the most architecturally disciplined code
found across all nine repos. Its docstring states explicit guarantees:
- "Zero Client Portal / Stage 11 branching or models inside generic eSign core."
- Context types are "in-memory integration DTOs / reference contracts ONLY,
  NOT persistent database entities."
- "Financial figures (GST, PAYGW, taxable income, tax payable/refundable, general ledger
  balances) are strictly excluded from eSign metadata; only minimal opaque correlation
  is stored." — deliberate data minimisation across a module boundary
- Two-gate finalisation: Gate 1 client+workflow prerequisites (internal professional
  review approved + client approval), Gate 2 generic declaration gate
- **Reissue-safe** (stale agreement IDs rejected even if completed),
  **webhook-safe** (tenant + correlation validation, idempotent),
  **revocation-safe** (upstream revocation blocks finalisation even after signing)
- Covers Financial Statements, Tax Return Declarations, Trust Resolutions,
  Company Resolutions
- Refers to the consumer as "the external Client Portal / **CRM** application"

NOTE the shared vocabulary: this is labelled **"Stage 11"**, the same name as
EntiqStart's final lifecycle stage. Two repos already share a lifecycle vocabulary.

=> **This is the module-boundary pattern the whole CRM programme should adopt:
   a generic core + per-consumer adapters + explicit data-minimisation at the seam.**

## Deployment — mature
`docker-compose.prod.yml` services: redis · **clamav** · **migrate** · **preflight** ·
api · worker · web (+ volumes storage_data, clamav_db)
`deploy/`: Caddyfile · nginx.conf · bootstrap-host.sh · provision-aws.sh · update.sh
Memory note confirmed relevant: build ALL compose services or `migrate`/`preflight`
go stale.

## Repo hygiene — one issue
~25 scratch scripts ARE git-tracked at `backend/` root despite HEAD being
"Remove committed scratch scripts and captured command output":
  check_constraint.py · check_db.py · check_signers.py · check_un.py ·
  **clean_db.py · clean_db2.py · clean_db3.py** · click_test.py · db_dump.py ·
  db_dump_pg.py · fix_admin.py · get_real_token.py · get_url.py · insert_token.py ·
  list_tables.py · query_*.py · setup_test.py · test_backend_save*.py ·
  verify_sign_flow.py
`clean_db*.py` are destructive scripts sitting in the repo root of a production
signature platform. Also tracked: `test.db`, `database.sqlite`, `esign.db` (0 bytes),
`test.pdf`. Recommend a cleanup commit.

## Relevance to the CRM programme
- **The definitive E-Sign module.** Retire GrowAccounting's `esignature.py` and
  ClientPortal's `signatures.py`; point EntiqStart's `ESIGN_API_BASE_URL` generic driver
  at this service.
- It is already the integration hub for `client_portal` + `xero` + `bas`, so the
  seam into accounting/portal exists and is tested.
- Its **generic-core + consumer-adapter** pattern, and EntiqStart's + RequestIQ's
  **provider-driver** pattern, are the same idea from two directions. Together they are
  the strongest evidence for a FEDERATED CRM with governed contracts rather than a
  merged monolith.
- Its frontend stack (React 18 + Vite + Tailwind + Radix/shadcn) matches GrowKyc and
  EntiqStart — three of nine repos already align on the FE, which is the natural
  standard for a unified CRM shell.

## Verdict on repo 9
Keep as its own service. Strongest security posture in the estate, best module-boundary
discipline, real multi-tenancy bound to the principal, 70 tests, mature deploy.
Fix the tracked scratch scripts. Adopt its adapter pattern estate-wide.
