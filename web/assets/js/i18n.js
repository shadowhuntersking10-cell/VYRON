/* VYRON i18n — uz / en / ru. Every visible UI string lives here. */
export const LANGS = ["uz", "en", "ru"];

const dict = {
  // ---- nav / chrome ----
  nav_home: { uz: "Bosh sahifa", en: "Home", ru: "Главная" },
  nav_games: { uz: "O'yinlar", en: "Games", ru: "Игры" },
  nav_support: { uz: "Yordam", en: "Support", ru: "Поддержка" },
  nav_account: { uz: "Kabinet", en: "Account", ru: "Кабинет" },
  nav_cart: { uz: "Savat", en: "Cart", ru: "Корзина" },
  nav_orders: { uz: "Buyurtmalar", en: "Orders", ru: "Заказы" },
  nav_admin: { uz: "Admin panel", en: "Admin panel", ru: "Админ панель" },
  search_placeholder: { uz: "Qidirish: o'yin, mahsulot...", en: "Search: games, products...", ru: "Поиск: игры, продукты..." },

  footer_tagline: {
    uz: "Raqamli o'yin bozori — o'yin valyutasi, to'ldirish va raqamli mahsulotlar.",
    en: "Digital gaming marketplace — game currency, top-ups and digital products.",
    ru: "Цифровой игровой маркетплейс — игровая валюта, пополнения и цифровые продукты.",
  },
  footer_market: { uz: "Bozor", en: "Marketplace", ru: "Маркетплейс" },
  footer_help: { uz: "Yordam", en: "Help", ru: "Помощь" },
  footer_trust: { uz: "Ishonch", en: "Trust", ru: "Надёжность" },
  footer_trust_text: {
    uz: "To'lov serverda tekshiriladi. Avtomatik yetkazib berish — faqat real provayder orqali.",
    en: "Payments are verified server-side. Automated delivery only via a real provider.",
    ru: "Оплата проверяется на сервере. Автоматическая выдача — только через реального провайдера.",
  },
  footer_rights: { uz: "Barcha huquqlar himoyalangan.", en: "All rights reserved.", ru: "Все права защищены." },

  // ---- common ----
  loading: { uz: "Yuklanmoqda...", en: "Loading...", ru: "Загрузка..." },
  save: { uz: "Saqlash", en: "Save", ru: "Сохранить" },
  cancel: { uz: "Bekor qilish", en: "Cancel", ru: "Отмена" },
  create: { uz: "Yaratish", en: "Create", ru: "Создать" },
  edit: { uz: "Tahrirlash", en: "Edit", ru: "Изменить" },
  search: { uz: "Qidirish", en: "Search", ru: "Поиск" },
  back: { uz: "Orqaga", en: "Back", ru: "Назад" },
  all: { uz: "Hammasi", en: "All", ru: "Все" },
  actions: { uz: "Amallar", en: "Actions", ru: "Действия" },
  total: { uz: "Jami", en: "Total", ru: "Итого" },
  price: { uz: "Narx", en: "Price", ru: "Цена" },
  quantity: { uz: "Soni", en: "Qty", ru: "Кол-во" },
  date: { uz: "Sana", en: "Date", ru: "Дата" },
  available: { uz: "Mavjud", en: "Available", ru: "Доступно" },
  unavailable: { uz: "Mavjud emas", en: "Unavailable", ru: "Недоступно" },
  not_available: { uz: "MAVJUD EMAS", en: "NOT AVAILABLE", ru: "НЕДОСТУПНО" },
  not_configured: { uz: "SOZLANMAGAN", en: "NOT CONFIGURED", ru: "НЕ НАСТРОЕНО" },
  configured: { uz: "Sozlangan", en: "Configured", ru: "Настроено" },
  connected: { uz: "Ulangan", en: "Connected", ru: "Подключено" },
  next: { uz: "Keyingi", en: "Next", ru: "Далее" },
  prev: { uz: "Oldingi", en: "Prev", ru: "Назад" },
  close: { uz: "Yopish", en: "Close", ru: "Закрыть" },
  apply: { uz: "Qo'llash", en: "Apply", ru: "Применить" },
  retry: { uz: "Qayta urinish", en: "Retry", ru: "Повторить" },
  refresh: { uz: "Yangilash", en: "Refresh", ru: "Обновить" },
  details: { uz: "Batafsil", en: "Details", ru: "Подробнее" },
  status: { uz: "Holat", en: "Status", ru: "Статус" },
  currency: { uz: "Valyuta", en: "Currency", ru: "Валюта" },
  error_generic: { uz: "Xatolik yuz berdi", en: "Something went wrong", ru: "Произошла ошибка" },
  error_network: { uz: "Tarmoq xatoligi", en: "Network error", ru: "Ошибка сети" },
  required: { uz: "Majburiy", en: "Required", ru: "Обязательно" },

  // ---- home ----
  hero_kicker: { uz: "ISHONCHLI RAQAMLI O'YIN BOZORI", en: "TRUSTED DIGITAL GAMING MARKETPLACE", ru: "НАДЁЖНЫЙ ЦИФРОВОЙ ИГРОВОЙ РЫНОК" },
  hero_title_a: { uz: "O'yin valyutasi", en: "Game currency", ru: "Игровая валюта" },
  hero_title_b: { uz: "bir zumda", en: "in an instant", ru: "мгновенно" },
  hero_sub: {
    uz: "UC, Diamond, Gems, Robux va yana ko'p narsalar — avtomatik yetkazib berish, xavfsiz to'lov, 3 tilda qo'llab-quvvatlash.",
    en: "UC, Diamonds, Gems, Robux and more — automated fulfillment, secure payments, support in 3 languages.",
    ru: "UC, Diamonds, Gems, Robux и многое другое — автоматическая выдача, безопасная оплата, поддержка на 3 языках.",
  },
  hero_cta_games: { uz: "O'yinlarni ko'rish", en: "Browse games", ru: "Смотреть игры" },
  hero_cta_support: { uz: "Qanday ishlaydi?", en: "How it works", ru: "Как это работает" },
  hero_stat_games: { uz: "O'yinlar", en: "Games", ru: "Игр" },
  hero_stat_auto: { uz: "Avtomatik yetkazish", en: "Auto fulfillment", ru: "Автовыдача" },
  hero_stat_langs: { uz: "Til", en: "Languages", ru: "Языков" },
  hero_stat_support: { uz: "Qo'llab-quvvatlash", en: "Support", ru: "Поддержка" },

  featured_games: { uz: "Trend o'yinlar", en: "Featured games", ru: "Популярные игры" },
  popular_products: { uz: "Ommabop mahsulotlar", en: "Popular products", ru: "Популярные продукты" },
  categories: { uz: "Kategoriyalar", en: "Categories", ru: "Категории" },
  promotions: { uz: "Aksiyalar", en: "Promotions", ru: "Акции" },
  trust_title: { uz: "Nega VYRON?", en: "Why VYRON?", ru: "Почему VYRON?" },
  trust_secure_t: { uz: "Xavfsiz to'lov", en: "Secure payment", ru: "Безопасная оплата" },
  trust_secure_d: {
    uz: "To'lov faqat serverda tekshirilgan webhook orqali tasdiqlanadi.",
    en: "Payments are only confirmed by verified server-side webhooks.",
    ru: "Оплата подтверждается только проверенными серверными вебхуками.",
  },
  trust_fast_t: { uz: "Tez yetkazish", en: "Fast delivery", ru: "Быстрая выдача" },
  trust_fast_d: {
    uz: "To'lov tasdiqlanishi bilan buyurtma avtomatik bajariladi.",
    en: "The order is fulfilled automatically once payment is verified.",
    ru: "Заказ выполняется автоматически после подтверждения оплаты.",
  },
  trust_support_t: { uz: "3 tilda yordam", en: "Support in 3 languages", ru: "Поддержка на 3 языках" },
  trust_support_d: {
    uz: "O'zbek, ingliz va rus tillarida to'liq interfeys va yordam.",
    en: "Full UI and help in Uzbek, English and Russian.",
    ru: "Полный интерфейс и помощь на узбекском, английском и русском.",
  },
  trust_real_t: { uz: "Real katalog", en: "Real catalog", ru: "Реальный каталог" },
  trust_real_d: {
    uz: "Mahsulotlar faqat real yetkazib beruvchi katalogidan keladi.",
    en: "Products only come from the real supplier catalog.",
    ru: "Продукты поступают только из реального каталога поставщика.",
  },
  view_all: { uz: "Barchasi →", en: "View all →", ru: "Все →" },
  no_products_yet: {
    uz: "Mahsulotlar yetkazib beruvchi katalogi sinxronizatsiyasidan keyin paydo bo'ladi.",
    en: "Products appear after the supplier catalog is synchronized.",
    ru: "Продукты появятся после синхронизации каталога поставщика.",
  },
  catalog_sync_note: {
    uz: "Katalog real Payerpin katalogi bilan sinxronizatsiya qilinadi. Soxta narxlar va mahsulotlar yo'q.",
    en: "The catalog syncs with the real Payerpin catalog. No fake prices or products.",
    ru: "Каталог синхронизируется с реальным каталогом Payerpin. Никаких фальшивых цен.",
  },
  supplier_banner_auto: { uz: "Avtomatik yetkazib berish faol", en: "Automated fulfillment active", ru: "Автоматическая выдача активна" },
  supplier_banner_off: {
    uz: "Yetkazib beruvchi ulanmagan — mahsulotlar hozircha sotilmaydi.",
    en: "Supplier not connected — products are not for sale yet.",
    ru: "Поставщик не подключён — продукты пока не продаются.",
  },

  cat_mobile: { uz: "Mobil o'yinlar", en: "Mobile games", ru: "Мобильные игры" },
  cat_pc: { uz: "PC o'yinlar", en: "PC games", ru: "PC игры" },
  cat_console: { uz: "Konsol", en: "Console", ru: "Консоли" },
  cat_gift: { uz: "Sovg'a kartalari", en: "Gift cards", ru: "Подарочные карты" },
  cat_digital: { uz: "Raqamli mahsulotlar", en: "Digital products", ru: "Цифровые продукты" },

  // ---- game / product ----
  products: { uz: "Mahsulotlar", en: "Products", ru: "Продукты" },
  choose_variant: { uz: "Paketni tanlang", en: "Choose a package", ru: "Выберите пакет" },
  buy: { uz: "Sotib olish", en: "Buy", ru: "Купить" },
  add_to_cart: { uz: "Savatga qo'shish", en: "Add to cart", ru: "В корзину" },
  faq: { uz: "Savol-javob", en: "FAQ", ru: "Вопросы" },
  how_to_buy: { uz: "Qanday buyurtma beriladi", en: "How to order", ru: "Как заказать" },
  how_to_buy_text: {
    uz: "1. Paketni tanlang. 2. O'yinchi ma'lumotlarini kiriting. 3. Savatga qo'shing. 4. To'lovni tasdiqlang — buyurtma avtomatik bajariladi.",
    en: "1. Pick a package. 2. Enter player information. 3. Add to cart. 4. Confirm payment — the order is fulfilled automatically.",
    ru: "1. Выберите пакет. 2. Введите данные игрока. 3. Добавьте в корзину. 4. Подтвердите оплату — заказ выполняется автоматически.",
  },
  player_info: { uz: "O'yinchi ma'lumotlari", en: "Player information", ru: "Данные игрока" },
  player_info_hint: {
    uz: "Faqat o'yin uchun kerakli ma'lumotlar so'raladi. Ma'lumotlar xavfsiz maskalanadi.",
    en: "Only the information required by the game is requested. Data is securely masked.",
    ru: "Запрашиваются только данные, необходимые для игры. Данные маскируются.",
  },
  from_price: { uz: "dan", en: "from", ru: "от" },
  currently_unavailable: { uz: "HOZIRCHA MAVJUD EMAS", en: "CURRENTLY UNAVAILABLE", ru: "ВРЕМЕННО НЕДОСТУПНО" },
  game_not_found: { uz: "O'yin topilmadi", en: "Game not found", ru: "Игра не найдена" },
  product_not_found: { uz: "Mahsulot topilmadi", en: "Product not found", ru: "Продукт не найден" },
  select_variant_first: { uz: "Avval paketni tanlang", en: "Select a package first", ru: "Сначала выберите пакет" },
  added_to_cart: { uz: "Savatga qo'shildi ✓", en: "Added to cart ✓", ru: "Добавлено в корзину ✓" },

  // ---- cart ----
  cart_title: { uz: "Savat", en: "Shopping cart", ru: "Корзина" },
  cart_empty: { uz: "Savatingiz bo'sh", en: "Your cart is empty", ru: "Корзина пуста" },
  cart_empty_sub: { uz: "O'yinlarni ko'rib, sevimli paketni tanlang.", en: "Browse games and pick your package.", ru: "Выберите игру и пакет." },
  subtotal: { uz: "Oraliq jami", en: "Subtotal", ru: "Сумма" },
  discount: { uz: "Chegirma", en: "Discount", ru: "Скидка" },
  coupon_placeholder: { uz: "Promokod", en: "Coupon code", ru: "Промокод" },
  apply_coupon: { uz: "Qo'llash", en: "Apply", ru: "Применить" },
  checkout: { uz: "Buyurtma berish", en: "Checkout", ru: "Оформить" },
  remove: { uz: "O'chirish", en: "Remove", ru: "Удалить" },
  clear_cart: { uz: "Savatni tozalash", en: "Clear cart", ru: "Очистить корзину" },
  cart_invalid: { uz: "Savatda mavjud bo'lmagan mahsulot bor", en: "Cart has unavailable items", ru: "В корзине есть недоступные товары" },

  // ---- checkout ----
  checkout_title: { uz: "Buyurtmani tasdiqlash", en: "Confirm order", ru: "Подтверждение заказа" },
  confirm_pay: { uz: "To'lovga o'tish", en: "Proceed to payment", ru: "Перейти к оплате" },
  payment_not_configured_msg: {
    uz: "To'lov tizimi sozlanmagan. Administratorga murojaat qiling.",
    en: "Payment is not configured. Please contact the administrator.",
    ru: "Оплата не настроена. Обратитесь к администратору.",
  },
  order_summary: { uz: "Buyurtma tarkibi", en: "Order summary", ru: "Состав заказа" },
  coupon_applied: { uz: "Promokod qo'llandi ✓", en: "Coupon applied ✓", ru: "Промокод применён ✓" },

  // ---- orders ----
  orders_title: { uz: "Buyurtmalarim", en: "My orders", ru: "Мои заказы" },
  order_number: { uz: "Buyurtma", en: "Order", ru: "Заказ" },
  order_detail: { uz: "Buyurtma tafsilotlari", en: "Order details", ru: "Детали заказа" },
  no_orders: { uz: "Hali buyurtmalar yo'q", en: "No orders yet", ru: "Заказов пока нет" },
  no_orders_sub: { uz: "Birinchi buyurtmangizni bering!", en: "Place your first order!", ru: "Оформите первый заказ!" },
  payment_status: { uz: "To'lov", en: "Payment", ru: "Оплата" },
  fulfillment_status: { uz: "Yetkazish", en: "Fulfillment", ru: "Выдача" },
  order_refresh_note: {
    uz: "Holat avtomatik yangilanadi",
    en: "Status refreshes automatically",
    ru: "Статус обновляется автоматически",
  },

  // statuses
  st_PENDING_PAYMENT: { uz: "To'lov kutilmoqda", en: "Pending payment", ru: "Ожидает оплаты" },
  st_PAID: { uz: "To'landi", en: "Paid", ru: "Оплачен" },
  st_FULFILLMENT_PENDING: { uz: "Bajarilmoqda", en: "Processing", ru: "В обработке" },
  st_SUPPLIER_PROCESSING: { uz: "Yetkazib beruvchi bajarayapti", en: "Supplier processing", ru: "У поставщика" },
  st_COMPLETED: { uz: "Bajarildi", en: "Completed", ru: "Выполнен" },
  st_FAILED: { uz: "Bajarilmadi", en: "Failed", ru: "Ошибка" },
  st_REFUNDED: { uz: "Qaytarildi", en: "Refunded", ru: "Возврат" },
  st_CANCELLED: { uz: "Bekor qilindi", en: "Cancelled", ru: "Отменён" },
  st_PENDING: { uz: "Kutilmoqda", en: "Pending", ru: "Ожидание" },
  st_PROCESSING: { uz: "Jarayonda", en: "Processing", ru: "В процессе" },
  st_AWAITING_STATUS: { uz: "Javob kutilmoqda", en: "Awaiting status", ru: "Ожидание статуса" },

  // ---- auth ----
  login: { uz: "Kirish", en: "Login", ru: "Вход" },
  register: { uz: "Ro'yxatdan o'tish", en: "Register", ru: "Регистрация" },
  username: { uz: "Foydalanuvchi nomi", en: "Username", ru: "Имя пользователя" },
  email: { uz: "Email", en: "Email", ru: "Email" },
  password: { uz: "Parol", en: "Password", ru: "Пароль" },
  logout: { uz: "Chiqish", en: "Logout", ru: "Выйти" },
  login_title: { uz: "Xush kelibsiz", en: "Welcome back", ru: "С возвращением" },
  register_title: { uz: "Hisob yaratish", en: "Create account", ru: "Создать аккаунт" },
  no_account: { uz: "Hisobingiz yo'qmi?", en: "No account?", ru: "Нет аккаунта?" },
  have_account: { uz: "Hisobingiz bormi?", en: "Have an account?", ru: "Есть аккаунт?" },
  telegram_login: { uz: "Telegram orqali kirish", en: "Login with Telegram", ru: "Войти через Telegram" },
  telegram_only_webapp: {
    uz: "Telegram orqali kirish faqat Telegram WebApp ichida ishlaydi.",
    en: "Telegram login only works inside the Telegram WebApp.",
    ru: "Вход через Telegram работает только внутри Telegram WebApp.",
  },
  invalid_credentials: { uz: "Login yoki parol noto'g'ri", en: "Invalid username or password", ru: "Неверное имя или пароль" },
  user_exists: { uz: "Bu foydalanuvchi allaqachon mavjud", en: "User already exists", ru: "Пользователь уже существует" },
  password_too_short: { uz: "Parol kamida 8 ta belgidan iborat bo'lsin", en: "Password must be at least 8 characters", ru: "Пароль минимум 8 символов" },
  password_too_simple: { uz: "Parol murakkabroq bo'lsin (harf + raqam)", en: "Password too simple (letters + digits)", ru: "Слишком простой пароль (буквы + цифры)" },
  invalid_username: { uz: "Noto'g'ri foydalanuvchi nomi", en: "Invalid username", ru: "Неверное имя пользователя" },
  account_locked: { uz: "Hisob vaqtincha bloklangan", en: "Account temporarily locked", ru: "Аккаунт временно заблокирован" },
  register_ok: { uz: "Hisob yaratildi ✓", en: "Account created ✓", ru: "Аккаунт создан ✓" },
  login_ok: { uz: "Xush kelibsiz ✓", en: "Welcome ✓", ru: "Добро пожаловать ✓" },

  // ---- account ----
  profile: { uz: "Profil", en: "Profile", ru: "Профиль" },
  personal_info: { uz: "Shaxsiy ma'lumot", en: "Personal information", ru: "Личные данные" },
  order_history: { uz: "Buyurtmalar tarixi", en: "Order history", ru: "История заказов" },
  active_orders: { uz: "Faol buyurtmalar", en: "Active orders", ru: "Активные заказы" },
  completed_orders: { uz: "Bajarilgan", en: "Completed", ru: "Выполненные" },
  failed_orders: { uz: "Muvaffaqiyatsiz", en: "Failed", ru: "Неудачные" },
  security: { uz: "Xavfsizlik", en: "Security", ru: "Безопасность" },
  language: { uz: "Til", en: "Language", ru: "Язык" },
  theme: { uz: "Mavzu", en: "Theme", ru: "Тема" },
  theme_day: { uz: "Kun", en: "Day", ru: "День" },
  theme_night: { uz: "Tun", en: "Night", ru: "Ночь" },
  notifications: { uz: "Bildirishnomalar", en: "Notifications", ru: "Уведомления" },
  mark_all_read: { uz: "Hammasini o'qilgan qilish", en: "Mark all read", ru: "Прочитать все" },
  no_notifications: { uz: "Bildirishnomalar yo'q", en: "No notifications", ru: "Нет уведомлений" },
  save_changes: { uz: "O'zgarishlarni saqlash", en: "Save changes", ru: "Сохранить изменения" },
  saved: { uz: "Saqlandi ✓", en: "Saved ✓", ru: "Сохранено ✓" },
  telegram_linked: { uz: "Telegram ulangan", en: "Telegram linked", ru: "Telegram привязан" },
  telegram_not_linked: { uz: "Telegram ulanmagan", en: "Telegram not linked", ru: "Telegram не привязан" },
  member_since: { uz: "A'zo bo'lgan sana", en: "Member since", ru: "Дата регистрации" },
  masked_note: {
    uz: "O'yinchi ma'lumotlari maskalangan",
    en: "Player information is masked",
    ru: "Данные игрока замаскированы",
  },

  // ---- support ----
  support_title: { uz: "Yordam markazi", en: "Help center", ru: "Центр помощи" },

  // ---- admin ----
  admin_title: { uz: "Boshqaruv paneli", en: "Admin dashboard", ru: "Панель управления" },
  admin_denied: { uz: "Ruxsat yo'q", en: "Access denied", ru: "Доступ запрещён" },
  admin_denied_sub: {
    uz: "Bu sahifa faqat administratorlar uchun.",
    en: "This page is for administrators only.",
    ru: "Страница только для администраторов.",
  },
  a_dashboard: { uz: "Dashboard", en: "Dashboard", ru: "Дашборд" },
  a_users: { uz: "Foydalanuvchilar", en: "Users", ru: "Пользователи" },
  a_games: { uz: "O'yinlar", en: "Games", ru: "Игры" },
  a_products: { uz: "Mahsulotlar", en: "Products", ru: "Продукты" },
  a_variants: { uz: "Variantlar", en: "Variants", ru: "Варианты" },
  a_orders: { uz: "Buyurtmalar", en: "Orders", ru: "Заказы" },
  a_payments: { uz: "To'lovlar", en: "Payments", ru: "Платежи" },
  a_fulfillments: { uz: "Bajarishlar", en: "Fulfillments", ru: "Выдачи" },
  a_payerpin: { uz: "Payerpin", en: "Payerpin", ru: "Payerpin" },
  a_pricing: { uz: "Narxlar", en: "Pricing", ru: "Цены" },
  a_promotions: { uz: "Aksiyalar", en: "Promotions", ru: "Акции" },
  a_coupons: { uz: "Kuponlar", en: "Coupons", ru: "Купоны" },
  a_analytics: { uz: "Analitika", en: "Analytics", ru: "Аналитика" },
  a_notifications: { uz: "Bildirishnomalar", en: "Notifications", ru: "Уведомления" },
  a_telegram: { uz: "Telegram", en: "Telegram", ru: "Telegram" },
  a_security: { uz: "Xavfsizlik", en: "Security", ru: "Безопасность" },
  a_audit: { uz: "Audit jurnali", en: "Audit logs", ru: "Журнал аудита" },
  a_health: { uz: "Tizim holati", en: "System health", ru: "Состояние системы" },
  a_settings: { uz: "Sozlamalar", en: "Settings", ru: "Настройки" },

  a_users_total: { uz: "Foydalanuvchilar", en: "Users", ru: "Пользователи" },
  a_orders_total: { uz: "Buyurtmalar", en: "Orders", ru: "Заказы" },
  a_orders_24h: { uz: "24 soatlik buyurtmalar", en: "Orders 24h", ru: "Заказов за 24ч" },
  a_revenue: { uz: "Tushum", en: "Revenue", ru: "Выручка" },
  a_profit: { uz: "Foyda", en: "Profit", ru: "Прибыль" },
  a_pending: { uz: "Kutilayotgan", en: "Pending", ru: "Ожидают" },
  a_processing: { uz: "Jarayonda", en: "Processing", ru: "В процессе" },
  a_completed: { uz: "Bajarilgan", en: "Completed", ru: "Выполнено" },
  a_failed: { uz: "Muvaffaqiyatsiz", en: "Failed", ru: "Ошибок" },
  a_active_products: { uz: "Faol mahsulotlar", en: "Active products", ru: "Активных продуктов" },
  a_recent_orders: { uz: "So'nggi buyurtmalar", en: "Recent orders", ru: "Последние заказы" },

  test_connection: { uz: "Ulanishni tekshirish", en: "Test connection", ru: "Проверить соединение" },
  sync_catalog: { uz: "Katalogni sinxronlash", en: "Sync catalog", ru: "Синхронизировать каталог" },
  check_balance: { uz: "Balansni tekshirish", en: "Check balance", ru: "Проверить баланс" },
  connection_status: { uz: "Ulanish holati", en: "Connection status", ru: "Статус подключения" },
  api_key_configured: { uz: "API kalit", en: "API key", ru: "API ключ" },
  balance: { uz: "Balans", en: "Balance", ru: "Баланс" },
  last_sync: { uz: "Oxirgi sinxronizatsiya", en: "Last sync", ru: "Последняя синхронизация" },
  last_success_request: { uz: "Oxirgi muvaffaqiyatli so'rov", en: "Last successful request", ru: "Последний успешный запрос" },
  last_failed_request: { uz: "Oxirgi xato so'rov", en: "Last failed request", ru: "Последний неудачный запрос" },
  pending_fulfillments: { uz: "Bajarish kutilmoqda", en: "Pending fulfillments", ru: "Ожидают выдачи" },
  failed_fulfillments: { uz: "Muvaffaqiyatsiz bajarishlar", en: "Failed fulfillments", ru: "Неудачные выдачи" },
  completed_supplier_orders: { uz: "Bajarilgan yetkazib beruvchi buyurtmalari", en: "Completed supplier orders", ru: "Выполненные заказы поставщика" },
  connection_successful: { uz: "Ulanish muvaffaqiyatli ✓", en: "Connection successful ✓", ru: "Соединение успешно ✓" },
  connection_failed: { uz: "Ulanish muvaffaqiyatsiz", en: "Connection failed", ru: "Ошибка соединения" },
  sync_done: { uz: "Sinxronizatsiya yakunlandi ✓", en: "Sync complete ✓", ru: "Синхронизация завершена ✓" },
  sync_report: { uz: "O'yinlar: {games} · Mahsulotlar: {products} · Variantlar: {variants}", en: "Games: {games} · Products: {products} · Variants: {variants}", ru: "Игр: {games} · Продуктов: {products} · Вариантов: {variants}" },
  low_balance: { uz: "Past balans ogohlantirishi", en: "Low balance warning", ru: "Предупреждение о низком балансе" },
  never_shows_key: {
    uz: "API kalit hech qachon ko'rsatilmaydi — faqat sozlangan/sozlanmagan holati.",
    en: "The API key is never displayed — only configured / not configured.",
    ru: "API-ключ никогда не отображается — только статус настройки.",
  },

  a_margin_percent: { uz: "Margin %", en: "Margin %", ru: "Маржа %" },
  a_margin_fixed: { uz: "Margin (qat'iy)", en: "Margin (fixed)", ru: "Маржа (фикс.)" },
  a_fee_percent: { uz: "To'lov haqi %", en: "Payment fee %", ru: "Комиссия %" },
  a_fee_fixed: { uz: "To'lov haqi (qat'iy)", en: "Payment fee (fixed)", ru: "Комиссия (фикс.)" },
  a_min_margin: { uz: "Min. margin %", en: "Min margin %", ru: "Мин. маржа %" },
  a_pricing_note: {
    uz: "Narx = yetkazib beruvchi narxi + to'lov haqi + VYRON margin. Yetkazib beruvchi narxi mijozlarga ko'rsatilmaydi.",
    en: "Price = supplier cost + payment fee + VYRON margin. Supplier cost is never shown to customers.",
    ru: "Цена = цена поставщика + комиссия + маржа VYRON. Цена поставщика не показывается покупателям.",
  },
  a_recalc_note: { uz: "Barcha variant narxlari qayta hisoblanadi.", en: "All variant prices will be recalculated.", ru: "Все цены вариантов будут пересчитаны." },

  a_code: { uz: "Kod", en: "Code", ru: "Код" },
  a_type: { uz: "Turi", en: "Type", ru: "Тип" },
  a_value: { uz: "Qiymat", en: "Value", ru: "Значение" },
  a_min_order: { uz: "Min. buyurtma", en: "Min order", ru: "Мин. заказ" },
  a_max_uses: { uz: "Maks. foydalanish", en: "Max uses", ru: "Макс. использований" },
  a_used: { uz: "Ishlatilgan", en: "Used", ru: "Использовано" },
  a_per_user: { uz: "Har bir foydalanuvchi uchun", en: "Per user", ru: "На пользователя" },
  a_expires: { uz: "Muddati", en: "Expires", ru: "Истекает" },
  a_active: { uz: "Faol", en: "Active", ru: "Активен" },
  a_percent: { uz: "Foiz", en: "Percent", ru: "Процент" },
  a_fixed: { uz: "Qat'iy", en: "Fixed", ru: "Фикс." },

  a_user: { uz: "Foydalanuvchi", en: "User", ru: "Пользователь" },
  a_role: { uz: "Rol", en: "Role", ru: "Роль" },
  a_supplier_cost: { uz: "Yetkazib beruvchi narxi", en: "Supplier cost", ru: "Себестоимость" },
  a_profit_line: { uz: "Foyda", en: "Profit", ru: "Прибыль" },
  a_supplier_mapping: { uz: "Yetkazib beruvchi mapping", en: "Supplier mapping", ru: "Маппинг поставщика" },
  a_mapped: { uz: "Ulangan", en: "Mapped", ru: "Привязан" },
  a_unmapped: { uz: "Ulanmagan", en: "Not mapped", ru: "Не привязан" },
  a_product_name: { uz: "Mahsulot nomi", en: "Product name", ru: "Название продукта" },
  a_game: { uz: "O'yin", en: "Game", ru: "Игра" },
  a_image_url: { uz: "Rasm URL", en: "Image URL", ru: "URL изображения" },
  a_required_fields: { uz: "Kerakli maydonlar (JSON)", en: "Required fields (JSON)", ru: "Обязательные поля (JSON)" },
  a_save_ok: { uz: "Saqlandi ✓", en: "Saved ✓", ru: "Сохранено ✓" },
  a_cancelled: { uz: "Bekor qilindi ✓", en: "Cancelled ✓", ru: "Отменено ✓" },
  a_retried: { uz: "Qayta ishga tushirildi ✓", en: "Retry scheduled ✓", ru: "Повтор запланирован ✓" },
  a_refunded: { uz: "Qaytarildi ✓", en: "Refunded ✓", ru: "Возврат выполнен ✓" },

  a_check_database: { uz: "Baza", en: "Database", ru: "База данных" },
  a_check_payment: { uz: "To'lov", en: "Payment", ru: "Оплата" },
  a_check_payerpin: { uz: "Payerpin", en: "Payerpin", ru: "Payerpin" },
  a_check_telegram: { uz: "Telegram", en: "Telegram", ru: "Telegram" },
  a_check_auth: { uz: "Autentifikatsiya", en: "Auth", ru: "Авторизация" },
  a_check_webhooks: { uz: "Webhooklar", en: "Webhooks", ru: "Вебхуки" },
  a_check_storage: { uz: "Saqlash", en: "Storage", ru: "Хранилище" },

  a_broadcast: { uz: "Barchaga yuborish", en: "Broadcast", ru: "Рассылка" },
  a_broadcast_title: { uz: "Bildirishnoma yuborish", en: "Send notification", ru: "Отправить уведомление" },
  a_broadcast_hint: {
    uz: "Barcha faol foydalanuvchilarga in-app + Telegram xabar.",
    en: "In-app + Telegram message to all active users.",
    ru: "In-app + Telegram сообщение всем активным пользователям.",
  },
  a_sent: { uz: "Yuborildi: {n}", en: "Sent: {n}", ru: "Отправлено: {n}" },

  a_admin_actions: { uz: "So'nggi admin amallari", en: "Recent admin actions", ru: "Последние действия админов" },
  a_failed_webhooks: { uz: "Yaroqsiz webhooklar", en: "Invalid webhooks", ru: "Неверные вебхуки" },
  a_locked_accounts: { uz: "Bloklangan hisoblar", en: "Locked accounts", ru: "Заблокированные аккаунты" },

  a_top_products: { uz: "Top mahsulotlar", en: "Top products", ru: "Топ продуктов" },
  a_revenue_chart: { uz: "Tushum (kunlar)", en: "Revenue (daily)", ru: "Выручка (по дням)" },

  a_setting_general: { uz: "Umumiy sozlamalar", en: "General settings", ru: "Общие настройки" },
  a_support_link: { uz: "Qo'llab-quvvatlash havolasi", en: "Support link", ru: "Ссылка поддержки" },
  a_announcement: { uz: "E'lon", en: "Announcement", ru: "Объявление" },

  // error keys (server)
  cart_empty: { uz: "Savat bo'sh", en: "Cart is empty", ru: "Корзина пуста" },
  product_unavailable: { uz: "Mahsulot mavjud emas", en: "Product unavailable", ru: "Продукт недоступен" },
  variant_unavailable: { uz: "Paket mavjud emas", en: "Package unavailable", ru: "Пакет недоступен" },
  not_available_err: { uz: "Hozircha mavjud emas", en: "Not available yet", ru: "Пока недоступно" },
  coupon_invalid: { uz: "Promokod noto'g'ri", en: "Invalid coupon", ru: "Неверный промокод" },
  coupon_expired: { uz: "Promokod muddati tugagan", en: "Coupon expired", ru: "Промокод истёк" },
  coupon_exhausted: { uz: "Promokod tugagan", en: "Coupon exhausted", ru: "Промокод исчерпан" },
  coupon_user_limit: { uz: "Promokod limiti tugagan", en: "Coupon user limit reached", ru: "Лимит промокода исчерпан" },
  coupon_min_order: { uz: "Minimal buyurtma summasi yetarli emas", en: "Minimum order amount not met", ru: "Минимальная сумма заказа не достигнута" },
  payment_not_configured: { uz: "To'lov sozlanmagan", en: "Payment is not configured", ru: "Оплата не настроена" },
  unauthorized: { uz: "Avval kiring", en: "Please log in", ru: "Войдите в аккаунт" },
  forbidden: { uz: "Ruxsat yo'q", en: "Forbidden", ru: "Доступ запрещён" },
  rate_limited: { uz: "Juda ko'p urinishlar. Kuting.", en: "Too many attempts. Please wait.", ru: "Слишком много попыток. Подождите." },
  missing_field: { uz: "Maydon to'ldirilmagan", en: "Required field missing", ru: "Обязательное поле не заполнено" },
  invalid_field: { uz: "Maydon noto'g'ri", en: "Invalid field value", ru: "Неверное значение поля" },
  order_not_found: { uz: "Buyurtma topilmadi", en: "Order not found", ru: "Заказ не найден" },
  item_not_found: { uz: "Element topilmadi", en: "Item not found", ru: "Элемент не найден" },
  supplier_not_configured: { uz: "Yetkazib beruvchi sozlanmagan", en: "Supplier is not configured", ru: "Поставщик не настроен" },
  not_configured_err: { uz: "Sozlanmagan", en: "NOT CONFIGURED", ru: "НЕ НАСТРОЕНО" },
};

let current = localStorage.getItem("vyron_lang") || "uz";
const tg = window.Telegram?.WebApp;
if (tg?.initDataUnsafe?.user?.language_code && !localStorage.getItem("vyron_lang")) {
  const code = tg.initDataUnsafe.user.language_code.slice(0, 2);
  if (LANGS.includes(code)) current = code;
}

export function getLang() {
  return current;
}

export function setLang(lang) {
  if (!LANGS.includes(lang)) return;
  current = lang;
  localStorage.setItem("vyron_lang", lang);
  document.documentElement.lang = lang;
}

export function t(key, params) {
  const entry = dict[key];
  let text = entry ? (entry[current] || entry.en || key) : key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replaceAll(`{${k}}`, String(v));
    }
  }
  return text;
}

/** Translate status enums from the API. */
export function tStatus(status) {
  return t(`st_${status}`);
}

/** Translate server error detail keys. */
export function tError(detail) {
  if (!detail) return t("error_generic");
  if (typeof detail === "string" && detail.startsWith("missing_field:")) {
    return `${t("missing_field")}: ${detail.split(":")[1]}`;
  }
  if (typeof detail === "string" && detail.startsWith("invalid_field:")) {
    return `${t("invalid_field")}: ${detail.split(":")[1]}`;
  }
  return t(detail) !== detail ? t(detail) : t("error_generic");
}

export function applyStaticTranslations() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
}
