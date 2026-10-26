/* Film rolls selected on LP01 are assigned atomically with their stock withdrawal. */
window.Lp01Film = {
  async load(prefix, sourceName, enabled, sourceId) {
    const panel = document.getElementById(prefix + 'FilmFields');
    const select = document.getElementById(prefix + 'FilmPlan');
    const role = document.getElementById(prefix + 'FilmRole');
    if (!panel || !select || !role) return;
    const submit = document.getElementById(prefix === 'lp01' ? 'btnConfirmLP01' : 'dispConfirmBtn');
    const status = panel.querySelector('[data-film-status]');
    const error = panel.querySelector('[data-film-error]');
    const retry = panel.querySelector('[data-film-retry]');
    const previousWrap = document.getElementById(prefix + 'PreviousWrap');
    const remaining = document.getElementById(prefix + 'PreviousRemaining');
    if (select.filmController) select.filmController.abort();
    const token = window.crypto?.randomUUID?.() || 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const n = Math.floor(Math.random() * 16); return (c === 'x' ? n : (n & 3) | 8).toString(16); });
    select.dataset.requestKey = token;
    select.dataset.loading = enabled ? '1' : '0';
    select.dataset.failed = '0';
    panel.hidden = !enabled;
    panel.setAttribute('aria-busy', enabled ? 'true' : 'false');
    error.textContent = '';
    status.textContent = enabled ? 'Ładowanie zleceń dla tej folii…' : '';
    retry.hidden = true;
    retry.style.display = 'none';
    retry.onclick = () => this.load(prefix, sourceName, enabled, sourceId);
    select.replaceChildren(new Option(enabled ? 'Ładowanie zleceń…' : 'Bez przypisania do zlecenia', ''));
    select.disabled = Boolean(enabled);
    role.disabled = true;
    role.value = 'prepared';
    previousWrap.hidden = true;
    remaining.value = '';
    remaining.required = false;
    remaining.disabled = true;
    if (submit) submit.disabled = Boolean(enabled);

    // Install handlers before fetching so no previous dialog state can be used.
    role.onchange = () => {
      const replacement = !role.disabled && role.value === 'replace';
      previousWrap.hidden = !replacement;
      remaining.required = replacement;
      remaining.disabled = !replacement;
    };
    select.onchange = () => {
      const option = select.selectedOptions[0];
      const selected = Boolean(select.value && option && !option.disabled && this.ready(prefix));
      const full = selected && option.dataset.full === '1';
      role.disabled = !selected;
      role.querySelector('[value=replace]').disabled = !selected || option.dataset.replace !== '1';
      role.querySelector('[value=prepared]').disabled = !selected || full;
      role.querySelector('[value=active]').disabled = !selected || option.dataset.active !== '1';
      role.value = full && option.dataset.replace === '1' ? 'replace' :
        (selected && option.dataset.active === '1' ? 'active' : 'prepared');
      role.onchange();
      if (this.ready(prefix)) status.textContent = selected
        ? 'Wybierz, czy rolka ma pracować, czekać na wymianę, czy zastąpić obecną.'
        : 'Bez wyboru zlecenia materiał trafi tylko na LP01. Aby zmienić rolkę w zleceniu, najpierw wybierz zlecenie.';
    };
    if (!enabled) return;
    const controller = new AbortController();
    select.filmController = controller;
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('/api/lp01/film-plans?source_id=' + encodeURIComponent(sourceId), {signal: controller.signal});
      const result = await response.json();
      if (!response.ok || !result.success || !Array.isArray(result.plans)) throw Error('Nie pobrano listy zleceń.');
      if (select.dataset.requestKey !== token) return;
      select.replaceChildren(new Option('Bez przypisania do zlecenia', ''));
      const name = String(sourceName || '').normalize('NFC').trim().replace(/\s+/g, ' ').toLocaleLowerCase('pl');
      const matches = [];
      result.plans.forEach(plan => {
        const compatible = Boolean(plan.wymagana_folia) && String(plan.wymagana_folia).normalize('NFC').trim().replace(/\s+/g, ' ').toLocaleLowerCase('pl') === name;
        if (!compatible) return;
        const option = new Option('#' + plan.id + ' — ' + plan.produkt + ' — ' + plan.status + ' — ' + plan.data_planu + ' — folia: ' + plan.wymagana_folia, plan.id);
        const used = Number(plan.used_rolls);
        const full = Number(plan.total_rolls) >= 2;
        const canReplace = plan.status === 'w toku' && used === 1;
        option.disabled = full && !canReplace;
        option.dataset.replace = canReplace ? '1' : '0';
        option.dataset.full = full ? '1' : '0';
        if (full) option.textContent += canReplace ? ' — dostępna tylko zmiana rolki' : ' — przypisane 2 rolki; najpierw rozlicz lub zwolnij rolkę';
        option.dataset.active = plan.status === 'w toku' && used === 0 ? '1' : '0';
        select.add(option);
        if (!option.disabled && plan.status === 'w toku') matches.push(option);
      });
      if (select.options.length === 1) error.textContent = 'Brak zleceń z tą folią przypisaną w planowaniu. Zaplanowane pokazujemy tylko z ostatnich 7 dni.';
      if (matches.length === 1) select.value = matches[0].value;
    } catch (failure) {
      if (select.dataset.requestKey === token) {
        select.dataset.failed = '1';
        select.replaceChildren(new Option('Nie pobrano zleceń', ''));
        status.textContent = '';
        error.textContent = failure.name === 'AbortError'
          ? 'Pobieranie zleceń trwało zbyt długo. Kliknij „Ponów pobieranie”. Niczego nie wydano.'
          : 'Nie udało się pobrać zleceń. Kliknij „Ponów pobieranie”. Niczego nie wydano.';
        retry.hidden = false;
        retry.style.display = 'inline-block';
      }
    } finally {
      clearTimeout(timeout);
      if (select.dataset.requestKey === token) {
        select.dataset.loading = '0';
        panel.setAttribute('aria-busy', 'false');
        const failed = select.dataset.failed === '1';
        select.disabled = failed;
        if (submit) submit.disabled = failed;
        select.onchange();
      }
    }
  },
  ready(prefix) {
    const panel = document.getElementById(prefix + 'FilmFields');
    const select = document.getElementById(prefix + 'FilmPlan');
    return Boolean(panel && select && (panel.hidden || (select.dataset.loading === '0' && select.dataset.failed !== '1')));
  },
  selection(prefix) {
    const panel = document.getElementById(prefix + 'FilmFields');
    const select = document.getElementById(prefix + 'FilmPlan');
    if (!panel || panel.hidden || !select.value || !this.ready(prefix)) return null;
    return {plan_id: Number(select.value), roll_role: document.getElementById(prefix + 'FilmRole').value, request_key: select.dataset.requestKey, previous_remaining: document.getElementById(prefix + 'PreviousRemaining').value};
  }
};
