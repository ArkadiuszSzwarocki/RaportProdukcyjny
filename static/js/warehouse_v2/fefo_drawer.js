// cspell:words fefo
(() => {
    const toggle = document.getElementById('fefoDrawerToggle');
    const drawer = document.getElementById('fefoDrawer');
    const close = document.getElementById('fefoDrawerClose');
    if (!toggle || !drawer || !close) return;
    const storageKey = 'warehouse_fefo_icon_position';
    let position = 0.35;
    let drag = null;
    let suppressClick = false;
    try {
        const saved = localStorage.getItem(storageKey);
        if (saved !== null && Number.isFinite(Number(saved))) position = Math.max(0, Math.min(1, Number(saved)));
    } catch (_) { /* Storage can be unavailable in private browser sessions. */ }
    const limits = () => ({ min: 76, max: Math.max(76, window.innerHeight - toggle.offsetHeight - 16) });
    const applyPosition = () => {
        const { min, max } = limits();
        toggle.style.top = `${min + (max - min) * position}px`;
    };
    const moveTo = y => {
        const { min, max } = limits();
        position = max > min ? (Math.max(min, Math.min(max, y)) - min) / (max - min) : 0;
        applyPosition();
    };
    const savePosition = () => {
        try { localStorage.setItem(storageKey, String(position)); } catch (_) { /* Position still works for this page. */ }
    };
    toggle.addEventListener('pointerdown', event => {
        if (event.button !== 0 || !event.isPrimary) return;
        suppressClick = false;
        drag = { id: event.pointerId, startY: event.clientY, top: toggle.getBoundingClientRect().top, moved: false };
        toggle.setPointerCapture(event.pointerId);
    });
    toggle.addEventListener('pointermove', event => {
        if (!drag || drag.id !== event.pointerId) return;
        const delta = event.clientY - drag.startY;
        if (Math.abs(delta) > 6) drag.moved = true;
        if (drag.moved) moveTo(drag.top + delta);
    });
    toggle.addEventListener('pointerup', event => {
        if (!drag || drag.id !== event.pointerId) return;
        suppressClick = drag.moved;
        if (drag.moved) savePosition();
        drag = null;
        if (toggle.hasPointerCapture(event.pointerId)) toggle.releasePointerCapture(event.pointerId);
    });
    toggle.addEventListener('pointercancel', () => { drag = null; suppressClick = false; });
    toggle.addEventListener('click', () => {
        if (suppressClick) { suppressClick = false; return; }
        drawer.showModal();
        toggle.setAttribute('aria-expanded', 'true');
    });
    toggle.addEventListener('keydown', event => {
        if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
        event.preventDefault();
        moveTo(toggle.getBoundingClientRect().top + (event.key === 'ArrowUp' ? -24 : 24));
        savePosition();
    });
    close.addEventListener('click', () => drawer.close());
    drawer.addEventListener('close', () => toggle.setAttribute('aria-expanded', 'false'));
    drawer.addEventListener('click', event => {
        if (event.target !== drawer) return;
        const rect = drawer.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) drawer.close();
    });
    window.addEventListener('resize', applyPosition);
    applyPosition();
})();
