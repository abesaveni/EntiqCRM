# EnTIQ

One platform for Australian accounting, tax and advisory practices: **one login, one client record, modules sold on top.**

- **Base plan** — Practice HQ + CRM. 15-day trial (card at signup, $0 charged), then **$99/month + GST**.
- **Modules** — Verify, Sign, Workpapers, Practice, Advisory, Start, Requests, Documents, Client, Academy, Lending and more, each a separate subscription.
- **Spec** — [`docs/BLUEPRINT_v1.1_2026-08-01.txt`](docs/BLUEPRINT_v1.1_2026-08-01.txt) (24 modules) and [`docs/architecture.html`](docs/architecture.html).

## Layout

```
apps/web            React 18 · Vite 6 · Tailwind 4 · Radix — the single shell, route-scoped per module
packages/ui         59 shadcn/Radix components on the Entiq "enterprise paper" tokens (one copy, was four)
packages/modules    module registry — one manifest per module; catalogue, nav, permissions and entitlement checks derive from it
docs/               blueprint, architecture, per-repo audit notes
```

Backend (`services/`), the platform spine (identity · tenancy · subscriptions) and module ports land next, in this order:
frontend → backend → integrations → wiring. See `docs/architecture.html` §07 for milestones.

## Run

```bash
pnpm install
pnpm dev            # http://localhost:5180
pnpm build
pnpm typecheck
```

The frontend runs on mock data and a persisted mock session (`localStorage: entiq.session.v1`). Sign up at `/signup`,
or `/login` with any email to get a demo practice. **Practice HQ → Settings → Demo controls** simulates the
subscription lifecycle (trialing → active → past_due → suspended → cancelled).

## Rules that keep it one codebase

1. Dependencies point **down** only: `apps → modules → core → packages`. A package never imports a module.
2. A module never owns users, tenants or the client record. It references `tenant_id`, `customer_id`, `entity_id`.
3. Every module declares itself in a manifest. No module appears in the UI that is not in the registry.
4. Entitlement is **data**: every module ships in every build; `tenant_subscriptions` decides what is reachable.
5. Records are never deleted on a billing event. Suspension restricts access; retention outlives the subscription.

## Secrets

Never committed. Copy `.env.example` → `.env.local` and fill in. Production uses the host's secret store.
