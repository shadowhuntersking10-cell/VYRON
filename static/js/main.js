// VYRON Main JS

document.addEventListener('DOMContentLoaded', () => {
    // Mobile menu
    const toggle = document.getElementById('mobileMenuToggle');
    const nav = document.getElementById('mobileNav');
    if (toggle && nav) {
        toggle.addEventListener('click', () => {
            nav.classList.toggle('open');
        });
    }

    // Bottom nav active
    const path = window.location.pathname;
    document.querySelectorAll('.bottom-nav-item').forEach(item => {
        const active = item.getAttribute('data-active');
        if (active && path.startsWith(active)) {
            item.classList.add('active');
        }
        if (path === '/' && active === '/') {
            item.classList.add('active');
        }
    });

    // Toast helper
    window.showToast = (message, type = 'info') => {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span>${type === 'error' ? '❌' : type === 'success' ? '✅' : 'ℹ️'}</span>
            <span>${message}</span>
        `;
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    };

    // Form handling with loading states
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', (e) => {
            const btn = form.querySelector('button[type="submit"]');
            if (btn) {
                btn.disabled = true;
                const original = btn.innerHTML;
                btn.innerHTML = '<span class="loading-spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px;"></span> Loading...';
                // Re-enable after 3s if not redirected
                setTimeout(() => {
                    btn.disabled = false;
                    btn.innerHTML = original;
                }, 3000);
            }
        });
    });

    // Lazy loading images
    if ('IntersectionObserver' in window) {
        const imgObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                    }
                    imgObserver.unobserve(img);
                }
            });
        });
        
        document.querySelectorAll('img[data-src]').forEach(img => {
            imgObserver.observe(img);
        });
    }

    // Copy coupon
    window.copyCoupon = (code) => {
        navigator.clipboard.writeText(code).then(() => {
            showToast(`Copied ${code}`, 'success');
        });
    };

    // Favorites
    window.toggleFavorite = async (type, id) => {
        try {
            const res = await fetch('/api/favorites/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({entity_type: type, entity_id: id})
            });
            const data = await res.json();
            if (data.success) {
                showToast('Added to favorites', 'success');
            } else {
                showToast(data.detail || 'Failed', 'error');
            }
        } catch (e) {
            showToast('Error', 'error');
        }
    };

    // Checkout
    window.proceedCheckout = async () => {
        const items = JSON.parse(localStorage.getItem('cart') || '[]');
        if (!items.length) {
            showToast('Cart is empty', 'error');
            return;
        }
        
        const gameData = {};
        document.querySelectorAll('[data-game-field]').forEach(input => {
            gameData[input.getAttribute('data-game-field')] = input.value;
        });

        try {
            const res = await fetch('/api/orders/checkout', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    items: items,
                    payment_provider: document.querySelector('input[name="payment_provider"]:checked')?.value || 'PAYME',
                    game_data: gameData,
                    coupon_code: document.getElementById('couponCode')?.value || null
                })
            });
            const data = await res.json();
            if (data.success) {
                localStorage.removeItem('cart');
                window.location.href = `/orders`;
            } else {
                showToast(data.detail || 'Checkout failed', 'error');
            }
        } catch (e) {
            showToast('Checkout error', 'error');
        }
    };

    // Telegram WebApp integration
    if (window.Telegram && window.Telegram.WebApp) {
        const tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();
        
        // Apply theme
        if (tg.colorScheme === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
        }
        
        // Haptic
        window.tgHaptic = (type = 'light') => {
            try {
                tg.HapticFeedback.impactOccurred(type);
            } catch {}
        };

        // Main button helper
        window.tgMainButton = (text, onClick) => {
            tg.MainButton.setText(text);
            tg.MainButton.show();
            tg.MainButton.onClick(onClick);
        };

        // Back button
        if (tg.BackButton) {
            tg.BackButton.onClick(() => {
                history.back();
            });
        }

        // Authenticate with backend using initData
        const initData = tg.initData;
        if (initData) {
            fetch('/api/auth/telegram', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({initData})
            }).then(r => r.json()).then(data => {
                if (data.success) {
                    console.log('Telegram auth success');
                }
            }).catch(e => console.error('Telegram auth failed', e));
        }
    }
});

// Cart helpers
window.addToCart = (productId, quantity = 1) => {
    let cart = JSON.parse(localStorage.getItem('cart') || '[]');
    const existing = cart.find(i => i.product_id === productId);
    if (existing) {
        existing.quantity += quantity;
    } else {
        cart.push({product_id: productId, quantity});
    }
    localStorage.setItem('cart', JSON.stringify(cart));
    if (window.showToast) showToast('Added to cart', 'success');
    if (window.tgHaptic) window.tgHaptic('light');
};

window.getCart = () => JSON.parse(localStorage.getItem('cart') || '[]');
