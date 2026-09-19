# Repo 7 — RequestIQ  (github.com/**growgroups**/RequestIQ)

NOTE: different GitHub org — `growgroups`, not `abesaveni`.
Cloned fresh to `D:\repos\RequestIQ` (no prior local clone; two stale ZIPs in D:\GrowKyc).
HEAD 76401f87 (2026-07-19) "Merge pull request #11 from growgroups/claude/brand-align-platform"
54 commits, first 2026-04-29.
Authors: **copilot-swe-agent[bot] 33** · growgroups 15 · Claude 6
=> Built largely by GitHub Copilot agents via PR workflow. Different provenance and
   process from every other repo (which are direct-to-main).

## What it is — ANSWERS THE "RequestIQ" QUESTION
**"A case-building workspace for commercial lending intake."**

NOT accounting, NOT KYC — a **different vertical: commercial lending**.

Flow: client uploads documents via scoped link -> classification + field extraction ->
checklist adapts (missing items auto-requested) -> policy validation -> staff review
**exceptions only** -> approved fields sync into the connected case record ->
"Ready for Credit" same day.

README is explicit that the AI is not real yet:
> "Document classification and field extraction are **deterministic heuristics** until
> the server-side OpenAI runtime is wired into those paths."

Self-declared **Phase 20 – Production Hardening and Investor-Grade Demo Pack**.
`demo/` holds an investor demo script, flow, synthetic case, positioning and FAQ.
=> This repo is positioned as an **investor/partner demo asset**, not (yet) a
   production revenue system. Confirm with the user.

## ★ Stack — the OUTLIER of the estate (7th variant, and a different paradigm)
| | |
|---|---|
| Backend | **TypeScript / Node on AWS Lambda** (no Python at all) |
| Data | **DynamoDB (NoSQL)** — not PostgreSQL |
| Storage | S3 (+ presigned URLs) · CloudFront |
| Messaging | SQS · SES (email) · **AppSync GraphQL** (live updates) |
| Auth | **AWS Cognito** (JWT via `jose`) + scoped client tokens |
| IaC | **CDK (9 files) + Terraform** |
| AI | Vercel AI SDK (`ai` v6) + `@ai-sdk/openai`, tiktoken |
| Doc processing | pdf-parse · mammoth (docx) · exceljs · **tesseract.js** (OCR) |
| Frontend | React + TS + **Vite + Tailwind** (43 .tsx, 70 .ts) |
| Tests | Jest — 14 backend test files |

Every other repo is FastAPI + SQLAlchemy + PostgreSQL, deployed as containers.
**This one shares no runtime, no database engine, no deployment model and no auth
provider with any of them.**

## Scale
- **29 Lambda handlers** (the API surface)
- **15 DynamoDB repositories**: intake · document · field · exception · requestItem ·
  reviewDecision · notification · queueJob · audit · adminSettings · externalCase (+config)
- 14 backend test files · CDK 9 + Terraform 1
- Frontend: 43 .tsx / 70 .ts, plus `src/agents`, `src/prompts`, `src/queues`

### Handlers (the product in one list)
startIntake · getIntake · approveIntake · createUploadUrl · completeUpload ·
processDocument · reprocessDocument · approveField · editApproveField · rejectField ·
resolveException · reviewQueue · reviewDecision · bulkReviewDecision ·
syncApprovedFields · createClientToken · rotateClientToken · revokeClientToken ·
listNotifications · sendNotification · updateNotificationSettings · sendReminder ·
runReminderCheck · queueWorker · queueMonitor · listDeadLetter · resolveDeadLetter ·
deadLetterRetry · adminSettings
=> Note the operational maturity: **dead-letter queue management, queue monitoring,
   bulk review, token rotation/revocation, reminder automation.**

## RBAC — the cleanest permission model in the estate
Roles: `admin` · `credit_manager` · `analyst` · `broker` · `client`
Fine-grained permissions, not role checks:
  intake:read/update/approve/upload/submit · field:approve/reject · exception:resolve ·
  document:download/upload · audit:read · token:create/revoke · notification:send/read ·
  admin:read/update
`admin: ['*']`. This permission vocabulary is a good template for the CRM.

## ★ Integration seam — same philosophy as EntiqStart
`repositories/externalCaseConfig.ts`: `EXTERNAL_CASE_PROVIDER = 'mock' | 'http'`,
with `EXTERNAL_CASE_API_URL` + `EXTERNAL_CASE_API_KEY`, timeout + retries.
Guard: **staging and production REFUSE to start unless provider = 'http'** (mock is
dev-only, enforced in config, not convention).
=> RequestIQ is agnostic about what the downstream "case record" system is.
   It can sync approved fields INTO the CRM with zero code change — just config.
   This mirrors EntiqStart's provider-driver pattern. Two independent repos converged
   on the same integration philosophy; that is the pattern the CRM should standardise.

## ⚠ FINDING — cross-tenant admin settings access (authenticated, admin-only)
`services/tenantContextService.ts::resolveTenantId()` derives the tenant from, in order:
  1. `?tenant=` **query string parameter**
  2. `X-Tenant-Id` **request header**
  3. host subdomain
  4. literal `'default'`
It is **never checked against the authenticated actor's own tenant**.
That value becomes the DynamoDB partition key: `PK = TENANT#${tenantId}`
(`adminSettingsRepository.ts:13-14`).

Accurate severity:
- `adminSettingsHandler` DOES authenticate (`authenticateStaffRequest`) and DOES enforce
  `admin:read` / `admin:update` permissions, and rate-limits.
- So this is **not** an unauthenticated hole.
- It IS a cross-tenant escalation for an authenticated admin: admin of tenant A can pass
  `?tenant=B` and read or overwrite tenant B's **admin settings, policy settings and
  agent settings** (which drive validation rules and AI behaviour).
- Blast radius is limited to settings — intake, document, field and exception
  repositories do not use `resolveTenantId`.
- Practical impact TODAY is low because the system effectively runs as `'default'`
  single-tenant.
=> Harmless now, a genuine landmine the moment this becomes multi-tenant inside a CRM.
   Fix: bind tenant to the authenticated principal (Cognito claim), never to input.

## Secrets check — CLEAN
`.env.staging` IS git-tracked but contains only placeholders
(`ap-southeast-2_your_staging_pool`, `api.staging.example.com`, empty API key). No leak.

## Relevance to the CRM programme
- **Different vertical (lending) and a different architecture paradigm.** It is the
  weakest candidate for absorption into a Postgres/FastAPI CRM monolith and the
  strongest candidate to remain a **federated satellite** integrated over its own
  external-case HTTP contract.
- Its RBAC permission vocabulary and its queue/DLQ operational tooling are worth
  copying into the CRM.
- Its Cognito dependency is the estate's **only** managed-identity implementation —
  relevant if the CRM ever adopts a real IdP (which the five-users-table problem argues
  strongly for).
- Adds a **sixth** independent identity store (Cognito user pool + client tokens).

## Verdict on repo 7
Keep separate. Integrate, do not absorb. Federate over the existing
`EXTERNAL_CASE_API_URL` seam and let the CRM be the case system of record it syncs into.
Confirm with the user whether this is a live product line or an investor demo, because
that changes how much integration effort it deserves.
