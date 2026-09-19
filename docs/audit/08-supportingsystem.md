# Repo 8 — EntiqSupportingSystem  (github.com/abesaveni/EntiqSupportingSystem)

Cloned fresh to `D:\repos\EntiqSupportingSystem`.
HEAD 3cfe52e (2026-08-14) "feat: SMTP email, notification bell toggle, sounds, live chat
queue system". Only **4 commits**, first 2026-08-07. Sole author **"Entiq Support Dev"**
(a third distinct contributor identity in the estate).

## What it is — THE "supporting system" FROM THE USER'S BRIEF
**"SupportHub CRM — an enterprise-grade Omnichannel Customer Support CRM built for
Entiq Software. Comparable to Salesforce Service Cloud, Zendesk, and Freshdesk."**

Two halves:
1. **Agent workspace**: live chat (Socket.IO), ticketing with SLA tracking, unified
   email inbox, **Customer 360**, analytics/KPI dashboards, employee management
   (Manager/Employee), notifications, settings (SLA policies, departments, org prefs)
2. **Embeddable customer widget** — one `<script>` tag on any site gives visitors
   live chat -> online agent · "Email us" -> CRM inbox · "Raise a ticket" -> tracked ticket
   `widget/`: widget-loader.js + widget-iframe.html + entiq-demo.html

## ⚠ NAMING COLLISION — it calls ITSELF a CRM
This repo is "SupportHub **CRM**" with a "**Customer 360**". GrowKyc's crm router also
has `/clients/{id}/360`. When the user says "centralized CRM", this repo is a *support*
CRM — a different thing from the client/practice CRM the programme is aiming at.
Terminology must be settled in the plan or the two will keep being confused.

## Stack — 8th variant, 2nd Node backend (but unlike RequestIQ's)
| Layer | Tech |
|---|---|
| Frontend | React 18 · TypeScript · Vite · **Tailwind v4** · TanStack Query |
| Backend | **Node.js + Express 4 + TypeScript** (NOT Lambda) |
| ORM/DB | **Prisma 5** · SQLite (dev) / PostgreSQL (prod) |
| Realtime | **Socket.IO 4** (NOT SSE, NOT AppSync) |
| Auth | jsonwebtoken + bcryptjs |
| Email | nodemailer (SMTP) |
| Hardening | express-rate-limit, express-validator |
| Monorepo | pnpm workspaces (`packages/{backend,frontend,shared}`) |

Realtime is now a 3-way split across the estate: SSE (EntiqStart) ·
AppSync/WebSocket (RequestIQ) · Socket.IO (this).

## Scale — the smallest backend in the estate
- **93 endpoints** across 12 modules
- **19 Prisma models**
- frontend: 27 .tsx
- **No test directory found** — the only repo with no tests at all

Modules (endpoints): chats 13 · tickets 13 · **portal 10** · settings 9 · analytics 8 ·
emails 8 · users 8 · auth 7 · customers 6 · departments 5 · notifications 4 · reports 2

Models: Organization · Department · User · UserPermission · Customer · CustomerTag ·
CustomerActivity · Ticket · TicketTag · TicketComment · InternalNote · Attachment ·
Chat · ChatMessage · Email · Notification · SLAPolicy · EmailTemplate · AuditLog

## Tenancy — NONE (`Organization` is a settings singleton, not a tenant)
`Organization` holds name/email/phone/website/logo/timezone/language/dateFormat/
**primaryColor**/darkMode — i.e. branding + preferences for ONE org (Entiq itself).
**Zero models carry `organizationId`** (verified: 0 occurrences).
=> Single-tenant. Cannot serve multiple practices as-is.

## Identity — the SEVENTH user store
`User`: cuid PK · email unique · passwordHash (bcryptjs) · role String default
"EMPLOYEE" (Manager/Employee) · status · departmentId · `UserPermission[]`
Plus `Customer` — an **eighth** customer/contact table in the estate.
Nothing links to GrowKyc, GrowAccounting, Training, ClientPortal, Start or RequestIQ.

## Public widget surface — CHECKED, and it is sound
`portal.routes.ts` is deliberately unauthenticated (it serves the embedded widget):
  GET /widget-config · POST /chat/start · POST /chat/:chatId/message ·
  GET /chat/:chatId/messages · POST /email · POST /ticket

I specifically checked whether chat history is exposed by ID enumeration. It is not:
`getWidgetMessages` loads the chat, parses `chat.metadata`, and **rejects with 403
unless `metadata.sessionToken` matches the caller's `?sessionToken=`**. IDs are cuid.
Minor nit only: the token comparison is a plain `!==` (non-constant-time) — negligible
for a random cuid-length secret, worth tightening if this goes multi-tenant.
=> No finding. Good design for an embeddable widget.

## Repo hygiene
- `fahhhhh.mp3` (31 KB) committed at repo root — a notification sound with a joke
  filename. Cosmetic, but it is in the product repo; rename/move under assets.
- `.env.example` present, no tracked secrets (clean).
- **No tests** — the only repo in the estate with none.

## Relevance to the CRM programme
- This is a **genuinely complete support product** for its size: SLA policies, email
  templates, internal notes, audit log, customer activity timeline, department routing,
  agent presence/status, notification system, and an embeddable widget.
- **No other repo has ticketing, live chat, or an email inbox.** Zero functional overlap
  with the other seven on its core (support) domain.
- Overlaps only on the generic edges: Customer/Contact, Notification, AuditLog,
  Attachment, Analytics — the same generic entities every repo re-implements.
- It is the natural **Support module** of the target CRM, and one of the two cheapest
  to re-home (93 endpoints, 19 models, no tests to port).
- Its embeddable widget is a real asset: it can be dropped onto ANY Entiq surface
  (KYC portal, Academy, client portal, marketing site) to funnel support into one queue.

## Risks
- No tests + 4 commits + a single unknown contributor = low confidence in robustness.
- Prisma is an 8th ORM/data-access choice; if the CRM standardises on SQLAlchemy this
  module either keeps Prisma behind a service boundary or gets rewritten.
- Single-tenant `Organization` singleton must become a real tenant if support is offered
  to multiple practices.

## Verdict on repo 8
Keep the product, fold it in as the **Support module**. Cheapest meaningful win in the
estate: it fills a genuine gap, duplicates almost nothing, and its widget gives the CRM
an immediate presence on every other Entiq surface.
