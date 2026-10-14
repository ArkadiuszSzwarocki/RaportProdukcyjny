import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function setup(response, offline = false) {
    const events = {}, clicks = {}, requests = [], notices = [];
    let feedback = null, removed = false;
    const status = {style: {}, closest: () => root};
    const root = {
        closest: () => root,
        getAttribute: name => ({'data-linia': 'AGRO', 'data-plan-id': '323', 'data-current-role': 'masteradmin'})[name],
        classList: {contains: () => false},
        querySelector: selector => selector === '#dosypki-status' ? status : selector === '.dosypki-confirm-message' ? feedback : null,
        querySelectorAll: () => [],
        appendChild: node => {feedback = node;},
        addEventListener: (name, fn) => {(clicks[name] ||= []).push(fn);}
    };
    const input = {value: '45', focus() {}};
    const row = {style: {}, getAttribute: () => '323', querySelector: () => input,
        parentNode: {removeChild() {removed = true;}}};
    const btn = {disabled: false, style: {}, textContent: '✓ Potwierdź',
        getAttribute: () => '91', closest: selector => selector === 'tr' ? row : selector === '.p-15' ? root : selector === 'button.dosypka-confirm-btn[data-id]' ? btn : null};
    const document = {documentElement: {}, querySelectorAll: () => [],
        addEventListener: (name, fn) => {events[name] = fn;}, getElementById: () => status,
        createElement: () => ({style: {}, setAttribute() {}})};
    const window = {location: {search: '?linia=PSD'}, showToast: (message, type) => notices.push({message, type})};
    vm.runInNewContext(fs.readFileSync('static/js/dosypki.js', 'utf8'), {
        window, document, URLSearchParams, console,
        MutationObserver: class {observe() {}}, HTMLElement: class {},
        setInterval() {}, clearInterval() {}, setTimeout: fn => fn(),
        fetch: async (url, options) => {
            requests.push({url, options});
            if (options.method === 'POST') {
                if (offline) throw new Error('offline');
                return {ok: response.status === 200, status: response.status, json: async () => response.body};
            }
            return {json: async () => ({success: true, dosypki: []})};
        }
    });
    events.DOMContentLoaded();
    return {btn, input, requests, notices, removed: () => removed,
        click: () => clicks.click.forEach(handler => handler({target: btn, preventDefault() {}}))};
}

async function settle() {await new Promise(resolve => setImmediate(resolve));}

test('confirmation sends form weight to the popup hall and waits for confirmed success', async () => {
    const s = setup({status: 200, body: {success: true, message: 'Potwierdzono dosypkę.'}});
    s.click();
    s.click(); // An in-flight confirmation must not be duplicated.
    await settle();
    const posts = s.requests.filter(r => r.options.method === 'POST');
    assert.equal(posts.length, 1);
    assert.equal(posts[0].url, '/potwierdz_dosypke/91?linia=AGRO');
    assert.match(posts[0].options.headers['Content-Type'], /^application\/x-www-form-urlencoded/);
    assert.equal(new URLSearchParams(posts[0].options.body).get('kg'), '45');
    assert.equal(s.removed(), true);
    assert.equal(s.notices.at(-1).type, 'success');
});

test('server rejection remains visible without AppDialog and permits retry', async () => {
    const s = setup({status: 403, body: {success: false, message: 'Brak uprawnień do tej sekcji.'}});
    s.click(); await settle();
    assert.equal(s.removed(), false);
    assert.equal(s.btn.disabled, false);
    assert.equal(s.btn.textContent, '✓ Potwierdź');
    assert.equal(s.notices.at(-1).message, 'Brak uprawnień do tej sekcji.');
});

test('HTTP 200 without successful confirmation never removes the pending ingredient', async () => {
    const s = setup({status: 200, body: {success: false, message: 'Nie zapisano.'}});
    s.click(); await settle();
    assert.equal(s.removed(), false);
    assert.equal(s.btn.disabled, false);
    assert.equal(s.notices.at(-1).type, 'danger');
});

test('connection failure preserves the row and reports the error', async () => {
    const s = setup({}, true);
    s.click(); await settle();
    assert.equal(s.removed(), false);
    assert.equal(s.btn.disabled, false);
    assert.match(s.notices.at(-1).message, /nie została potwierdzona/);
});
