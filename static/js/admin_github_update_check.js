/* Check GitHub / GHCR image availability and CI build status from System Settings. */
(function () {
    'use strict';

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function workflowBadge(conclusion, status) {
        if (status !== 'completed') {
            return '<span style="padding:2px 7px;border-radius:999px;background:#fef3c7;color:#92400e;font-size:11px;font-weight:700;">W toku</span>';
        }
        if (conclusion === 'success') {
            return '<span style="padding:2px 7px;border-radius:999px;background:#dcfce7;color:#166534;font-size:11px;font-weight:700;">OK</span>';
        }
        if (conclusion === 'failure') {
            return '<span style="padding:2px 7px;border-radius:999px;background:#fee2e2;color:#991b1b;font-size:11px;font-weight:700;">Błąd</span>';
        }
        return '<span style="padding:2px 7px;border-radius:999px;background:#f1f5f9;color:#475569;font-size:11px;font-weight:700;">Pominięto</span>';
    }

    async function checkGithubImageUpdate() {
        const btn = document.getElementById('btn-check-github-image');
        const box = document.getElementById('github-image-status-box');
        if (!btn || !box) return;

        const originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Sprawdzanie…';
        box.style.display = 'block';
        box.innerHTML = '<div style="color:#475569;font-size:12px;">Łączenie z GitHub API…</div>';

        try {
            const resp = await fetch('/admin/api/github-image-check', { cache: 'no-store' });
            const data = await resp.json();

            const palette = {
                update_available: { bg: '#ecfdf5', border: '#6ee7b7', text: '#065f46' },
                up_to_date: { bg: '#eff6ff', border: '#93c5fd', text: '#1e40af' },
                ci_blocked: { bg: '#fef2f2', border: '#fca5a5', text: '#991b1b' },
                building: { bg: '#fffbeb', border: '#fcd34d', text: '#92400e' },
                pending: { bg: '#fffbeb', border: '#fcd34d', text: '#92400e' },
                error: { bg: '#fef2f2', border: '#fca5a5', text: '#991b1b' },
            }[data.status] || { bg: '#f8fafc', border: '#cbd5e1', text: '#334155' };

            const local = data.local || {};
            const remote = data.remote_commit || {};
            const workflows = Array.isArray(data.workflows) ? data.workflows : [];

            let wfHtml = '';
            if (workflows.length) {
                wfHtml = '<div style="margin-top:10px;display:grid;gap:6px;">' + workflows.map(w => (
                    '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 8px;background:#ffffff;border:1px solid #e2e8f0;border-radius:7px;font-size:12px;">' +
                    '<a href="' + escapeHtml(w.url) + '" target="_blank" rel="noopener" style="color:#0f172a;font-weight:600;text-decoration:none;">' + escapeHtml(w.name) + ' <span style="color:#64748b;font-family:monospace;">(' + escapeHtml(w.head_sha) + ')</span></a>' +
                    workflowBadge(w.conclusion, w.status) +
                    '</div>'
                )).join('') + '</div>';
            }

            box.innerHTML =
                '<div style="padding:10px 12px;border-radius:8px;background:' + palette.bg + ';border:1px solid ' + palette.border + ';color:' + palette.text + ';font-size:12px;line-height:1.5;">' +
                '<div style="font-weight:700;margin-bottom:6px;">' + escapeHtml(data.summary || 'Sprawdzono status.') + '</div>' +
                '<div><strong>Lokalna wersja:</strong> v' + escapeHtml(local.version || 'N/A') + ' (' + escapeHtml(local.commit_sha || '—') + ') · ' + escapeHtml(local.commit_date || '—') + '</div>' +
                (remote.sha ? '<div><strong>GitHub main:</strong> ' + escapeHtml(remote.sha) + ' · ' + escapeHtml(remote.date) + ' — ' + escapeHtml(remote.message) + '</div>' : '') +
                wfHtml +
                (data.actions_url ? '<div style="margin-top:8px;"><a href="' + escapeHtml(data.actions_url) + '" target="_blank" rel="noopener" style="font-weight:700;color:#1d4ed8;">Otwórz GitHub Actions →</a></div>' : '') +
                '</div>';
        } catch (err) {
            box.innerHTML = '<div style="padding:10px 12px;border-radius:8px;background:#fef2f2;border:1px solid #fca5a5;color:#991b1b;font-size:12px;font-weight:700;">Błąd połączenia z serwerem aplikacji.</div>';
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }

    window.checkGithubImageUpdate = checkGithubImageUpdate;
})();
