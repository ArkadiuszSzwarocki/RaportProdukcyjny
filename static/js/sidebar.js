/**
 * Sidebar Navigation & Responsive Logic
 */
(function () {
    const SIDEBAR_STATE_KEY = 'sidebar_submenus_state';
    const SIDEBAR_SCROLL_KEY = 'sidebar_scroll_pos';

    function initAria() {
        document.querySelectorAll('.nav-item-group').forEach(function (group) {
            var trigger = group.querySelector('.nav-item');
            var sub = group.querySelector('.nav-sub');
            if (!trigger || !sub) return;
            trigger.setAttribute('role', 'button');
            trigger.setAttribute('aria-expanded', sub.classList.contains('open') ? 'true' : 'false');
        });
    }

    // Save state to localStorage
    function saveSidebarState() {
        try {
            const states = {};
            document.querySelectorAll('.nav-sub').forEach(sub => {
                if (sub.id) {
                    states[sub.id] = sub.classList.contains('open');
                }
            });
            localStorage.setItem(SIDEBAR_STATE_KEY, JSON.stringify(states));
            console.log('[sidebar] state saved', states);
        } catch (e) { console.error('[sidebar] save error', e); }
    }

    // Restore state from localStorage
    function restoreSidebarState() {
        try {
            const saved = localStorage.getItem(SIDEBAR_STATE_KEY);
            if (!saved) return;
            const states = JSON.parse(saved);
            console.log('[sidebar] restoring state', states);
            
            Object.keys(states).forEach(id => {
                const sub = document.getElementById(id);
                if (sub) {
                    const shouldBeOpen = !!states[id];
                    if (shouldBeOpen) {
                        sub.classList.add('open');
                    } else {
                        // Only remove if it's not the current active path (to avoid overriding server logic if no state was saved)
                        // But usually we want to respect the user's manual closure.
                        sub.classList.remove('open');
                    }
                    const trigger = sub.previousElementSibling;
                    if (trigger && trigger.classList.contains('nav-item')) {
                        trigger.setAttribute('aria-expanded', shouldBeOpen ? 'true' : 'false');
                    }
                }
            });
        } catch (e) {
            console.warn('[sidebar] failed to restore state', e);
        }
    }

    // Save scroll position
    function saveSidebarScroll() {
        const sidebar = document.querySelector('.sidebar-nav');
        if (sidebar) {
            localStorage.setItem(SIDEBAR_SCROLL_KEY, sidebar.scrollTop);
        }
    }

    // Restore scroll position
    function restoreSidebarScroll() {
        const sidebar = document.querySelector('.sidebar-nav');
        if (sidebar) {
            const pos = localStorage.getItem(SIDEBAR_SCROLL_KEY);
            if (pos) {
                sidebar.scrollTop = parseInt(pos, 10);
            }
        }
    }

    // Toggle submenu on click/touch
    function handleSubmenuClick(e) {
        var trigger = e.target.closest('.nav-item-group > .nav-item, .nav-sub-item');
        if (!trigger) return;
        
        // If it's a real link (<a>), save state and let it work normally
        if (trigger.tagName === 'A' && trigger.getAttribute('href') && trigger.getAttribute('href') !== '#') {
            saveSidebarState();
            saveSidebarScroll();
            
            // Close sidebar on mobile when navigating
            if (window.innerWidth <= 900) {
                document.body.classList.remove('sidebar-open');
            }
            return;
        }

        // If it's a sub-item that isn't a link, just return
        if (trigger.classList.contains('nav-sub-item')) return;

        var group = trigger.closest('.nav-item-group');
        var sub = group ? group.querySelector('.nav-sub') : null;
        if (!sub) return;

        e.preventDefault();
        e.stopPropagation();

        var now = Date.now();
        var lastToggle = parseInt(group.getAttribute('data-last-toggle') || '0', 10);
        if (now - lastToggle < 200) return;
        group.setAttribute('data-last-toggle', String(now));

        var isOpen = sub.classList.toggle('open');
        trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        
        saveSidebarState();
    }

    // Global toggle function
    window.toggleNavSub = function(id) {
        const sub = document.getElementById(id);
        if (!sub) return;
        const btn = sub.previousElementSibling;
        const isOpen = sub.classList.toggle('open');
        if(btn) btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        saveSidebarState();
    };

    // Show current page name in top bar on desktop
    function updateTopBarTitle() {
        var titleEl = document.getElementById('topBarPageTitle');
        if (!titleEl) return;
        var activeItem = document.querySelector('.sidebar .nav-sub-item.active');
        if (!activeItem) return;
        
        var label = activeItem.textContent.replace(/[\u{1F300}-\u{1FFFF}]/gu, '').trim();
        titleEl.textContent = label;
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

    // Initialization
    document.addEventListener('DOMContentLoaded', function() {
        const sidebarNav = document.querySelector('.sidebar-nav');
        
        // Always run responsiveness init if possible
        initResponsiveSidebar();
        
        if (sidebarNav) {
            initAria();
            restoreSidebarState();
            restoreSidebarScroll();
            
            sidebarNav.addEventListener('click', handleSubmenuClick);
            
            // Handle scroll persistence on navigation
            sidebarNav.querySelectorAll('a').forEach(link => {
                link.addEventListener('click', saveSidebarScroll);
            });
            
            // Watch for manual scroll to save it occasionally
            let scrollTimeout;
            sidebarNav.addEventListener('scroll', function() {
                clearTimeout(scrollTimeout);
                scrollTimeout = setTimeout(saveSidebarScroll, 500);
            }, { passive: true });

            // Fail-safe save on page unload
            window.addEventListener('beforeunload', function() {
                saveSidebarState();
                saveSidebarScroll();
            });
        }
        
        updateTopBarTitle();
    });
    
    window.addEventListener('resize', updateTopBarTitle);
    window.runIntegrityCheck = function() {
        if (!confirm('Czy na pewno chcesz uruchomić pełny test integralności systemu? Może to potrwać kilka sekund.')) return;
        
        const btn = event.currentTarget;
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<span class="material-icons rotating" style="font-size:16px; vertical-align:middle; margin-right:4px;">sync</span> Sprawdzanie...';
        btn.style.pointerEvents = 'none';
        btn.style.opacity = '0.7';

        fetch('/admin/master/verify')
            .then(response => response.json())
            .then(data => {
                btn.innerHTML = originalHtml;
                btn.style.pointerEvents = 'auto';
                btn.style.opacity = '1';
                
                if (data.success) {
                    alert('SUKCES: System jest stabilny!\n\n' + data.output);
                } else {
                    alert('BŁĄD: Wykryto problemy!\n\n' + data.output);
                }
            })
            .catch(error => {
                btn.innerHTML = originalHtml;
                btn.style.pointerEvents = 'auto';
                btn.style.opacity = '1';
                alert('Błąd komunikacji z serwerem: ' + error);
            });
    };
})();
