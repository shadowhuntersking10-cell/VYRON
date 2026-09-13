// Theme toggle
document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('themeToggle');
    if (!toggle) return;

    toggle.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme-choice') || 'system';
        let next;
        if (current === 'light') next = 'dark';
        else if (current === 'dark') next = 'system';
        else next = 'light';

        localStorage.setItem('vyron-theme', next);
        document.documentElement.setAttribute('data-theme-choice', next);

        let effective = next;
        if (next === 'system') {
            effective = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        document.documentElement.setAttribute('data-theme', effective);

        // Update meta theme-color
        const meta = document.querySelector('meta[name="theme-color"]');
        if (meta) {
            meta.content = effective === 'dark' ? '#071426' : '#FFFFFF';
        }
    });

    // Listen system change if system theme
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        const choice = document.documentElement.getAttribute('data-theme-choice');
        if (choice === 'system') {
            document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
        }
    });
});
