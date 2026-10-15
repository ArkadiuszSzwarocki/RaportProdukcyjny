import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source = fs.readFileSync(new URL('../../static/js/temporary-admin.js', import.meta.url), 'utf8');
function setup(active = false) {
    const listeners = {};
    const intervals = [];
    const calls = [];
    const navigation = [];
    let now = 9000000; // Browser clock differs from the server clock.
    let reply = {ok: true, data: {success: true, eligible: true, active: true, expires_at: 10600, server_now: 10000}};
    const nodes = {
        temporaryAdminSwitch: {dataset: {active: String(active), expires: active ? '10600' : '', serverNow: '10000',
            csrf: 'session-token', statusUrl: '/status', enableUrl: '/enable', disableUrl: '/disable'}},
        temporaryAdminButton: {addEventListener: (name, handler) => { listeners.click = handler; }},
        temporaryAdminTimer: {}, temporaryAdminBanner: {}, temporaryAdminError: {}
    };
    const document = {hidden: false, getElementById: id => nodes[id], addEventListener: (name, handler) => {listeners[name] = handler;}};
    const window = {location: {replace: value => navigation.push(['replace', value]),
        assign: value => navigation.push(['assign', value]), reload: () => navigation.push(['reload'])},
        addEventListener: (name, handler) => { listeners[name] = handler; }};
    vm.runInNewContext(source, {document, window, Date: {now: () => now}, AbortController,
        setTimeout, clearTimeout, setInterval: (handler, delay) => intervals.push({handler, delay}),
        fetch: async (url, options) => {calls.push({url, options}); if (reply.error) throw new Error('offline');
            return {ok: reply.ok, json: async () => reply.data};}});
    return {nodes, calls, navigation, listeners, document,
        tick: () => intervals.find(item => item.delay === 1000).handler(),
        poll: () => intervals.find(item => item.delay === 15000).handler(),
        advance: seconds => {now += seconds * 1000;}, reply: value => {reply = value;}};
}

test('countdown uses server time and returns to leader exactly at deadline once', () => {
    const state = setup(true);
    assert.equal(state.nodes.temporaryAdminTimer.textContent, '10:00');
    state.advance(599);
    state.tick();
    assert.equal(state.nodes.temporaryAdminTimer.textContent, '00:01');
    state.advance(1);
    state.tick();
    state.tick();
    assert.deepEqual(state.navigation, [['replace', '/']]);
});

test('activation sends only POST with session CSRF and reloads the current view', async () => {
    const state = setup();
    await state.listeners.click();
    assert.equal(state.calls[0].url, '/enable');
    assert.equal(state.calls[0].options.method, 'POST');
    assert.equal(state.calls[0].options.headers['X-CSRF-Token'], 'session-token');
    assert.equal(state.calls[0].options.credentials, 'same-origin');
    assert.deepEqual(state.navigation, [['reload']]);
});

test('manual return goes to the leader home page', async () => {
    const state = setup(true);
    state.reply({ok: true, data: {success: true, active: false, server_now: 10000}});
    await state.listeners.click();
    assert.equal(state.calls[0].url, '/disable');
    assert.deepEqual(state.navigation, [['assign', '/']]);
});

test('server refusal and connection failure retain visible error and permit retry', async () => {
    const state = setup();
    state.reply({ok: false, data: {success: false, message: 'Brak uprawnień'}});
    await state.listeners.click();
    assert.equal(state.nodes.temporaryAdminError.textContent, 'Brak uprawnień');
    assert.equal(state.nodes.temporaryAdminButton.disabled, false);
    state.reply({error: true});
    await state.listeners.click();
    assert.equal(state.calls.length, 2);
    assert.equal(state.navigation.length, 0);
});

test('a role change in another tab refreshes this tab without extending its deadline', async () => {
    const state = setup(true);
    state.reply({ok: true, data: {success: true, eligible: true, active: false, server_now: 10001}});
    await state.poll();
    assert.deepEqual(state.navigation, [['replace', '/']]);
});

test('hidden tabs skip status polling while the deadline remains fixed', async () => {
    const state = setup(true);
    state.document.hidden = true;
    await state.poll();
    assert.equal(state.calls.length, 0);
    state.advance(600);
    state.tick();
    assert.deepEqual(state.navigation, [['replace', '/']]);
});
