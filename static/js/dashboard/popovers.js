(function () {
    if (window.dashboardPopover) return;
    let active = null;

    function close() {
        if (!active) return;
        active.panel.style.display = 'none';
        active.button.setAttribute('aria-expanded', 'false');
        if (active.backdrop) active.backdrop.style.display = 'none';
        active = null;
    }

    function toggle(panelId, buttonId, backdropId, event) {
        if (event) { event.preventDefault(); event.stopPropagation(); }
        const panel = document.getElementById(panelId);
        const button = document.getElementById(buttonId);
        const backdrop = backdropId && document.getElementById(backdropId);
        if (!panel || !button) return;
        const wasOpen = active && active.panel === panel;
        close();
        if (wasOpen) return;
        // Escape parent clipping and stacking contexts before positioning.
        document.body.appendChild(panel);
        if (backdrop) {
            document.body.appendChild(backdrop);
            backdrop.style.display = 'block';
        }
        const rect = button.getBoundingClientRect();
        panel.style.position = 'fixed';
        panel.style.zIndex = '1045';
        panel.style.right = 'auto';
        panel.style.boxSizing = 'border-box';
        panel.style.minWidth = '0';
        panel.style.maxWidth = (window.innerWidth - 16) + 'px';
        panel.style.overflowY = 'auto';
        panel.style.display = 'block';
        const top = Math.min(rect.bottom + 8, window.innerHeight - 80);
        panel.style.top = Math.max(8, top) + 'px';
        panel.style.maxHeight = Math.max(64, window.innerHeight - top - 8) + 'px';
        const left = panelId === 'dashboardActionsDropdownMenu' ? rect.left : rect.right - panel.offsetWidth;
        panel.style.left = Math.max(8, Math.min(left, window.innerWidth - panel.offsetWidth - 8)) + 'px';
        button.setAttribute('aria-expanded', 'true');
        active = {panel, button, backdrop};
    }

    document.addEventListener('click', function (event) {
        if (active && !active.panel.contains(event.target) && !active.button.contains(event.target)) close();
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && active) {
            const button = active.button;
            close();
            button.focus();
        }
    });
    window.addEventListener('resize', close);
    document.addEventListener('scroll', function (event) {
        if (active && !active.panel.contains(event.target)) close();
    }, true);
    window.dashboardPopover = {toggle, close};
})();
