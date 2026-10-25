import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

function setup() {
    let listener, release, posts = 0, stopped = 0;
    const button = {textContent: 'Confirm', disabled: false}, timers = [], notices = [];
    const form = {dataset: {}, action: '/koniec_zlecenie/2', reportValidity: () => true,
        matches: selector => selector === 'form[data-order-close="true"]',
        querySelector: () => button, remaining: '962'};
    const window = {showToast: (message, type) => notices.push({message, type}),
        setTimeout: fn => timers.push(fn), closeQuickPopup() {}, location: {reload() {}}};
    const context = {document: {addEventListener(name, fn) { listener = fn; }}, window,
        FormData: class {constructor(value) { assert.equal(value.remaining, '962'); }},
        fetch(url, options) { posts++; assert.equal(url, form.action); assert.equal(options.method, 'POST');
            return new Promise(resolve => { release = resolve; }); }};
    vm.runInNewContext(readFileSync('static/js/common/order-close.js', 'utf8'), context);
    return {form, button, notices, timers, posts: () => posts, stopped: () => stopped,
        submit() { listener({target: form, preventDefault() {}, stopImmediatePropagation() { stopped++; }}); },
        async respond(response) { release(response); for (let i = 0; i < 8; i++) await Promise.resolve(); }};
}

test('closing with 962 remaining sends exactly one request despite repeated clicks', async () => {
    const ui = setup();
    ui.submit(); ui.submit();
    assert.equal(ui.posts(), 1);
    assert.equal(ui.stopped(), 2);
    assert.equal(ui.button.disabled, true);
    await ui.respond({ok: true, status: 200, json: async () => ({success: true})});
    assert.equal(ui.timers.length, 1);
    assert.equal(ui.notices[0].type, 'success');
});

test('storage errors retain the entered remaining count and re-enable confirmation', async () => {
    const ui = setup(); ui.submit();
    await ui.respond({ok: false, status: 500, json: async () => ({success: false, message: 'Storage failed'})});
    assert.equal(ui.button.disabled, false);
    assert.equal(ui.button.textContent, 'Confirm');
    assert.equal(ui.form.dataset.submitting, 'false');
    assert.equal(ui.form.remaining, '962');
    assert.equal(ui.timers.length, 0);
    assert.equal(ui.notices[0].type, 'danger');
});

test('a non-JSON error page is never mistaken for a successful closure', async () => {
    const ui = setup(); ui.submit();
    await ui.respond({ok: false, status: 502, json: async () => {throw new Error('Invalid JSON');}});
    assert.equal(ui.button.disabled, false);
    assert.equal(ui.timers.length, 0);
    assert.equal(ui.notices[0].type, 'danger');
});
