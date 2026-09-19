# Repo 3 — entiq-app  (github.com/abesaveni/entiq-app)

Local canonical clone: `D:\Grow Entiq Projects\entiq_app` — main @ a08c641 (2026-08-12),
clean, in sync with origin. 57 commits.

This is **Deployment Unit 3** named in GrowKyc's ENTIQ_PLATFORM_MAP.md.

## What it is
Flutter customer app — "Entiq customer onboarding + wallet app".
A **pure client of the GrowKyc API**. Holds no data of record.
Targets: iOS, Android, **and Web** (built + served at app/entiq.com.au).

## Stack
Flutter / Dart SDK ^3.12.2
Riverpod 3 (state) · go_router 17 (routing) · dio 5 (HTTP)
flutter_secure_storage 10 · local_auth 3 (biometric unlock) · mobile_scanner 7 (QR)
file_picker 8 · app_links 7 (deep links) · android_play_install_referrer
firebase_core 4 + firebase_messaging 16 (push)
built_value (generated models)

## Scale
- App code is SMALL: lib/features 29 + lib/core 30 + lib/design 3 = **62 dart files**
- `packages/entiq_api` = **500 dart files** — a GENERATED dart-dio OpenAPI client
- 8 test files
- `openapi.json` = 851 KB, committed at repo root (the contract snapshot)

### Feature sizes (dart files)
onboarding 13 · wallet 8 · entry 2 · resume 2 · home 1 · splash 1 · unlock 1 · debug 1
=> Only onboarding + wallet are substantially built (matches "M0 built" note).

### core/
api (api_providers, onboarding_repository, api_error) · session (session,
session_controller, session_interceptor, session_store) · biometric · deeplink ·
entry · flow · platform · push · router · wallet · env.dart

## ★ The API contract boundary (most important fact for the CRM plan)
`packages/entiq_api` is **generated from GrowKyc's openapi.json and never hand-edited**
(regenerate via `tool/gen_api.*`). It exposes **35 API groups**, including:
  admin · ai · audit · authentication · billing · cases · clients · communications ·
  compatibility · **crm** · dashboard · didit · documents · edd · equifax · head_office ·
  identity_documents · integrations · invoices · kyc · monitoring · notifications ·
  onboarding · payments · pexa · ... (+10 more)

=> The mobile app already consumes the GrowKyc **crm** API.
=> **Any breaking change to the GrowKyc API contract breaks this app** and requires a
   regen + rebuild + (for stores) a re-review. This is a hard constraint on how
   aggressively the CRM can refactor GrowKyc's endpoints.
=> It also independently VALIDATES the "one API, many surfaces" doctrine — a third
   surface is already live against it.

## Environments / hosting
`lib/core/env.dart`: dev | staging | prod via `--dart-define=ENTIQ_ENV=`
- staging base URL = **https://entiq.com.au**
- web build calls **same-origin** (`Uri.base.origin`) — the host proxies `/api/v1`
  to the backend, so there is deliberately NO CORS
- prod host "not yet distinct from staging"
- Android emulator dev uses 10.0.2.2
NOTE: this is the **entiq.com.au** brand fronting the **growfintec** KYC backend —
brand consolidation is already partly in motion at the hosting layer.

## CI (.github/workflows/ci.yml)
1. **Never-sells gate** (`tool/never_sells_gate.sh`) — build FAILS if any IAP /
   store-billing symbol appears (in_app_purchase, RevenueCat, StoreKit, SKPayment,
   BillingClient, com.android.vending.BILLING...). Rationale in-file: Entiq is a
   regulated real-world service, not digital goods; onboarding in-app, **payment in the
   system browser** (Apple 3.1.5(a)). Excludes docs + the generated client.
2. `flutter analyze lib test`
3. `flutter test`
4. Build Web (staging) + Build Android (debug)

## Build constraint (from memory, still applies)
C: is full — `flutter build web` needs `build/`, `.dart_tool` and TEMP junctioned to D:,
otherwise the bundle comes out partial (missing main.dart.js).

## Relevance to the CRM programme
- NOT a system of record; does not compete with any CRM module.
- It is the **mobile/web client surface** for the client-facing side (identity wallet,
  onboarding, document requests, consent/sharing).
- Its existence is the strongest practical argument that GrowKyc's API stays the
  client-facing contract: three surfaces already depend on it.
- Its generated client is a **change-cost multiplier**: CRM work that renames or
  restructures GrowKyc endpoints incurs app regen + store review.
- The `never-sells` rule constrains how CRM billing can ever surface on mobile.

## Verdict on repo 3
Low architectural risk, high constraint value. Keep as-is; treat the GrowKyc OpenAPI
contract as a governed interface with versioning + deprecation, not something the CRM
work can freely reshape.
