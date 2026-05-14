/**
 * Sidebar Navigation & Responsive Logic
 */
(function () {
    function initAria() {
        document.querySelectorAll('.nav-item-group').forEach(function (group) {
            var trigger = group.querySelector('.nav-item');
            var sub = group.querySelector('.nav-sub');
            if (!trigger || !sub) return;
            trigger.setAttribute('role', 'button');
            trigger.setAttribute('aria-expanded', sub.classList.contains('open') ? 'true' : 'false');
        });
    }

    // Toggle submenu on click
    function handleSubmenuClick(e) {
        var trigger = e.target.closest('.nav-item-group > .nav-item');
        if (!trigger) return;
        var group = trigger.closest('.nav-item-group');
        var sub = group ? group.querySelector('.nav-sub') : null;
        if (!sub) return;

        e.preventDefault();
        e.stopPropagation();

        var now = Date.now();
        var lastToggle = parseInt(group.getAttribute('data-last-toggle') || '0', 10);
        if (now - lastToggle < 250) {
            return;
        }
        group.setAttribute('data-last-toggle', String(now));

        var isOpen = sub.classList.toggle('open');
        trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    }

    // Global toggle function (legacy/direct support)
    window.toggleNavSub = function(id) {
        const sub = document.getElementById(id);
        if (!sub) return;
        
        const btn = sub.previousElementSibling;
        const isOpen = sub.classList.contains('open');

        if (isOpen) {
            sub.classList.remove('open');
            if(btn) btn.setAttribute('aria-expanded', 'false');
        } else {
            sub.classList.add('open');
            if(btn) btn.setAttribute('aria-expanded', 'true');
        }
    };

    // Show current page name in top bar on desktop
    function updateTopBarTitle() {
        var titleEl = document.getElementById('topBarPageTitle');
        if (!titleEl) return;
        var activeItem = document.querySelector('.sidebar .nav-item.active');
        if (!activeItem) return;
        
        var textSpan = activeItem.querySelector('span.text-capitalize');
        var label = textSpan ? textSpan.textContent.trim() : activeItem.textContent.replace(/[\u{1F300}-\u{1FFFF}]/gu, '').trim();
        var raw = activeItem.textContent.trim();
        var emojiMatch = raw.match(/^([\p{Extended_Pictographic}\uFE0F\u200D]+)/u);
        var emoji = emojiMatch ? emojiMatch[1] : '';
        titleEl.textContent = (emoji ? emoji + ' ' : '') + label;
        
        if (window.innerWidth >= 960) {
            titleEl.style.display = 'flex';
        } else {
            titleEl.style.display = 'none';
        }
    }

    // Responsive Sidebar Logic
    function initResponsiveSidebar() {
        const hamburger = document.getElementById('hamburgerBtn');
        const overlay = document.getElementById('sidebarOverlay');
        const sidebar = document.getElementById('appSidebar');
        const navItems = sidebar ? sidebar.querySelectorAll('.nav-item') : [];

        function openSidebar() {
            if (window.innerWidth > 900) return;
            document.body.classList.add('sidebar-open');
            if (overlay) overlay.classList.add('open');
            if (hamburger) hamburger.setAttribute('aria-expanded', 'true');
            try {
                if (sidebar) { sidebar.inert = false; sidebar.removeAttribute('inert'); sidebar.setAttribute('aria-hidden', 'false'); }
                if (overlay) { overlay.inert = false; overlay.removeAttribute('inert'); overlay.setAttribute('aria-hidden', 'false'); }
            } catch (e) {
                if (sidebar) sidebar.setAttribute('aria-hidden', 'false');
                if (overlay) overlay.setAttribute('aria-hidden', 'false');
            }
        }

        function closeSidebar() {
            if (window.innerWidth > 900) {
                document.body.classList.remove('sidebar-open');
                if (sidebar) { sidebar.inert = false; sidebar.removeAttribute('inert'); sidebar.setAttribute('aria-hidden', 'false'); sidebar.classList.remove('open'); }
                if (overlay) { overlay.classList.remove('open'); overlay.setAttribute('aria-hidden', 'true'); }
                return;
            }
            document.body.classList.remove('sidebar-open');
            if (sidebar) sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('open');
            if (hamburger) hamburger.setAttribute('aria-expanded', 'false');
            try {
                var active = document.activeElement;
                if (sidebar && active && sidebar.contains(active)) {
                    if (hamburger && typeof hamburger.focus === 'function') hamburger.focus();
                    else document.body.focus();
                }
            } catch (e) {}
            setTimeout(function () {
                if (window.innerWidth > 900) return;
                try {
                    if (sidebar) { sidebar.inert = true; sidebar.setAttribute('aria-hidden', 'true'); }
                    if (overlay) { overlay.inert = true; overlay.setAttribute('aria-hidden', 'true'); }
                } catch (e) {
                    if (sidebar) sidebar.setAttribute('aria-hidden', 'true');
                    if (overlay) overlay.setAttribute('aria-hidden', 'true');
                }
            }, 0);
        }

        if (hamburger) {
            hamburger.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                const open = document.body.classList.contains('sidebar-open');
                if (open) closeSidebar(); else openSidebar();
            });
        }
        
        // Ensure sidebar has 'open' class when body has 'sidebar-open'
        function syncSidebarClass() {
            if (sidebar) {
                if (document.body.classList.contains('sidebar-open')) {
                    sidebar.classList.add('open');
                } else {
                    sidebar.classList.remove('open');
                }
            }
        }
        
        // Observer to sync classes if needed (fallback)
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.attributeName === 'class' && mutation.target === document.body) {
                    syncSidebarClass();
                }
            });
        });
        observer.observe(document.body, { attributes: true });

        if (overlay) {
            overlay.addEventListener('click', function () { if (window.innerWidth <= 900) closeSidebar(); });
        }
        navItems.forEach(item => item.addEventListener('click', function() {
            if (window.innerWidth <= 900) closeSidebar();
        }));
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && window.innerWidth <= 900) closeSidebar();
        });

        window.addEventListener('resize', function () {
            try {
                if (window.innerWidth <= 900) {
                    closeSidebar();
                } else {
                    document.body.classList.remove('sidebar-open');
                    try {
                        if (sidebar) { sidebar.inert = false; sidebar.removeAttribute('inert'); sidebar.setAttribute('aria-hidden', 'false'); }
                        if (overlay) { overlay.inert = true; overlay.setAttribute('aria-hidden', 'true'); overlay.classList.remove('open'); }
                    } catch (e) {
                        if (sidebar) sidebar.setAttribute('aria-hidden', 'false');
                        if (overlay) overlay.setAttribute('aria-hidden', 'true');
                    }
                }
            } catch (e) {}
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        initAria();
        updateTopBarTitle();
        initResponsiveSidebar();
    });
    
    document.addEventListener('click', handleSubmenuClick, true);
    window.addEventListener('resize', updateTopBarTitle);
})();
