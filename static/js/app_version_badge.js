/* Interactive top-bar update badge & popover */
(function () {
    'use strict';

    const STORAGE_KEY = 'rp_seen_app_version';

    function initAppVersionBadge() {
        const wrapper = document.getElementById('appVersionWrapper');
        const toggleBtn = document.getElementById('appVersionToggleBtn');
        const popover = document.getElementById('appVersionPopover');
        const closeBtn = document.getElementById('appVersionCloseBtn');
        if (!wrapper || !toggleBtn || !popover || wrapper.dataset.initialized === '1') return;
        wrapper.dataset.initialized = '1';

        const currentStamp = String(toggleBtn.dataset.versionStamp || '').trim();
        try {
            const seenStamp = localStorage.getItem(STORAGE_KEY) || '';
            if (currentStamp && seenStamp !== currentStamp) {
                toggleBtn.classList.add('has-unseen-update');
            }
        } catch (err) {
            // Ignore storage errors in restricted browsing modes.
        }

        function closePopover() {
            popover.hidden = true;
            toggleBtn.setAttribute('aria-expanded', 'false');
        }

        function openPopover() {
            popover.hidden = false;
            toggleBtn.setAttribute('aria-expanded', 'true');
            toggleBtn.classList.remove('has-unseen-update');
            if (currentStamp) {
                try {
                    localStorage.setItem(STORAGE_KEY, currentStamp);
                } catch (err) {
                    // Ignore storage errors.
                }
            }
        }

        toggleBtn.addEventListener('click', (event) => {
            event.stopPropagation();
            if (popover.hidden) openPopover();
            else closePopover();
        });

        if (closeBtn) {
            closeBtn.addEventListener('click', (event) => {
                event.stopPropagation();
                closePopover();
            });
        }

        document.addEventListener('click', (event) => {
            if (!popover.hidden && !wrapper.contains(event.target)) {
                closePopover();
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && !popover.hidden) {
                closePopover();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAppVersionBadge);
    } else {
        initAppVersionBadge();
    }
})();
