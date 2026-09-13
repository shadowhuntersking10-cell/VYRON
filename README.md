# VYRON — Gaming Commerce & Digital Marketplace Platform

VYRON is a production-oriented commercial platform for game top-ups, digital products,
gift cards, donations, marketplace trade, sellers, payments, suppliers, wallet, coupons,
reviews, support, Telegram bot + Mini App, public website and an admin panel with revenue tracking.

**One command starts everything:**

```bash
python main.py
```

This orchestrates: FastAPI backend + public website + Mini App backend + payment webhooks,
Telegram bot, background workers and scheduled jobs — with graceful shutdown.

---

## 1. Requirements

- Python 3.11+
- MySQL 8 (production) — development may use the automatic local fallback (see below)
- Redis (optional — in-memory fallback is used when not configured)
- Telegram bot token (optional — bot idles with a warning when missing)

## 2. Installation

```bash
git clone <repo> VYRON && cd VYRON
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real values
```

## 3. Environment variables

See `.env.example` for the full list. Key groups:

| Group | Variables |
|---|---|
| App | `APP_ENV`, `APP_SECRET`, `BASE_URL`, `HOST`, `PORT` |
| MySQL | `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD` or `DATABASE_URL` |
| Redis | `REDIS_URL` (optional) |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBAPP_URL`, `ADMIN_TELEGRAM_IDS` |
| Safety | `SALES_ENABLED`, `SUPPLIER_ORDERS_ENABLED`, `PAYMENTS_ENABLED`, `LOSS_SELLING` |
| Fees | `PAYMENT_FEE_PERCENT`, `PAYMENT_FEE_FIXED`, `SAFETY_BUFFER_PERCENT`, `PLATFORM_MARGIN_PERCENT`, `MINIMUM_MARGIN_PERCENT`, `MARKETPLACE_COMMISSION_PERCENT`, `DONATION_FEE_PERCENT` |
| Payments | `PAYME_*`, `CLICK_*`, `STRIPE_*` |
| Supplier | `SUPPLIER_API_URL`, `SUPPLIER_API_KEY` |
| Media/SMTP | `MEDIA_DIR`, `MAX_UPLOAD_MB`, `SMTP_*` |

Never commit `.env`. Never hardcode secrets.

## 4. MySQL setup

```sql
CREATE DATABASE vyron CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'vyron'@'%' IDENTIFIED BY 'strong-password';
GRANT ALL ON vyron.* TO 'vyron'@'%';
```

```bash
# .env
DATABASE_URL=mysql+pymysql://vyron:strong-password@localhost:3306/vyron?charset=utf8mb4
```

Run migrations:

```bash
.venv/bin/alembic -c migrations/alembic.ini upgrade head
# or let main.py create tables automatically on first start (init_db)
```

Seed catalog:

```bash
python main.py --seed-only
```

> Development: if MySQL is not configured and `APP_ENV != production`, the app uses a local
> `dev.db` with a loud warning. Production **requires** MySQL and refuses to start otherwise.
> Check only: `python main.py --check`.

## 5. Redis setup (optional)

```bash
# .env
REDIS_URL=redis://localhost:6379/0
```

When empty, rate limiting/caching use a safe in-memory fallback.

## 6. Telegram Bot setup

1. Create a bot via [@BotFather](https://t.me/BotFather), copy the token into `TELEGRAM_BOT_TOKEN`.
2. Set `TELEGRAM_WEBAPP_URL=https://your-domain/tg-miniapp`.
3. In BotFather: `/mybots → Bot Settings → Menu Button → Configure menu button` with your Mini App URL.
4. Set `ADMIN_TELEGRAM_IDS=123456789,987654321` — these Telegram IDs get the admin role server-side.

Bot commands: `/start /help /profile /orders /support /paysupport`. Order/payment events trigger
real Telegram notifications through the same backend services as the website.

## 7. Telegram Mini App setup

The Mini App is served at `/tg-miniapp` (mobile-first, theme detection, safe-area, back button,
haptics). Authentication validates `initData` **server-side** (hash + `auth_date`, replay protection).
Deploy behind HTTPS and set `TELEGRAM_WEBAPP_URL` accordingly.

## 8. Payment provider setup

Providers implement a common adapter interface (`app/payments/*`). Statuses are visible at
`GET /api/payments/providers` and honesty is enforced:

- `PAYME_MERCHANT_ID`, `PAYME_SECRET` (+ endpoint) → checkout redirect + signed JSON-RPC webhooks
- `CLICK_MERCHANT_ID`, `CLICK_SERVICE_ID`, `CLICK_SECRET` → redirect + `sign_string` verification
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` → timestamped `Stripe-Signature` verification
- Telegram Stars → enabled when the bot token is set (for digital goods inside Telegram)

Without credentials the provider reports `NOT_CONFIGURED` and checkout refuses to fake success.
**An order becomes PAID only after verified server-side confirmation** (webhook signature,
amount match, idempotency). Webhooks: `POST /api/payments/webhooks/{payme,click,stripe}`.

## 9. Supplier setup

Suppliers implement `get_balance/get_products/create_order/get_order_status/cancel_order`
(`app/suppliers/*`). Configure in Admin → Suppliers or `.env` (`SUPPLIER_API_URL`, `SUPPLIER_API_KEY`).
After payment, the order goes to `SUPPLIER_PROCESSING` and completes **only on real supplier
confirmation** (polled by the background worker). Without a configured supplier, orders go to
`MANUAL_REVIEW` — delivery is never faked. Unique references + idempotency keys prevent duplicates.

## 10. Local development

```bash
python main.py                 # full stack on http://0.0.0.0:8000
python main.py --check         # preflight only
python main.py --seed-only     # init DB + seed catalog
pytest tests/ -q               # test suite
```

## 11. Production deployment

1. Set `APP_ENV=production`, strong `APP_SECRET`, MySQL `DATABASE_URL`, `BASE_URL=https://...`.
2. Run `alembic -c migrations/alembic.ini upgrade head`.
3. Run behind a reverse proxy (nginx/caddy) with TLS; forward `/api/payments/webhooks/*`.
4. Run `python main.py` under systemd/supervisor; logs are structured on stdout.
5. Set payment + supplier credentials; verify statuses in Admin → Payments/Suppliers.
6. Keep `LOSS_SELLING=false` (default) so the pricing engine blocks below-cost prices.

## 12. Security notes

PBKDF2 password hashing, server-side sessions with rotation/expiry, rate limiting, brute-force
protection, RBAC (user/seller/admin), Telegram `initData` verification, signed payment webhooks,
supplier auth, idempotency everywhere, audit logging, upload validation (type/MIME/size/dimensions),
security headers, secure cookies. No secrets are ever logged or committed.

## 13. Business safety

- Pricing engine computes minimum-safe/suggested prices from supplier cost + fees + margin and
  **blocks** below-cost saves unless an explicit admin override is enabled.
- Emergency switches: `SALES_ENABLED`, `SUPPLIER_ORDERS_ENABLED`, `PAYMENTS_ENABLED`.
- All money uses `DECIMAL`; wallet/ledger are append-only ledgers.

## 14. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `FATAL: Production requires MySQL` | Set `DATABASE_URL` or `MYSQL_*` |
| `PAYMENT_PROVIDER_NOT_CONFIGURED` | Add provider credentials to `.env` |
| Order stuck in `MANUAL_REVIEW` | No supplier configured — configure one or fulfill manually |
| Bot idle | `TELEGRAM_BOT_TOKEN` missing |
| `price_below_minimum` | Raise price above minimum-safe or enable override explicitly |

## 15. Project structure

```
main.py app/ templates/ static/ locales/ migrations/ tests/
app/{config,database,dependencies,models,schemas,repositories,services,
    api,auth,payments,suppliers,telegram,marketplace,donations,media,
    notifications,utils,web,seed.py,worker.py,app.py}
```
