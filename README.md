# VYRON 🎮

Professional gaming & digital marketplace platform: game top-ups, gift cards,
marketplace, sellers, donations, orders, payments, wallet, Telegram Mini App + Bot,
admin panel, promotions, coupons, payouts, media library and revenue management.

Seed catalog: **19 games / 96 products** (PUBG Mobile, Roblox, Clash of Clans,
Clash Royale, CS2, Standoff 2, Free Fire, Mobile Legends, Brawl Stars, Valorant,
Fortnite, EA Sports FC, League of Legends, Minecraft + Steam/PlayStation/Xbox/
Apple/Google Play gift cards), 4 categories, demo seller with listings, demo
donation profiles, promotions and a WELCOME10 coupon. Seed products use manual
fulfilment (paid orders → MANUAL_REVIEW) until a real supplier is configured.

**Single entry point — everything starts with:**

```bash
python main.py
```

---

## 1. Requirements

- Python 3.11+
- MySQL 8 (production) — SQLite dev fallback works out of the box
- Redis (optional, recommended in production)

## 2. Installation

```bash
git clone <repo> && cd VYRON
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env (see below)
python main.py
```

Open: **http://localhost:8000** · Mini App: **/miniapp** · Admin: **/admin**

## 3. Environment variables

| Group | Variables |
|---|---|
| App | `APP_ENV APP_SECRET APP_BASE_URL APP_HOST APP_PORT DEFAULT_LANG` |
| MySQL | `MYSQL_HOST MYSQL_PORT MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD` or full `DATABASE_URL` |
| Redis | `REDIS_URL` (e.g. `redis://localhost:6379/0`) |
| Telegram | `TELEGRAM_BOT_TOKEN TELEGRAM_WEBAPP_URL ADMIN_TELEGRAM_IDS` |
| Payme | `PAYME_MERCHANT_ID PAYME_SECRET_KEY` |
| Click | `CLICK_MERCHANT_ID CLICK_SERVICE_ID CLICK_SECRET_KEY` |
| Stripe | `STRIPE_SECRET_KEY STRIPE_PUBLISHABLE_KEY STRIPE_WEBHOOK_SECRET` |
| Supplier | `SUPPLIER_DEFAULT SUPPLIER_API_URL SUPPLIER_API_KEY SUPPLIER_API_SECRET` |
| SMTP | `SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD SMTP_FROM` |
| Storage | `STORAGE_BACKEND STORAGE_LOCAL_DIR STORAGE_MAX_FILE_MB` |
| Revenue | `MARKETPLACE_COMMISSION_PERCENT DONATION_FEE_PERCENT SERVICE_FEE_*` |
| Seed | `SEED_DEMO_DATA ADMIN_EMAIL ADMIN_PASSWORD` |

Never commit `.env`. See `.env.example` for the full list.

## 4. MySQL setup

```sql
CREATE DATABASE vyron CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'vyron'@'%' IDENTIFIED BY 'strong-password';
GRANT ALL ON vyron.* TO 'vyron'@'%';
```

Set `MYSQL_*` in `.env`, then either let `main.py` auto-create tables or run:

```bash
alembic upgrade head
```

Without MySQL credentials a development boot uses a local SQLite fallback
(`vyron_dev.db`) with a clear warning. **Production (`APP_ENV=production`)
strictly requires MySQL and fails fast if it is unreachable** — there is no
silent downgrade. Donation presets, marketplace categories, commissions, fees
and promotion pricing are all admin-configurable (Admin → Settings).

## 5. Redis setup (optional)

```bash
docker run -d -p 6379:6379 redis:7
# .env: REDIS_URL=redis://localhost:6379/0
```

## 6. Telegram Bot setup

1. Create a bot with [@BotFather](https://t.me/BotFather) → get the token.
2. `.env`: `TELEGRAM_BOT_TOKEN=<token>` and `TELEGRAM_BOT_USERNAME=<botname>`.
3. The bot starts automatically with `python main.py` (long polling).
4. Commands: `/start /help /games /profile /orders /support /paysupport`.
5. Telegram Stars: once the token is set, the `stars` provider appears in
   checkout; the bot sends real XTR invoices (`?start=pay_<order>`) and
   settles them via `pre_checkout` / `successful_payment` handlers.

## 6b. Pricing engine

Every product carries cost inputs (`supplier_cost`, payment %, platform
margin %, minimum margin %). The server derives a **minimum safe price**
and a **suggested price**; saving below the floor is blocked unless the
product is an explicitly confirmed loss-leader. See Admin → **Pricing**.

## 7. Telegram Mini App setup

1. Deploy VYRON on HTTPS (Telegram requires it).
2. `.env`: `TELEGRAM_WEBAPP_URL=https://yourdomain.com/miniapp`.
3. In BotFather: Bot Settings → Menu Button → set the same URL.
4. Mini App authenticates via signed `initData` (`/api/telegram/auth`).

## 8. Admin access

Two ways:

- **Telegram IDs (recommended):** `ADMIN_TELEGRAM_IDS=123456789,987654321`
  — matching Telegram users get `ADMIN` automatically.
- **Seed admin:** `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`
  (defaults: `admin@vyron.local` / `Admin12345!` — change in production).

Admin panel: `/admin` (every `/api/admin/*` route is server-side protected).

## 9. Payment configuration

Providers are real integrations behind a common interface
(`create_payment / verify_payment / handle_webhook / refund_payment`).
Without credentials the platform honestly shows **"Payment provider not
configured"** — nothing is faked.

- **Payme:** `PAYME_MERCHANT_ID`, `PAYME_SECRET_KEY` → webhook `/api/webhooks/payme`
- **Click:** `CLICK_*` → webhook `/api/webhooks/click`
- **Stripe:** `STRIPE_*` → webhook `/api/webhooks/stripe` (HMAC verified)

Configure the webhook URLs in each provider's merchant cabinet.

## 10. Supplier configuration

- Default `manual` supplier routes paid top-ups to `MANUAL_REVIEW`.
- For automation point `SUPPLIER_API_URL` + `SUPPLIER_API_KEY` at your
  top-up provider (or set per-game/per-product suppliers in Admin →
  Suppliers / Games / Products) and select the `generic` provider.

## 11. Project structure

```
main.py                 single entry point (API + bot + workers)
app/                    config, database, models, schemas, repositories,
                        services, api/*, auth, payments, suppliers,
                        telegram, marketplace, donations, orders,
                        admin, notifications, utils, scheduler, seed
migrations/             Alembic (env + 0001_initial)
templates/              public / app / admin / miniapp / auth / errors
static/                 css (Soft UI) / js
locales/                uz.json en.json ru.json (default: uz)
tests/                  pytest suite
```

## 12. Development & production

```bash
python main.py          # run everything
pytest -q               # run tests
alembic upgrade head    # migrations (production)
```

Production checklist: `APP_ENV=production`, strong `APP_SECRET`, MySQL,
Redis, HTTPS (`APP_BASE_URL`), real Telegram/Payment/Supplier credentials,
`SEED_DEMO_DATA=false`, reverse proxy (nginx/caddy) → `APP_PORT`.

Docker alternative (app + MySQL):

```bash
docker compose up --build -d   # reads MYSQL_*/APP_* from .env
```

## 13. Honesty rules (built-in)

- No payment credentials → "not configured", order stays `PENDING_PAYMENT`.
- No supplier credentials → order goes to `MANUAL_REVIEW`, never fake-completed.
- Revenue reports include **only verified** transactions.
- Supplier costs are never exposed to clients.

## 14. License

Proprietary — all rights reserved.
