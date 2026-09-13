// Simple i18n
const translations = {
    uz: {
        "Games": "O'yinlar",
        "Marketplace": "Market",
        "Donations": "Donatlar",
        "Promotions": "Aksiyalar",
        "Support": "Yordam",
        "Login": "Kirish",
        "Register": "Ro'yxatdan o'tish",
        "Logout": "Chiqish",
        "Profile": "Profil",
        "Orders": "Buyurtmalar",
        "Home": "Bosh sahifa",
        "Buy Now": "Sotib olish",
        "Add to Cart": "Savatga qo'shish"
    },
    ru: {
        "Games": "Игры",
        "Marketplace": "Маркетплейс",
        "Donations": "Донаты",
        "Promotions": "Акции",
        "Support": "Поддержка",
        "Login": "Вход",
        "Register": "Регистрация",
        "Logout": "Выход",
        "Profile": "Профиль",
        "Orders": "Заказы",
        "Home": "Главная",
        "Buy Now": "Купить",
        "Add to Cart": "В корзину"
    },
    en: {
        "Games": "Games",
        "Marketplace": "Marketplace",
        "Donations": "Donations",
        "Promotions": "Promotions",
        "Support": "Support",
        "Login": "Login",
        "Register": "Register",
        "Logout": "Logout",
        "Profile": "Profile",
        "Orders": "Orders",
        "Home": "Home",
        "Buy Now": "Buy Now",
        "Add to Cart": "Add to Cart"
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const savedLang = localStorage.getItem('vyron-lang') || 'uz';
    document.documentElement.lang = savedLang;

    document.querySelectorAll('.lang-btn').forEach(btn => {
        if (btn.dataset.lang === savedLang) btn.classList.add('active');
        btn.addEventListener('click', () => {
            const lang = btn.dataset.lang;
            localStorage.setItem('vyron-lang', lang);
            document.documentElement.lang = lang;
            document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            // In real app, would reload translations via API
            location.reload();
        });
    });

    window.t = (key) => {
        const lang = localStorage.getItem('vyron-lang') || 'uz';
        return translations[lang]?.[key] || translations['en']?.[key] || key;
    };
});
