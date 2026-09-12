# VYRON — Gaming & Digital Marketplace

**PLAY. BUY. DONATE.**

Production-ready marketplace for game top-ups, digital goods, a seller marketplace and
creator donations — with a public website, a Telegram Mini App, a Telegram bot and a
full admin panel, all served by **one shared backend**.

---

## Feature overview

| Domain | What's implemented |
|---|---|
| **Auth** | Argon2id hashing, HTTP-only session cookies, CSRF (double-submit), Redis-backed rate limiting, email verification, password reset, "log out everywhere" |
| **RBAC** | `USER / SELLER / SUPPORT / MODERATOR / FINANCE / ADMIN / SUPER_ADMIN` — enforced **server-side on every route** (API + SSR pages). No client-side role flags anywhere |
| **Catalog** | Games → products → variants, dynamic required top-up fields (per game/product, with patterns & validation), stock, featured flags |
| **Cart & checkout** | Server-priced cart (client prices are ignored), coupons (percent/fixed, limits, min order), service fees, idempotent order placement |
| **Orders** | Strict state machine `CREATED → PAYMENT_PENDING → PAID → PROCESSING → DELIVERING → COMPLETED` (+ `MANUAL_REVIEW / FAILED / REFUND_PENDING / REFUNDED / CANCELLED`), numbers `VYR-YYYY-NNNNNN`, full timeline history |
| **Payments** | Provider abstraction (Payme, Click, Stripe adapters), webhook **signature verification** — only server-verified events move money states; refunds workflow |
| **Suppliers** | `SupplierProvider` interface + HTTP-JSON adapter, `SupplierRouter` with priority/failover, reconciliation queue (never double-delivers paid orders), supplier test/sync from admin |
| **Donations** | Public `/donate/<username>` pages, server-side amounts, configurable platform fee shown transparently at checkout |
| **Seller marketplace** | Listings `DRAFT → PENDING_REVIEW → APPROVED → ACTIVE → SOLD`, sensitive delivery data encrypted & revealed only after purchase, balance with pending/available/reserved, holding period, payouts workflow, promoted listings, premium subscription plans |
| **Revenue** | Immutable ledger (gross, supplier costs, margin, commissions, donation/service/payment fees, refunds, payouts, net), `/admin/revenue` dashboard with charts & range filters, per-product profitability. **Unverified events never enter reporting** |
| **Fraud** | Risk engine (0–100 score + signals), high-risk orders routed to `MANUAL_REVIEW`, admin resolution flow |
| **Notifications** | In-app + email outbox (worker-sent, honestly `SKIPPED` when SMTP absent) + Telegram messages |
| **Support** | Ticket threads with status transitions, admin replies, internal notes |
| **Telegram** | Mini App (initData HMAC auth, bottom-nav SPA, haptics, safe areas) + bot (`/start` with 🚀 web-app button, `/help /orders /profile /support`, one-time `/start <token>` account linking, `ADMIN_TELEGRAM_IDS` gate) |
| **i18n** | Uzbek (default), English, Russian — 650+ keys, persisted per user/cookie, zero hardcoded UI strings |
| **Theming** | Dark / light / system, persisted, pre-paint boot (no flash) |
| **Ops** | `/health`, `/ready`, OpenAPI docs at `/api/docs`, structured errors `{success:false,error:{code,message}}`, audit logs + admin action trail, queue health & DLQ |

## Tech stack

- **Python 3.11**, FastAPI, SQLAlchemy 2.0 (sync) + **MySQL 8** via Alembic migrations
- **Redis 7** — custom Redis-Streams job queue (consumer groups, retries w/ backoff, DLQ, dedupe keys, interval-locked schedulers)
- **python-telegram-bot 21** (asyncio, own thread) — Mini App + bot
- Jinja2 SSR website + vanilla ES-module JS, hand-crafted Soft-UI/neumorphism CSS (no UI framework)
- argon2-cffi, httpx, minio (S3-compatible storage, local-disk fallback)

## Quickstart

### With Docker (recommended)

```bash
cp .env.example .env      # set SESSION_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD (+ provider keys)
docker compose up -d --build
# → http://localhost:8000  (API docs: /api/docs, Mini App: /miniapp)
```

### Locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # point DATABASE_URL/REDIS_URL at your MySQL+Redis, set secrets
python main.py            # ← the ONLY entry point
```

`python main.py` orchestrates everything in one process:
preflight (MySQL+Redis reachability with clear errors) → Alembic migrations →
seed (super admin from `ADMIN_EMAIL/ADMIN_PASSWORD`, default settings, demo catalog when
`SEED_DEMO_DATA=1`) → queue workers + periodic scheduler (payment reconciliation, supplier
sweep, holding-period balance releases, promotion expiry) → Telegram bot (when
`TELEGRAM_BOT_TOKEN` set) → uvicorn web server, with graceful shutdown on SIGINT/SIGTERM.

### Tests

```bash
pytest tests/ -q          # 70 tests against real MySQL (vyron_test DB) + Redis
ruff check vyron tests main.py
```

## Environment variables

See [`.env.example`](.env.example) — every variable is documented there. Highlights:

| Variable | Purpose |
|---|---|
| `SESSION_SECRET` | **Required.** 32+ bytes (`openssl rand -hex 32`) |
| `DATABASE_URL` | MySQL DSN (`mysql+pymysql://user:pass@host:3306/vyron`) |
| `REDIS_URL` | Redis DSN — queues, rate limits, session locks |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seeded SUPER_ADMIN |
| `SEED_DEMO_DATA` | `1` in dev seeds games/products/coupon (never fake financial data) |
| `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_IDS` | Bot + Mini App; server-side Telegram admin gate |
| `PAYME_*`, `CLICK_*`, `STRIPE_*` | Payment credentials — absent ⇒ `PAYMENT_PROVIDER_NOT_CONFIGURED` (never a fake success) |
| `SMTP_*` | Email — absent ⇒ outbox rows marked `SKIPPED` with reason |
| `SUPPLIER_API_*` | HTTP supplier — absent ⇒ `SUPPLIER_NOT_CONFIGURED` |

## Integrations that need real credentials

Payments (Payme/Click/Stripe), supplier API, SMTP, Telegram bot, S3/MinIO storage.
Each missing credential produces a **structured config error at the exact point of use** —
no silent fallbacks, no simulated deliveries, no fake revenue.

## Project layout

```
main.py                 single entry point (preflight → migrate → seed → workers → bot → web)
vyron/
  app.py                FastAPI application factory
  api/                  18 JSON routers (auth, cart, checkout, orders, admin, seller, …)
  web/                  SSR router + Jinja2 render context + JSON serializers
  services/             21 business-logic modules (orders, payments, delivery, revenue, fraud…)
  db/models/            50 tables — SQLAlchemy 2.0 typed models, DECIMAL money, GUID PKs
  security/             hashing, sessions, CSRF, rate limiting, RBAC, Telegram initData HMAC
  payments/             provider abstraction + payme/click/stripe adapters + webhook registry
  suppliers/            SupplierProvider interface, router with failover, HTTP-JSON adapter
  queue/                Redis Streams engine (retries, DLQ, dedupe, interval locks)
  workers/              queue consumers + periodic scheduler (reconciliation, balance release)
  telegram_bot/         bot handlers + threaded asyncio runner
  i18n/                 uz/en/ru catalogs (identical key sets, enforced by tests)
templates/              28 SSR pages (public, auth, dashboard, seller, admin, miniapp, error)
static/                 vyron.css design system + 13 ES-module page scripts
migrations/             Alembic (head: 614fd1cdb953)
tests/                  70 pytest tests (real MySQL + Redis, no infrastructure mocks)
```

## Security model

- Passwords: Argon2id. Sessions: HTTP-only, SameSite=Lax, server-side revocable rows.
- CSRF: double-submit cookie enforced on all `/api/*` mutations (webhooks exempt — signature-verified instead).
- Money: `DECIMAL(16,2)` in MySQL, `Decimal` in Python — floats never touch finances.
- Supplier **cost prices are never serialized** to any customer-facing endpoint (test-enforced).
- Admin: every `/admin*` page and `/api/admin/*` route checks roles server-side; non-staff get 404 (pages) / 403 (API).
- Webhooks: signature verification per provider; unverified events are recorded and rejected.
- Errors: structured `{success, error:{code, message}}`; production never leaks stack traces; logs redact secrets.
- CORS: explicit origin allowlist — never `*`.

## License

Proprietary — all rights reserved.
