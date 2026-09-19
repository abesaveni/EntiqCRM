# Repo 6 — EntiqStart  (github.com/abesaveni/EntiqStart)

Cloned fresh to `D:\repos\EntiqStart` (no prior local copy existed).
HEAD **d3ce586 (2026-09-19 — TODAY)** "Make the app realtime for all users and run
connectors over real HTTP". Only **3 commits**, sole author abesaveni.
=> The NEWEST and most actively-moving repo in the estate.

## What it is — ANSWERS THE "Start" QUESTION
**"EnTIQ Start — Client Onboarding Orchestrator & Engagement Gateway"**

Takes a prospect from first contact to a signed, compliance-checked, activated
engagement through a strictly sequential **11-stage lifecycle**, then hands the finished
client off to downstream practice systems.

Its own README states the architectural position explicitly:
> "It is built for Australian accounting, tax and advisory firms, and is **one module of
> a larger EnTIQ suite: Start owns onboarding, while identity, AML, eSign, billing and
> practice management are separate systems it integrates with.**"

### The 11-stage lifecycle (sequential invariant enforced SERVER-side in stage_service.py)
1 Invitation (magic link / QR) -> 2 Entity Details (ABN/ACN verified, structure, tax
residency) -> 3 Questionnaire -> 4 Document Requests (uploaded AND advisor-verified) ->
5 Related Parties (directors, trustees, beneficial owners) -> 6 Service Selection ->
7 Proposal (fee + commercial terms accepted) -> 8 Engagement Prep (LoE compiled+signed)
-> 9 External Checks (**all four gates: KYC, AML, eSign, payment mandate**) ->
10 Internal Acceptance -> 11 Client Activated
Stage n cannot complete until 1..n-1 are complete. Not a UI convention — server-enforced.

## Stack
FastAPI 0.110+ · SQLAlchemy 2 · Alembic · PostgreSQL 16 (SQLite local)
React 18 · TypeScript 5.5 · **Vite 6 · Tailwind 4 · Radix UI** (same FE stack as GrowKyc)
SSE realtime (`/events/stream`) with replay + backpressure via in-process event bus
Deploy: Dockerfile + docker-compose + nginx.conf

## Scale
- **112 endpoints** across 19 routers
- **22 tables** in a single `models.py`
- 7 test files (README badge claims **135 tests passing**)
- frontend: 78 .tsx

Routers: activity · alerts · api_keys · auth · billing · cases · clients · dashboard ·
documents · engagements · events · integrations · invitations · public_onboarding ·
qr_codes · services · templates · workflows

Models: User · OnboardingCase · OnboardingStage · QuestionnaireResponse · ReviewAlert ·
Invitation · ClientEntity · Engagement · ActivityEvent · Template · ApiKey ·
BillingSchedule · Invoice · Payment · ServiceItem · FeeItem · StaffMember ·
WorkflowProcess · SystemSetting · QRCode · CaseDocument · OnboardingSession

## ★★ THE PROVIDER-DRIVER ARCHITECTURE — the most reusable thing in the whole estate
`backend/app/integrations/` — every external capability is an abstract provider with
(a) a live HTTP driver and (b) a **simulation driver** used when no credentials exist.

| Capability        | Live drivers                        | Config |
|-------------------|-------------------------------------|--------|
| Identity (KYC)    | didit, frankieone, **generic**      | KYC_API_BASE_URL + KYC_API_KEY |
| AML / PEP         | complyadvantage, **generic**        | AML_API_BASE_URL + AML_API_KEY |
| eSign             | docusign, **generic**               | ESIGN_API_BASE_URL + ESIGN_API_KEY |
| Payment mandate   | stripe, gocardless, **generic**     | PAYMENTS_API_KEY |
| Business register | abr (free, government)              | ABR_API_GUID |
| Accounting ledger | xero                                | ACCOUNTING_API_KEY + ACCOUNTING_TENANT_ID |
| Practice handover | signed webhook POST                 | HANDOVER_WEBHOOK_URL |

`CheckResult` is the normalised contract: status · provider · **simulated** · reference ·
detail · raw · checked_at.
**`simulated: true` propagates everywhere** — stage metadata, API response, Integrations
screen, Stage 9 gate panel, Stage 11 handover payload. README is blunt:
> "A simulated check satisfies the Stage 9 gate but is not evidence of anything.
> It does not meet AML/CTF obligations."
Live state queryable: `GET /api/v1/integrations/health` with LIVE/SIMULATED badges.

### ★ WHY THIS MATTERS FOR THE CRM
The `generic` driver for KYC / AML / eSign means **GrowKyc can BE the KYC and AML
provider** and the E-Sign repo can BE the eSign provider — just point the base URLs at
them. No rewrite. This is the cleanest integration seam discovered so far, and it was
designed for exactly the problem this programme is trying to solve.

## Stage 11 handover — a real downstream contract
`integrations/handover.py` emits the complete onboarding record to the production
practice system as a **signed HTTP POST**: HMAC-SHA256 over `"<timestamp>.<body>"`,
headers `X-EnTIQ-Signature` / `X-EnTIQ-Timestamp` (origin verification + replay
rejection). `build_handover_payload()` is deliberately separated from dispatch so it can
be previewed in the UI and asserted in tests.
=> A ready-made, secure "onboarding complete -> create the client downstream" event.
   This is the integration point into whatever becomes the CRM system of record.

## Tenancy — NONE (single-tenant)
`tenant`/`firm_id` appear zero times in models.py. A **FIFTH** `User` table
(role default "Partner"), plus a separate `StaffMember` (role default "Accountant") —
two people-tables inside this one repo.
Auth: password users + **ApiKey** table + `X-API-Key` master key for machine access.

## Security
`security.py`: rate limiting · **webhook HMAC** · upload validation
`routers/documents.py`: per-case authorisation on upload/retrieve
Public surface: `public_onboarding.py` + `invitations.py` + `qr_codes.py` (magic links)

## Documentation
`ENTIQ_START_11_STAGE_LIFECYCLE_AUDIT.md` (33 KB) + an HTML render — a full audit of the
lifecycle. `docs/`, `guidelines/`, `ATTRIBUTIONS.md`. README is 19 KB and unusually
honest (the "what is real and what is simulated" section leads).

## ★ OVERLAP — the onboarding count is now FIVE
GrowKyc onboarding (34 eps) · GrowAccounting portal · ClientPortal onboarding ·
GrowAccounting client_portal · **EntiqStart (a purpose-built 11-stage engine)**
Of these, **EntiqStart is the only one designed as an orchestrator rather than an
in-app feature**, and the only one with a sequential server-enforced invariant.

Also duplicated here: billing/Invoice/Payment/FeeItem/ServiceItem (GrowKyc money spine,
GrowAccounting, ClientPortal), documents, activity, alerts, templates, clients, dashboard.

## Verdict on repo 6
Small (112 endpoints, 22 tables) but **architecturally the most important repo after
GrowKyc**. It is the only codebase in the estate that was designed from the start as a
*module of a suite* that *integrates with* sibling systems rather than absorbing them.

Two things to lift into the CRM plan regardless of which consolidation path is chosen:
1. **The provider-driver + simulation-flag pattern** (`integrations/base.py`) as the
   standard way every CRM module talks to every other module and to vendors.
2. **The signed-webhook handover** as the standard inter-module event contract.

Risk: only 3 commits and moving daily — it is under active construction right now, so
anything built against it should assume churn. Confirm with the user before treating it
as stable.
