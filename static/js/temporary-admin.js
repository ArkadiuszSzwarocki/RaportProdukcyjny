/* A server deadline controls access; this timer only presents the state. */
(function () {
    'use strict';
    const panel = document.getElementById('temporaryAdminSwitch');
    if (!panel) return;
    const button = document.getElementById('temporaryAdminButton');
    const timer = document.getElementById('temporaryAdminTimer');
    const banner = document.getElementById('temporaryAdminBanner');
    const error = document.getElementById('temporaryAdminError');
    let active = panel.dataset.active === 'true';
    let deadline = Number(panel.dataset.expires || 0);
    let offset = Number(panel.dataset.serverNow) - Date.now() / 1000;
    let busy = false;
    let checking = false;
    let navigating = false;
    async function send(url, options) {
        const controller = new AbortController();
        const timeout = setTimeout(function () { controller.abort(); }, 10000);
        try { return await fetch(url, Object.assign({}, options, {signal: controller.signal})); }
        finally { clearTimeout(timeout); }
    }
    function tick() {
        if (!active) return;
        const seconds = Math.max(0, Math.ceil(deadline - (Date.now() / 1000 + offset)));
        timer.textContent = String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0');
        if (seconds === 0 && !navigating) {
            navigating = true;
            if (window.recordDashboardNavigation) window.recordDashboardNavigation('deadline', {previous_active: active});
            window.location.replace('/');
        }
    }
    function display(data) {
        active = !!data.active;
        deadline = Number(data.expires_at || 0);
        offset = Number(data.server_now) - Date.now() / 1000;
        banner.hidden = !active;
        button.textContent = active ? 'Wróć do lidera' : 'Włącz MasterAdmin na 10 minut';
        tick();
    }
    async function refresh() {
        if (document.hidden || busy || checking || navigating) return;
        checking = true;
        try {
            const response = await send(panel.dataset.statusUrl, {credentials: 'same-origin', cache: 'no-store', silent: true});
            if (!response.ok) return;
            const data = await response.json();
            if (!data.success || busy || navigating) return;
            if (active !== !!data.active || !data.eligible) {
                navigating = true;
                if (window.recordDashboardNavigation) window.recordDashboardNavigation(!data.eligible ? 'eligibility_lost' : (data.active ? 'role_activated_elsewhere' : 'role_disabled_elsewhere'), {previous_active: active, observed_active: !!data.active, observed_eligible: !!data.eligible});
                window.location.replace('/');
                return;
            }
            display(data);
        } catch (_) { /* The server still enforces the deadline while offline. */ }
        finally { checking = false; }
    }
    button.addEventListener('click', async function () {
        if (busy || navigating) return;
        busy = true;
        button.disabled = true;
        error.textContent = '';
        const wasActive = active;
        try {
            const response = await send(wasActive ? panel.dataset.disableUrl : panel.dataset.enableUrl, {
                method: 'POST', credentials: 'same-origin', cache: 'no-store',
                headers: {'X-CSRF-Token': panel.dataset.csrf, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'}
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || 'Nie udało się przełączyć roli.');
            navigating = true;
            if (wasActive) {
                if (window.recordDashboardNavigation) window.recordDashboardNavigation('manual_disable', {previous_active: true, observed_active: false});
                window.location.assign('/');
            }
            else window.location.reload();
        } catch (reason) {
            error.textContent = reason.message || 'Brak połączenia. Spróbuj ponownie.';
        } finally {
            busy = false;
            button.disabled = false;
        }
    });
    display({active: active, expires_at: deadline, server_now: Number(panel.dataset.serverNow)});
    setInterval(tick, 1000);
    setInterval(refresh, 15000);
    document.addEventListener('visibilitychange', refresh);
    window.addEventListener('focus', refresh);
    window.addEventListener('pageshow', refresh);
}());
