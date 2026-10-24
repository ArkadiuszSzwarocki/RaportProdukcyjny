/* Per-user permission editor. Keys remain private; labels and groups come from the server. */
(function () {
    'use strict';
    let editor = null;
    const escape = value => { const node = document.createElement('span'); node.textContent = String(value || ''); return node.innerHTML; };
    const node = (tag, className, text) => { const item = document.createElement(tag); if (className) item.className = className; if (text !== undefined) item.textContent = text; return item; };
    const inheritedMode = item => !item.role_access ? 'deny' : item.role_readonly ? 'readonly' : 'allow';
    const originalMode = item => !item.has_override ? 'inherit' : !item.override_access ? 'deny' : item.override_readonly ? 'readonly' : 'allow';
    const describe = (item, mode) => {
        if (mode === 'inherit' && item.default_source === 'operation_policy') return 'Zasady strony i operacji';
        const effective = mode === 'inherit' ? inheritedMode(item) : mode;
        return effective === 'deny' ? 'Zablokowane' : effective === 'readonly' ? (item.kind === 'function' ? 'Bez prawa wykonania czynności' : 'Tylko podgląd') : 'Zezwolone';
    };
    function status() {
        if (!editor) return;
        const count = editor.modules.filter(item => editor.values.get(item.page_key) !== originalMode(item)).length;
        const button = document.getElementById('btnSaveUserPerms');
        const label = document.getElementById('userPermsStatus');
        if (button) button.disabled = !count || editor.saving || editor.master;
        if (label) label.textContent = editor.saving ? 'Zapisywanie…' : count ? 'Niezapisane zmiany: ' + count : 'Brak niezapisanych zmian';
    }
    function updateValue(key, value) {
        editor.values.set(key, value);
        document.querySelectorAll('#userPermsGroups .user-perm-select').forEach(select => {
            if (select.dataset.page !== key) return;
            select.value = value;
            const item = editor.byKey.get(key);
            select.closest('.user-perm-row').querySelector('.user-perm-current').textContent = describe(item, value);
        });
        status();
    }
    function render() {
        const list = document.getElementById('userPermsGroups');
        if (!list || !editor) return;
        const opened = new Set([...list.querySelectorAll('details[open]')].map(group => group.dataset.group));
        const query = document.getElementById('userPermsSearch').value.trim().toLocaleLowerCase('pl');
        const groups = new Map();
        editor.modules.forEach(item => {
            (item.groups || [{id:'other', title:'Pozostałe strony'}]).forEach(group => {
                const text = [item.label, group.title, item.page_key].join(' ').toLocaleLowerCase('pl');
                if (query && !query.split(/\s+/).every(word => text.includes(word))) return;
                if (!groups.has(group.id)) groups.set(group.id, {title:group.title, items:[]});
                groups.get(group.id).items.push(item);
            });
        });
        list.replaceChildren();
        const rank = id => {
            const [area, section] = id.split('.');
            const areaRank = {agro:0,psd:1,magazyn:2,osip:2,ustawienia:3}[area] ?? 4;
            const sectionRank = {zasyp:0,workowanie:1,bufor:2,dashboard:3,magazyn:4}[section] ?? 5;
            return areaRank * 10 + sectionRank;
        };
        const entries = [...groups.entries()].sort((a,b) => rank(a[0]) - rank(b[0]) || a[1].title.localeCompare(b[1].title, 'pl'));
        entries.forEach(([id, group]) => {
            const details = node('details', 'user-perm-group');
            details.dataset.group = id;
            details.open = !!query || opened.has(id) || (!editor.rendered && id === 'agro.zasyp') || (!editor.rendered && entries.length === 1);
            const summary = node('summary');
            summary.append(node('span', '', group.title));
            summary.append(node('small', '', group.items.filter(item => item.kind === 'function').length + ' czynności'));
            details.append(summary);
            group.items.sort((a,b) => (a.kind === 'function') - (b.kind === 'function') || a.label.localeCompare(b.label,'pl')).forEach(item => {
                const row = node('div', 'user-perm-row');
                const info = node('div', 'user-perm-info');
                info.append(node('strong', '', item.label));
                const inherited = describe(item, 'inherit');
                const source = item.default_source === 'operation_policy' ? 'Obowiązują zasady strony i operacji.' : 'Rola ' + editor.role + ': ' + inherited;
                info.append(node('small', 'user-perm-inherited', source));
                if (item.groups.length > 1) {
                    const elsewhere = item.groups.filter(group => group.id !== id).map(group => group.title).join(', ');
                    info.append(node('small', 'user-perm-shared', 'Wspólna reguła — zmiana obejmuje także: ' + elsewhere));
                }
                const field = node('div', 'user-perm-field');
                const select = node('select', 'user-perm-select');
                select.dataset.page = item.page_key;
                select.setAttribute('aria-label', group.title + ' — ' + item.label);
                const mode = editor.values.get(item.page_key);
                const options = [['inherit', item.default_source === 'operation_policy' ? 'Użyj zasad strony i operacji' : 'Użyj zasad roli: ' + editor.role], ['allow', item.kind === 'function' ? 'Zezwól na czynność' : 'Zezwól na dostęp']];
                if (item.kind !== 'function' || mode === 'readonly') options.push(['readonly', item.kind === 'function' ? 'Zablokowane (dawniej: tylko odczyt)' : 'Tylko podgląd']);
                options.push(['deny','Zablokuj']);
                options.forEach(([value,label]) => select.add(new Option(label, value)));
                select.value = mode;
                select.disabled = editor.master;
                select.addEventListener('change', () => updateValue(item.page_key, select.value));
                field.append(select, node('small', 'user-perm-current', describe(item, mode)));
                row.append(info, field);
                details.append(row);
            });
            list.append(details);
        });
        if (!entries.length) list.append(node('p', 'user-perm-empty', 'Brak stron i czynności pasujących do wyszukiwania.'));
        editor.rendered = true;
        status();
    }
    window.openUserPermissionsModal = function (userId, login, role) {
        editor = null;
        showQuickPopup('Indywidualne uprawnienia: @' + escape(login), `
            <div id="userPermsLoading" class="user-perm-loading" role="status">Ładowanie uprawnień…</div>
            <div id="userPermsContent" class="user-perm-editor" hidden>
                <div class="user-perm-help">
                    <p><strong>Użyj zasad roli</strong> oznacza brak indywidualnego wyjątku. Konto korzysta z ustawień roli <strong id="userPermsRole"></strong>; zmiana ustawień tej roli obejmie także to konto.</p>
                    <p>Czynność wymaga również dostępu do odpowiedniej strony i spełnienia zasad operacji. „Zasady strony i operacji” oznaczają, że czynność nie ma osobnej reguły w ustawieniach roli.</p>
                    <p id="userPermsMasterNote" hidden>MasterAdmin zachowuje pełny dostęp. Indywidualne ograniczenia nie dotyczą tej roli.</p>
                </div>
                <label class="user-perm-search">Znajdź stronę lub czynność
                    <input id="userPermsSearch" type="search" placeholder="Np. Zasyp AGRO, dosypka, drukowanie…" autocomplete="off">
                </label>
                <div id="userPermsGroups" class="user-perm-groups"></div>
                <div class="user-perm-footer">
                    <span id="userPermsStatus" role="status" aria-live="polite"></span>
                    <button type="button" class="btn-popup-secondary" onclick="closeQuickPopup()">Zamknij</button>
                    <button type="button" id="btnSaveUserPerms" class="btn-popup-primary" disabled>Zapisz zmiany</button>
                </div>
            </div>`, {maxWidth:'1000px'});
        const popup = document.getElementById('quickPopup');
        if (popup) popup.classList.add('qp-user-permissions');
        const content = document.getElementById('userPermsContent');
        const loading = document.getElementById('userPermsLoading');
        fetch('/admin/api/user/' + encodeURIComponent(userId) + '/permissions', {silent:true})
            .then(response => { if (!response.ok) throw new Error('Nie udało się pobrać uprawnień.'); return response.json(); })
            .then(data => {
                if (!content.isConnected) return;
                if (!data.success) throw new Error(data.message || 'Nie udało się pobrać uprawnień.');
                editor = {userId, role:data.user.rola || role, modules:data.modules, saving:false, rendered:false,
                    byKey:new Map(data.modules.map(item => [item.page_key,item])),
                    values:new Map(data.modules.map(item => [item.page_key,originalMode(item)]))};
                editor.master = editor.role.toLowerCase().replace(/[\s_-]/g,'') === 'masteradmin';
                document.getElementById('userPermsRole').textContent = editor.role;
                document.getElementById('userPermsMasterNote').hidden = !editor.master;
                loading.hidden = true;
                content.hidden = false;
                document.getElementById('userPermsSearch').addEventListener('input', render);
                document.getElementById('btnSaveUserPerms').addEventListener('click', () => window.saveUserPermissions(userId));
                render();
            })
            .catch(error => { if (loading.isConnected) loading.textContent = error.message; });
    };
    window.saveUserPermissions = function (userId) {
        if (!editor || editor.userId !== userId || editor.saving || editor.master) return;
        const overrides = {};
        editor.modules.forEach(item => {
            const mode = editor.values.get(item.page_key);
            if (mode !== originalMode(item)) overrides[item.page_key] = {mode:mode === 'readonly' ? 'allow' : mode, readonly:mode === 'readonly'};
        });
        if (!Object.keys(overrides).length) return;
        editor.saving = true;
        status();
        fetch('/admin/api/user/' + encodeURIComponent(userId) + '/permissions', {
            method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({overrides})
        }).then(response => { if (!response.ok) throw new Error('Nie udało się zapisać uprawnień.'); return response.json(); })
          .then(data => { if (!data.success) throw new Error(data.message || 'Nie udało się zapisać uprawnień.'); alert('Uprawnienia użytkownika zostały zapisane.'); closeQuickPopup(); })
          .catch(error => { if (editor && editor.userId === userId) {editor.saving=false;status();} alert(error.message); });
    };
}());
