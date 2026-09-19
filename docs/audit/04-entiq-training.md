# Repo 4 — EntiqTraining  (github.com/abesaveni/EntiqTraining)

Local canonical clone: `D:\Entiq Training`
HEAD 07dd3c0 (2026-08-28) "Rebrand the last two notification-template strings to Entiq"
Branch: **fix/audit-remediation** (== remote HEAD). Clean tree. 32 commits.
Prod (memory): academy.entiq.com.au, co-hosted with E-Sign on EC2 3.106.103.23.

## What it is
**"Staff Learning Portal"** — an internal compliance-training LMS.
Package name literally `staff-learning-portal`; DB name `grow_compliance`.
NOT a customer-facing academy. This matters: it is an INTERNAL tool, so its natural
place in the CRM is staff competency/compliance evidence, not a client-facing product.

## Stack — the NEWEST of the estate (4th distinct variant)
Backend: FastAPI **0.141.1** · SQLAlchemy **2.0.51** · **psycopg3** · Pydantic 2.13 ·
Alembic 1.18 · python-jose · bcrypt 5 · slowapi · gunicorn 23 · openai 2.52 · boto3 ·
tenacity
Frontend: **React 19 + Vite 8**, plain **JavaScript (.jsx, not TypeScript)**,
react-router 7, recharts 3, axios, jspdf + html2canvas + qrcode (certificate PDFs),
react-player (lesson video). No Tailwind, no component library.
DB: **postgres:17**

### Version drift across the estate is now severe
| repo           | FastAPI | Pydantic | Postgres | Frontend            |
|----------------|---------|----------|----------|---------------------|
| GrowKyc        | 0.104   | 2.5      | 15       | Vite 6 / React 18 TS|
| GrowAccounting | 0.128   | 2.12     | 16       | Next 16 / React 19  |
| EntiqTraining  | 0.141   | 2.13     | 17       | Vite 8 / React 19 JS|

## Scale
- **112 endpoints** across 18 routers
- **21 tables**, all in ONE `models.py` file
- 5 Alembic migrations · 13 test files · 75 .jsx + 26 .js frontend files

## Domain model (21 tables)
RBAC: Role · Permission · RolePermission · UserRole  (a full permission layer)
Identity: User · RevokedToken
Learning: Course · Lesson · Quiz · QuizAttempt · Enrollment · Certificate ·
          SimulatorAttempt
Compliance: ComplianceRecord · RiskAssessment
Engagement: CommunityPost · PostComment · Notification · NudgeLog · Activity
Audit: AuditLog (+ an `AuditMixin` applied to EVERY model)

Routers: ai_tutor · audit_logs · auth · certificates · community · compliance ·
courses · enrollments · lessons · notifications · permissions · quizzes · reports ·
risk_assessments · roles · users

## Identity model — a THIRD incompatible variant
- **UUID** PKs (matches GrowAccounting, NOT GrowKyc's Integer)
- `email` **globally unique**
- **NO tenancy** — `tenant_id` appears zero times
- `role_name` (Administrator | User) + `designation` (job title: Staff/Manager/Director/
  Compliance Officer/Senior Accountant) + `department`
- Comment in-model: *"designation is a label only; all Users have identical access"*
  => a FLAT access model despite the Role/Permission tables existing
- `legacy_id` (String, unique, NOT NULL) — carries an id from a predecessor system
- Denormalised JSONB on User: `enrolled_courses`, `earned_certificates`,
  plus counters `progress`, `courses_done`, `certificates_count`
  => duplicated state that will drift; a CRM reading these directly would read stale data
- Good security: activation token hash + expiry, failed_login_attempts, locked_until,
  `tokens_valid_from` (password change/reset/disable genuinely ends live sessions)

## Integration surface: NONE
Verified — no reference anywhere to GrowKyc, growfintec, entiq.com.au, or any sibling
system. "KYC" appears only as a compliance **course category**. `OAuth2PasswordBearer`
is FastAPI's local password flow, not federated SSO. There is no SSO, no shared identity,
no webhook, no shared DB.
=> **Completely standalone silo.** Staff exist here a third time, unlinked.

## Engineering quality — the best-documented repo so far
- requirements.txt pinned with `==` and a written rationale for pinning
- Production **boot refusal** if: JWT_SECRET_KEY leaked/placeholder/<32 chars ·
  SEED_SAMPLE_DATA true · SQL_ECHO true · LOG_LEVEL DEBUG · CORS contains
  http://localhost or '*' · FRONTEND_URL empty · ADMIN_PASSWORD set
  (same defensive posture as GrowKyc — likely same author/assistant lineage)
- `.env.development` / `.env.production` ARE git-tracked but contain only
  `VITE_API_URL` — **no secret leak** (verified)
- JSON logs in production with credential-shaped values redacted
- Documented AWS guidance: use IAM task roles, leave static keys empty
- `RUN_MIGRATIONS_ON_START=false` in prod with a written explanation (Alembic takes no
  lock; concurrent ECS tasks would race) — migrate as a separate deploy step
- repositories/ layer (the only repo in the estate using that pattern)

## Deployment — three targets, fully built out
- `deploy/academy/` — EC2 docker compose + nginx + update.sh (the live one)
- `deploy/ec2/`     — alternate EC2 compose + nginx-academy.conf
- `deploy/aws/`     — **ECS/CloudFormation**: 01-foundation.yml, 02-training-service.yml,
  task definitions (api/web/migrate), IAM execution + task role policies, push-images.sh
  => the most production-mature deployment story in the estate
- `backend/db_setup_brickbanq.sql` — BriqBanq leaked in; this codebase was reused as a
  template for another product. Confirms it is a reusable app skeleton.

## Relevance to the CRM programme
- The LMS domain (courses/lessons/quizzes/certificates/enrolments) does not exist
  anywhere else. GrowKyc's `training` router is a 3-endpoint stub — **this is the real one**.
- Because it is INTERNAL staff training, its CRM value is: staff competency records,
  compliance evidence, and training-due nudges attached to staff, not to clients.
- It is small enough (112 endpoints, 21 tables, 5 migrations) that it is the **cheapest
  module to re-home** if a consolidation is chosen.
- Its stack is the newest and its deployment automation the best — a good reference
  template for whatever the CRM hub ends up being.

## Open question for the user
Is Training meant to stay INTERNAL staff training, or become a client-facing academy
sold/delivered through the CRM? The answer changes whether it needs tenancy at all.
