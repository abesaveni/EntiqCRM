# EnTIQ CRM — build status

One codebase, one login, per-module subscriptions. Base plan (Practice HQ + CRM) is **$99/month + GST**
with a **15-day trial**: the card is captured at signup, **$0 is charged**, and the first charge of
**$108.90** falls on day 16. Every other module is a separate subscription, priced from its manifest.

## Modules (blueprint v1.1, 2026-08-01)

| # | Module | Status | Ported from | What it does here |
|---|--------|--------|-------------|-------------------|
| 01 | Practice HQ | **built** | GrowKyc (tenant, plans) | Subscriptions, users, access, integrations, settings, support |
| 02 | Control Centre | internal | GrowKyc (head office) | EnTIQ operators: support queue across practices |
| 03 | Start | **built** | EntiqStart | 11-stage onboarding, server-enforced; prospect link + practice workspace |
| 04 | Verify | **built** | GrowKyc | Identity, screening, beneficial ownership, risk rating, review cycle |
| 05 | Sign | **built** | Esign | Agreements, tokened signing, hash-chained evidence, sealed certificate |
| 06 | Requests | **built** | RequestIQ, GrowAccounting | Adaptive checklists, client uploads, exceptions-only review |
| 07 | Documents | **built** | GrowKyc, Esign, RequestIQ | Folders, tags, text index, search, retention policies |
| 08 | Workpapers | **built** | GrowAccounting | Ledger sync, variance + evidence rules, review, sign-off seal, lodgement |
| 09 | Practice | **built** | GrowAccounting | Jobs, recurring compliance work, time, deadlines, team load |
| 10 | Advisory | **built** | ClientPortal, GrowAccounting | Snapshots, KPIs, alerts, meetings, owned actions |
| 11 | Capital | planned | — | Blueprint only; no source code exists |
| 12 | Credit | planned | — | Blueprint only |
| 13 | Settle | planned | — | Blueprint only |
| 14 | Client portal | **built** | ClientPortal, entiq-app | Passwordless portal: documents, requests, agreements, jobs, messages |
| 15 | Academy | **built** | EntiqTraining | Courses, quizzes, certificates, role-based compliance requirements |
| 16 | CRM | **built** | GrowKyc, GrowAccounting | Clients, contacts, relationships, pipeline, tasks, timeline, import |
| 17 | Marketing | planned | — | Blueprint only |
| 18 | Projects | planned | — | Blueprint only |
| 19 | Billing | **built** | GrowKyc, EntiqStart | The practice invoicing its clients: invoices, payments, recurring fees, aged debt |
| 20 | Lending | **built** | RequestIQ | Finance pipeline, serviceability, conditions, settlement |
| 21 | Loan Manager | planned | — | Blueprint only |
| 22 | Funds | planned | — | Blueprint only |
| 23 | Trust | planned | — | Blueprint only |
| 24 | Associations | planned | — | Blueprint only |

**14 built · 1 internal · 9 planned.** The nine planned modules have no source code in any of the nine
repositories; they appear in the catalogue with their blueprint pricing and outcome so a practice can
see what is coming, and the module route renders their manifest rather than a fake screen.

## How the modules meet

Nothing is duplicated between modules; each one reads the others through the spine.

- **Start → everything.** Stage 8 sends the engagement letter through **Sign**. Stage 9's gates read
  **Verify** (identity, screening), **Sign** (completed agreement) and the recorded mandate — no second
  implementation of any of them. Stage 11 activates the CRM client and emits `onboarding.activated`,
  which **Practice** turns into the onboarding job and recurring work, and **Billing** turns into fee
  schedules from the accepted proposal.
- **Requests → Lending.** A completed lending pack advances the application and re-scores readiness.
- **Workpapers → Advisory.** A snapshot folds a synced trial balance into headline figures and KPIs.
- **Workpapers → Practice.** Signing off a pack completes its linked job.
- **Advisory → Client portal / CRM.** Publishing a meeting posts the summary to the client; a
  practice-owned action is mirrored as a CRM task.
- **Everything → Documents.** Every upload path (staff, prospect, client, request) goes through
  `services/document_service`, so scanning, hashing, the timeline entry and the search index are identical.
- **Everything → CRM.** One client record carries the pipeline stage, the risk rating, the timeline and
  the module panels.

## Simulation, and why nothing lies

No Stripe, Xero or ABR credentials exist in the estate yet, and Didit/OpenSanctions keys exist but are
not used in tests. Each of those has the same shape: a **live driver** and a **simulation driver**, chosen
from configuration, and a `simulated` flag that travels with every record it produces — into the pack,
the snapshot, the onboarding gate, the billing ledger and the UI. A simulated result never reads as a
real check, charge or ledger. `Practice HQ → Integration hub` reports exactly what is configured on the
server it is talking to, and names the environment variables still missing.

## Verification

- **75 backend tests** (`services/api`), covering tenancy isolation, entitlements, the lifecycle job,
  and every module's happy path, guard rails and cross-module interlink.
- **Full cross-module smoke** against a running API: signup → 12 module subscriptions → onboarding
  through all 11 stages with real gates → Practice/Billing interlinks → risk assessment → ledger sync,
  workpaper rules and sign-off → advisory snapshot, meeting and publication → portal login, upload and
  message → request pack filled and reviewed → lending to settlement → academy quiz and certificate →
  document filing, search and retention → invoice and payment → support ticket → integration hub.
- `tsc --noEmit` clean, production Vite build clean.

## What production still needs

| Missing | Blocks | Where it goes |
|---------|--------|---------------|
| `STRIPE_SECRET_KEY` + `BILLING_MODE=stripe` | Real charges on day 16 | `.env` — the charge path, dunning, ledger and emails are already written |
| `XERO_CLIENT_ID` / `XERO_CLIENT_SECRET` | Live ledger sync | `.env` — OAuth URL and TrialBalance parsing already written |
| `AWS_S3_BUCKET` + `STORAGE_BACKEND=s3` | Durable file storage | `.env` |
| `CLAMAV_HOST` | Upload scanning (production refuses uploads without it) | `.env` |
| `DIDIT_API_KEY` / `OPENSANCTIONS_API_KEY` in the deployed env | Live identity and screening | present in `.env.local`, not yet in a deployed environment |
| A domain | Public links (signing, onboarding, requests, portal) | `APP_PUBLIC_URL` |
