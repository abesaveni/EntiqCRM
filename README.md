# EnTIQ

One platform for Australian accounting, tax and advisory practices: **one login, one client record, modules sold on top.**

- **Base plan** — Practice HQ + CRM. 15-day trial (card at signup, $0 charged), then **$99/month + GST**.
- **Modules** — Verify, Sign, Workpapers, Practice, Advisory, Start, Requests, Documents, Client, Academy, Lending and more, each a separate subscription.
- **Spec** — [`docs/BLUEPRINT_v1.1_2026-08-01.txt`](docs/BLUEPRINT_v1.1_2026-08-01.txt) (24 modules) and [`docs/architecture.html`](docs/architecture.html).

## Layout

```
apps/web            React 18 · Vite 6 · Tailwind 4 · Radix — the single shell, route-scoped per module
services/api        FastAPI · SQLAlchemy 2 · Alembic · Postgres — the platform spine:
                    identity (users + memberships), fail-closed tenancy, tenant_subscriptions,
                    require_module() gate, RBAC, hash-chained audit
packages/ui         59 shadcn/Radix components on the Entiq "enterprise paper" tokens (one copy, was four)
packages/modules    module registry — manifests.json is read by BOTH the frontend and the API;
                    catalogue, nav, permissions and entitlement checks derive from it
docs/               blueprint, architecture, per-repo audit notes
```

Module ports (Verify, Sign, Workpapers, …) land next. See `docs/architecture.html` §07 for milestones.

## Run

```bash
# 1. API (Python 3.12+; SQLite by default, Postgres via docker compose)
cd services/api
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Windows path shown
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000           # http://localhost:8000/docs
.venv/Scripts/python -m pytest                                              # 21 tests

# 2. Web (proxies /api → :8000)
pnpm install
pnpm dev            # http://localhost:5180
pnpm build && pnpm typecheck

# Optional: Postgres + Redis
docker compose up -d postgres redis      # then DATABASE_URL=postgresql+psycopg://entiq:entiq_dev_only@localhost:55432/entiq
```

Sign up at `/signup` (card captured, $0 charged, 15-day trial) — the practice, owner and base-bundle
subscriptions are created for real. **Practice HQ → Settings → Demo controls** walks the lifecycle
(trialing → active → past_due → suspended → cancelled) through `POST /dev/lifecycle` (non-production only).

**Platform (M4, live):** in-app notifications (bell) · email outbox with SMTP delivery (`EMAIL_DELIVERY_ENABLED`
gates real sending outside production) · documents with storage backends, ClamAV hook and retention holds ·
hash-chained billing ledger · **lifecycle job** (`python -m app.jobs.lifecycle`, run hourly): day-10/14 trial
reminders, trial → active (charge simulated until Stripe), past_due → suspended → cancelled → retained.
Practice HQ → Settings → Demo controls moves the clock and runs the job.

**CRM (M3, live):** clients · contacts · relationship graph · shared timeline · tasks · notes · pipeline ·
segments · duplicate detection · global search · **Xero / MYOB / CSV import** (`/clients/import`,
auto-detects the export format, de-duplicates on ABN then name). Every module writes to the same
timeline through `app.core.events.emit()`; the client record renders each subscribed module's panel
and an upsell tile for the rest.

### How a request is enforced

`authenticate → bind tenant to the Session → require_module() → require_permission() → handler → tenant-filtered ORM`

- The tenant comes from the JWT `tid` claim, never from a header or query parameter.
- Every tenant-scoped SELECT gets `WHERE tenant_id = …` injected at the ORM; a scoped query with no tenant **raises** (fail closed).
- Every scoped INSERT is stamped with the tenant; a row for another tenant is **refused**.
- `require_module()` returns `403 {error: module_not_subscribed, upsell: {…}}` — the shell renders "Add <Module>" from it.
- Suspended tenants are read-only (`423`). Cancelled/retained tenants get no access; their records are never deleted.

## Rules that keep it one codebase

1. Dependencies point **down** only: `apps → modules → core → packages`. A package never imports a module.
2. A module never owns users, tenants or the client record. It references `tenant_id`, `customer_id`, `entity_id`.
3. Every module declares itself in a manifest. No module appears in the UI that is not in the registry.
4. Entitlement is **data**: every module ships in every build; `tenant_subscriptions` decides what is reachable.
5. Records are never deleted on a billing event. Suspension restricts access; retention outlives the subscription.

## Secrets

Never committed. Copy `.env.example` → `.env.local` and fill in. Production uses the host's secret store.
