# VYRON — Digital Gaming Marketplace

**VYRON** — production-grade digital gaming marketplace: game currency, top-ups,
gift cards and digital products with **automated fulfillment via Payerpin**.

One command starts **everything**:

```bash
pip install -r requirements.txt
python main.py
```

That single process runs:

| Component | Description |
|---|---|
| **Website + WebApp** | Soft UI frontend (day/night modes, UZ/EN/RU) |
| **REST API** | FastAPI backend (auth, catalog, cart, checkout, orders, admin) |
| **Telegram bot** | `/start` → WebApp button; `/admin` for admin IDs |
| **Fulfillment worker** | Payerpin orders with locking, retries, idempotency |
| **Catalog scheduler** | periodic real Payerpin catalog sync |
| **Database** | MySQL (SQLite dev fallback) — migrations run automatically |

---

## 1. Quick start (development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in what you have; app runs without any secrets
python main.py                # http://localhost:8000
```

Without external credentials the platform is **honest** about it:

* products show **NOT AVAILABLE** until the real Payerpin catalog is synced
* checkout shows **Payment is not configured** until a payment provider is set
* admin → Payerpin page shows **NOT CONFIGURED**
* nothing is ever faked — no fake prices, orders, payments or fulfillment

## 2. Production configuration

All secrets live in the environment (`.env` / server secrets) — **never in code**.
See [.env.example](.env.example):

```ini
PUBLIC_BASE_URL=https://your-domain.example
WEBAPP_URL=https://your-domain.example
SESSION_SECRET=<long random string>
DATABASE_URL=mysql+pymysql://user:pass@host:3306/vyron

PAYERPIN_API_KEY=<from Payerpin cabinet>
PAYERPIN_BASE_URL=https://api.payerpin.uz

PAYMENT_PROVIDER=generic            # or: sandbox (explicit test mode)
PAYMENT_API_KEY=<payment provider>
PAYMENT_SECRET=<payment provider>
PAYMENT_WEBHOOK_SECRET=<webhook HMAC secret>

TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_ADMIN_IDS=123456789,987654321
```

* **Payerpin** is the supplier/fulfillment provider (v2 reseller API:
  `GET /api/v2/me`, `/api/v2/balance`, `/api/v2/catalog`, `/api/v2/catalog/{gameKey}`,
  `POST /api/v2/order`, `GET /api/v2/order/{id}`, `/api/v2/orders` — auth header
  `X-API-Key`). If your account documentation differs, the adapter follows the
  actual official docs (see `app/providers/suppliers/payerpin.py`).
* **Payments** are a *separate* system: customer → VYRON → payment provider →
  **verified webhook** → VYRON → Payerpin → top-up. The frontend can never
  confirm a payment; only signed server-side webhooks can.
* `PAYMENT_PROVIDER=sandbox` enables an explicitly configured **test-mode**
  provider (labelled in the UI) that signs real HMAC webhooks for end-to-end
  testing. It is never active by default.

### Telegram WebApp

1. Create a bot with [@BotFather](https://t.me/BotFather), set the WebApp URL
   (`WEBAPP_URL`) via `/newapp` or `/setmenubutton`.
2. Put the token in `TELEGRAM_BOT_TOKEN`, your numeric user ID(s) in
   `TELEGRAM_ADMIN_IDS`.
3. `/start` in the bot shows **Open VYRON** (WebApp button). Users are
   authenticated with Telegram `initData` HMAC verification **server-side**.
   Admin IDs automatically receive the admin role and the **Admin panel** button.

### Admin access

* Web: register an account → promote to `ADMIN` (via another admin or the
  `PATCH /api/admin/users/{id}` role change).
* Telegram: numeric IDs in `TELEGRAM_ADMIN_IDS` are automatically admins.
* Every admin route is enforced **server-side** (401/403 for anyone else) and
  every admin action is written to the immutable audit log.

## 3. Design

* **Soft UI** (soft shadows, rounded surfaces, glassy header)
* Colors: **to'q ko'k** (deep navy `#0B2447`) + **och ko'k** (light blue `#4DA8DA/#5AB2F7`)
* **Kun / Tun** (day / night) themes, persisted (localStorage + account profile)
* **3 languages**: O'zbekcha · English · Русский — everything translatable
  (backend `app/i18n.py`, frontend `web/assets/js/i18n.js`), persisted per user
* Fully responsive: desktop, tablet, mobile, Telegram WebApp viewport

## 4. Order flow (production)

```
customer → game → real product/variant → player info (validated)
        → server-side price (NEVER trust frontend price)
        → VYRON order (VYR-YYYYMMDD-000001) + payment
        → payment provider → signed webhook (HMAC-SHA256, delivery-id dedup)
        → PAID → fulfillment worker (row locks, idempotency key per order)
        → Payerpin createOrder → status polling + Payerpin webhooks
        → COMPLETED / FAILED (+ in-app & Telegram notifications)
```

* Supplier orders are created **exactly once** (unique supplier transaction per
  order + idempotency key); timeouts first check supplier status — never a
  duplicate top-up.
* Unknown supplier statuses are never treated as COMPLETED.
* Failed fulfillment never marks an order completed; refunds are a separate,
  admin-initiated payment-provider action.

## 5. Admin panel (`#/admin`)

Dashboard · Users · Games · Products · Variants · Orders (cancel/refund/retry) ·
Payments · Fulfillments · **Payerpin** (test connection / sync catalog /
check balance — never shows the API key) · Pricing (margin system) · Coupons ·
Promotions · Analytics · Notifications (broadcast) · Telegram · Security ·
Audit logs · System health (Configured / Not configured / Connected) · Settings.

Pricing model: `supplier cost + payment fee + VYRON margin = customer price`
(global / product / variant margin). Supplier costs and profit are internal-only.

## 6. API overview

* `POST /api/auth/register|login|logout|telegram` · `GET /api/auth/me`
* `GET /api/games`, `GET /api/games/{slug}`, `GET /api/products`, `GET /api/search`
* `GET/POST/PATCH/DELETE /api/cart[...]` · `POST /api/checkout`
* `GET /api/orders`, `GET /api/orders/{order_number}`
* `POST /api/webhooks/payments` — payment provider (HMAC verified, idempotent)
* `POST /api/webhooks/payerpin` — supplier events (HMAC verified, idempotent)
* `GET /api/support/faq` · `GET /api/account/[...]`
* `GET/POST/PATCH/PUT /api/admin/[...]` — RBAC-protected
* `GET /healthz`

Interactive API docs (dev): `APP_DEBUG=true` → `/api/docs`.

## 7. Tests

```bash
pytest tests/ -q
```

61 tests cover: auth, products, cart, checkout, orders, payments, webhooks,
Payerpin adapter, idempotency, admin authorization, catalog sync, pricing,
coupons + failure scenarios (invalid login, duplicate registration, invalid
player ID, unavailable product, changed price, failed/duplicate/invalid-signature
webhooks, amount mismatch, unknown order, supplier timeout, insufficient
mapping, invalid admin access).

## 8. Project layout

```
main.py                  # single entrypoint (web + api + bot + workers)
app/
  config.py              # env settings (secrets never logged/exposed)
  db.py                  # SQLAlchemy engine (MySQL-first, SQLite fallback)
  migrations.py          # schema + seed (40-game catalog structure, roles…)
  models/                # users, games, products, variants, orders, payments,
                         # fulfillments, supplier_transactions, webhooks, coupons…
  security.py            # bcrypt, sessions, Telegram initData HMAC, rate limit
  i18n.py                # backend uz/en/ru strings
  api/                   # auth, catalog, cart, checkout, account, webhooks,
                         # support, admin, sandbox
  services/              # pricing, orders, payments, fulfillment, catalog_sync,
                         # notifications, audit
  providers/
    suppliers/payerpin.py    # Payerpin v2 adapter
    payments/                # provider interface + sandbox + generic
  worker is in services/fulfillment.py
bot/bot.py               # aiogram bot (/start → WebApp button)
web/                     # Soft UI SPA (index.html, css/, js/)
tests/                   # pytest suite
```

## 9. Security notes

* bcrypt password hashing, server-side hashed session tokens, login lockout
* Telegram `initData` HMAC verification (server-side, 24h freshness)
* Webhook HMAC-SHA256 (`timestamp.rawBody`), constant-time compares,
  delivery-id dedup, amount/currency/merchant checks
* Role-based authorization on every admin route; audit logging of admin actions
* Rate limiting, security headers (CSP, HSTS…), SQL-injection-safe ORM,
  server-side validation of all forms and player fields
* Secrets never appear in logs (redaction filter), API responses, DB or git
  (`.env` ignored; `.env.example` placeholders only)

## 10. Honest limitations (by design)

* **Payerpin**: not connected until `PAYERPIN_API_KEY` is set and **Test
  connection** succeeds from the admin panel. Until then: NOT CONFIGURED.
* **Payments**: a real provider must be configured (`PAYMENT_PROVIDER`). The
  `generic` adapter verifies webhooks immediately; its create-payment endpoint
  activates against the provider's official API once confirmed. `sandbox` is
  for end-to-end testing only and clearly labelled.
* **Catalog / prices**: no products are sellable before a real Payerpin catalog
  sync maps real supplier product/variation IDs and costs. The 40-game catalog
  structure exists (game pages, banners, currencies) but shows
  **NOT AVAILABLE** instead of invented prices.
* **Password reset**: token flow is implemented; email delivery requires an
  email provider integration (tokens are never returned by the API).
