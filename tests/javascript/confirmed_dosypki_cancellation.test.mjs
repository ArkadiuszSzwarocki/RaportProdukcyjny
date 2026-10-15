import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function setup({accepted = true, status = 200, success = true, offline = false} = {}) {
    const events = {}, calls = [], notices = [];
    let reloads = 0;
    const button = {disabled: false, getAttribute: () => '/usun_zatwierdzona_dosypke/91?linia=AGRO'};
    const document = {addEventListener: (event, handler) => {events[event] = handler;}};
    const window = {AppDialog: {confirm: async () => accepted},
        dashboardToasts: {notify: (message, type) => notices.push({message, type})},
        location: {reload: () => {reloads++;}}};
    vm.runInNewContext(fs.readFileSync('static/js/dashboard/card-actions.js', 'utf8'), {
        window, document, console, Promise,
        fetch: async (url, options) => {
            calls.push({url, options});
            if (offline) throw new Error('offline');
            return {ok: status === 200, json: async () => ({success, message: 'Odmowa'})};
        }
    });
    window.dashboardCardActions.init();
    return {button, calls, notices, reloads: () => reloads,
        click: () => events.click({preventDefault() {}, target: {closest: selector => selector === '[data-action="cancel-confirmed-dosypka"]' ? button : null}})};
}

async function settle() {await new Promise(resolve => setImmediate(resolve));}

test('a duplicate click cancels exactly the chosen record once and reloads weights', async () => {
    const s = setup();
    s.click(); s.click(); await settle();
    assert.equal(s.calls.length, 1);
    assert.equal(s.calls[0].url, '/usun_zatwierdzona_dosypke/91?linia=AGRO');
    assert.equal(s.calls[0].options.method, 'POST');
    assert.equal(s.reloads(), 1);
});

test('rejecting the confirmation does not change the addition', async () => {
    const s = setup({accepted: false});
    s.click(); await settle();
    assert.equal(s.calls.length, 0);
    assert.equal(s.button.disabled, false);
});

for (const scenario of [{status: 403, success: false}, {offline: true}]) {
    test('a refusal or network failure remains visible and permits retry ' + JSON.stringify(scenario), async () => {
        const s = setup(scenario);
        s.click(); await settle();
        assert.equal(s.reloads(), 0);
        assert.equal(s.button.disabled, false);
        assert.equal(s.notices.at(-1).type, 'danger');
    });
}
