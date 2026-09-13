# VYRON - Gaming Commerce Platform

**Premium gaming commerce and digital marketplace platform**

VYRON is a production-ready commercial platform for:
- Game top-ups (PUBG Mobile, Roblox, Clash of Clans, etc)
- Digital products & game currencies
- Gift cards
- Marketplace with seller accounts
- Donations
- Wallet, promotions, coupons, reviews

Built with FastAPI, MySQL, Redis, aiogram, and premium soft UI.

---

## 🚀 One Command Startup

```bash
python main.py
```

This single command orchestrates:
1. ✅ FastAPI backend
2. ✅ Public website
3. ✅ Telegram Bot (if token configured)
4. ✅ Telegram Mini App backend
5. ✅ Background workers (order processing, supplier sync)
6. ✅ Scheduled jobs

Graceful shutdown on Ctrl+C.

---

## 📋 Requirements

- Python 3.11+
- MySQL 8.0+ (or SQLite for dev)
- Redis (optional, in-memory fallback)
- Telegram Bot Token (optional)

---

## 🛠️ Installation

```bash
# Clone
git clone https://github.com/shadowhuntersking10-cell/VYRON.git
cd VYRON

# Create venv
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run
python main.py
```

Visit:
- Website: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Admin: http://localhost:8000/admin

---

## ⚙️ Environment Variables

See `.env.example` for full list.

### Critical

```env
APP_SECRET=your-strong-secret-min-32-chars
DATABASE_URL=mysql+asyncmy://user:pass@localhost:3306/vyron
# Or for dev: sqlite+aiosqlite:///./vyron.db

TELEGRAM_BOT_TOKEN=your_bot_token
ADMIN_TELEGRAM_IDS=123456789,987654321

# Payments (configure when ready)
PAYME_MERCHANT_ID=
PAYME_SECRET=
CLICK_MERCHANT_ID=
CLICK_SECRET=
STRIPE_SECRET_KEY=

# Supplier
SUPPLIER_API_URL=
SUPPLIER_API_KEY=
SUPPLIER_ENABLED=false
```

### Business Safety Switches

```env
SALES_ENABLED=true
SUPPLIER_ORDERS_ENABLED=true
PAYMENTS_ENABLED=true
```

Disable risky systems instantly without code deploy.

---

## 🗄️ MySQL Setup

```sql
CREATE DATABASE vyron CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'vyron'@'localhost' IDENTIFIED BY 'strong_password';
GRANT ALL PRIVILEGES ON vyron.* TO 'vyron'@'localhost';
FLUSH PRIVILEGES;
```

Set in `.env`:
```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=vyron
MYSQL_USER=vyron
MYSQL_PASSWORD=strong_password
DATABASE_URL=mysql+asyncmy://vyron:strong_password@localhost:3306/vyron
```

For development without MySQL, use SQLite:
```env
DATABASE_URL=sqlite+aiosqlite:///./vyron.db
```

---

## 🔴 Redis Setup (Optional)

```bash
# Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or local
sudo apt install redis-server
sudo systemctl start redis
```

Set:
```env
REDIS_URL=redis://localhost:6379/0
```

If not set, in-memory fallback is used.

---

## 🤖 Telegram Bot Setup

1. Talk to @BotFather on Telegram
2. Create bot: `/newbot`
3. Get token
4. Set webhook or use polling (polling is default in VYRON)
5. Create Mini App: `/newapp` -> link to your bot
6. Set URL: `https://yourdomain.com/telegram-app`

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_WEBAPP_URL=https://t.me/your_bot/app
TELEGRAM_BOT_USERNAME=your_bot
ADMIN_TELEGRAM_IDS=your_telegram_id
```

Bot commands:
- `/start` - Welcome with Mini App button
- `/help` - Help
- `/profile` - Profile
- `/orders` - Orders
- `/support` - Support

---

## 💳 Payment Provider Setup

### Payme

```env
PAYME_MERCHANT_ID=your_merchant_id
PAYME_SECRET=your_secret
PAYME_ENDPOINT=https://checkout.paycom.uz/api
```

Implement webhook at: `/api/payments/webhook/payme`

### Click

```env
CLICK_MERCHANT_ID=...
CLICK_SERVICE_ID=...
CLICK_SECRET=...
```

Webhook: `/api/payments/webhook/click`

### Stripe

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
```

Webhook: `/api/payments/webhook/stripe`

**Important**: Orders are only marked PAID after verified server-side webhook, never from frontend.

If credentials missing, API returns `PAYMENT_PROVIDER_NOT_CONFIGURED` - no fake success.

---

## 📦 Supplier Setup

VYRON uses supplier abstraction. Implement your supplier adapter in `app/suppliers/providers.py`.

```env
SUPPLIER_API_URL=https://api.supplier.com
SUPPLIER_API_KEY=your_key
SUPPLIER_ENABLED=true
```

If not configured, orders go to `MANUAL_REVIEW` - never fake delivery.

Interface:
- `get_balance()`
- `get_products()`
- `create_order()`
- `get_order_status()`
- `cancel_order()`

---

## 🗃️ Migrations

VYRON auto-creates tables on first startup via `Base.metadata.create_all`.

For Alembic (production):

```bash
# Init (already configured)
alembic revision --autogenerate -m "init"
alembic upgrade head
```

---

## 🌱 Seed Data

On first startup, if no games exist, VYRON auto-seeds:

- 14 games (PUBG Mobile, Roblox, Clash of Clans, Clash Royale, CS2, Standoff 2, Free Fire, Mobile Legends, Brawl Stars, Valorant, Fortnite, LoL, Minecraft, EA FC)
- 5-10 products per game (60 UC, 325 UC, 400 Robux, etc)
- 7 donation presets (10k - 1M UZS)
- 3 donation profiles
- 4 marketplace categories
- 3 promotions
- Roles, supplier, settings

Seed is clearly marked as catalog data, not fake transactions.

No fake payments, revenue, or completed supplier orders are created.

---

## 🧪 Testing

```bash
# Run tests
pytest tests/ -v

# Test registration flow
python -m pytest tests/test_auth.py -v

# Test pricing engine
python -m pytest tests/test_pricing.py -v
```

Tests cover:
- registration, duplicate email, duplicate username
- wrong password, correct login, logout
- Telegram auth validation
- admin auth
- products, pricing, minimum safe price
- commission, coupon, checkout, orders
- payment states, webhooks, idempotency
- supplier orders, wallet, ledger, donations, marketplace, reviews, favorites

---

## 🎨 UI/UX

- **Design**: Premium Soft UI / Neumorphism
- **Colors**: Deep Navy #071426, Dark Blue #0B1F3A, Blue #2563EB, Light Blue #60A5FA, Soft Blue #DBEAFE
- **Features**: Dark/Light/System themes, responsive, mobile-first, Telegram Mini App style
- **Languages**: Uzbek (default), Russian, English - via `locales/*.json`

---

## 🔐 Security

- Secure password hashing (bcrypt)
- Secure sessions (httpOnly, secure cookies)
- RBAC with server-side admin check via `ADMIN_TELEGRAM_IDS`
- Rate limiting & brute-force protection
- CSRF where applicable, XSS protection
- SQL injection protection via ORM
- Security headers
- Telegram initData validation (HMAC SHA256, auth_date check, replay protection)
- Payment webhook signature verification
- Idempotency keys for orders, payments, supplier orders
- Audit logging for admin actions
- File upload validation (no executables)
- Never expose secrets in logs or frontend

---

## 📁 Project Structure

```
VYRON/
├── main.py
├── requirements.txt
├── .env.example
├── app/
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── main.py (FastAPI app)
│   ├── seed.py
│   ├── models/
│   ├── schemas/
│   ├── api/
│   ├── auth/
│   ├── payments/
│   ├── suppliers/
│   ├── telegram/
│   ├── services/
│   └── utils/
├── templates/
├── static/
├── locales/
└── tests/
```

---

## 🛣️ Routes

### Website

- `/` - Home
- `/games` - Games list
- `/games/{slug}` - Game detail
- `/products/{id}` - Product detail
- `/marketplace` - Marketplace
- `/marketplace/{id}` - Listing detail
- `/donations` - Donation profiles
- `/donations/{username}` - Donation profile
- `/promotions` - Promotions
- `/support` - Support
- `/about`, `/terms`, `/privacy`, `/refund` - Legal
- `/login`, `/register`, `/profile`, `/orders`, `/checkout`
- `/admin` - Admin panel
- `/telegram-app` - Telegram Mini App

### API

- `/api/auth/*` - Registration, login, Telegram auth
- `/api/games/*` - Games
- `/api/products/*` - Products
- `/api/orders/*` - Orders & checkout
- `/api/payments/*` - Payments, webhooks
- `/api/marketplace/*` - Marketplace
- `/api/donations/*` - Donations
- `/api/wallet/*` - Wallet
- `/api/users/*` - Users
- `/api/reviews/*` - Reviews
- `/api/favorites/*` - Favorites
- `/api/support/*` - Support tickets
- `/api/notifications/*` - Notifications
- `/api/admin/*` - Admin (protected)
- `/health` - Health check
- `/api/config` - Public config

---

## 💰 Pricing Engine

Core business safety:

```
Supplier Cost: 40,000 UZS
Payment Fee (2% + 500): 1,300
Safety Buffer (2%): 800
Base Cost: 42,100
Platform Margin (10%): 4,210
Minimum Safe Price: 46,310
Suggested Price: 48,625 (5% extra)
Expected Profit: 6,525
```

- Customer price can NEVER be below minimum safe price by default
- Admin override requires explicit flag
- Visual profit indicator in admin
- If profit < 0: BLOCK SAVE
- If profit < min margin: WARNING

---

## 🏪 Marketplace Commission

Configurable:

- Global commission (default 10%)
- Category commission
- Seller-specific commission

Example:
```
Sale: 100,000 UZS
Commission 10%: 10,000 to VYRON
Seller: 90,000
```

Seller sees breakdown.

---

## 💝 Donations

- Presets: 10k, 25k, 50k, 100k, 250k, 500k, 1M UZS + custom
- Platform fee configurable (default 5%)
- Example: 100k donation, 5% fee, recipient gets 95k, VYRON gets 5k
- Breakdown shown before payment

---

## 📊 Revenue Dashboard

Admin sees:

- Today / 7 days / 30 days / custom
- Gross Revenue, Supplier Costs, Payment Fees, Platform Revenue, Marketplace Commission, Donation Fees, Seller Payouts, Refunds, Net Profit, Orders, AOV
- Charts: Revenue, Profit, Orders, Top Games, Top Products, Top Sellers

Only verified transactions count.

---

## 🧩 Telegram Mini App

- Mobile-first
- Navigation: Home, Games, Marketplace, Orders, Profile, Admin (for admins)
- Telegram WebApp APIs: theme detection, safe area, back button, main button, haptic feedback
- Looks like native premium app

---

## 🚢 Production Deployment

```bash
# Set env to production
APP_ENV=production

# Use MySQL, Redis, strong secrets
# Set APP_SECRET, SESSION_SECRET

# Run with systemd or docker
# Example systemd service:
[Unit]
Description=VYRON
After=network.target

[Service]
User=vyron
WorkingDirectory=/opt/VYRON
EnvironmentFile=/opt/VYRON/.env
ExecStart=/opt/VYRON/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

- Use reverse proxy (nginx) with TLS
- Set secure cookies
- Enable rate limiting at proxy level
- Backup MySQL regularly
- Monitor logs

---

## 🐛 Troubleshooting

**Database connection failed**:
- Check MYSQL_* env or DATABASE_URL
- For dev, use SQLite: `DATABASE_URL=sqlite+aiosqlite:///./vyron.db`
- Ensure MySQL is running

**Telegram bot not starting**:
- Check TELEGRAM_BOT_TOKEN
- Bot will be disabled if token missing, app still works

**Payments show NOT CONFIGURED**:
- Set Payme/Click/Stripe credentials in .env
- This is expected if not configured - no fake success

**Supplier orders in MANUAL_REVIEW**:
- Configure SUPPLIER_API_URL and SUPPLIER_API_KEY
- Or process manually via admin panel

**Port already in use**:
- Change APP_PORT in .env or kill process on 8000

---

## 📄 License

Private - VYRON commercial platform.

---

## 🤝 Contributing

This is a commercial platform foundation. For production use, review security, payments, and legal pages.

---

**Built with ❤️ for gamers - VYRON**
