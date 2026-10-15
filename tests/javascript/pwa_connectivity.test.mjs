import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const settle = () => new Promise(resolve => setImmediate(resolve));

function setup(responses = []) {
    let banner, nextTimer = 0;
    const listeners = {}, timers = new Map(), intervals = [], calls = [], classes = new Set();
    const bar = {querySelector: () => ({}), insertBefore: element => {banner = element;},
        classList: {toggle(name, enabled) {if (enabled) classes.add(name); else classes.delete(name);}}};
    const navigator = {onLine: true};
    const document = {hidden: false, getElementById: () => banner, querySelector: () => bar,
        addEventListener: (name, handler) => {listeners[name] = handler;},
        createElement: () => ({style: {}, setAttribute() {}}), body: {prepend() {}}};
    const context = {navigator, document, console, Promise, Error, AbortController,
        localStorage: {setItem() {}},
        window: {location: {pathname: '/', search: ''}, addEventListener: (name, handler) => {listeners[name] = handler;}},
        setInterval: handler => intervals.push(handler),
        setTimeout: (handler, delay) => {const id = ++nextTimer; timers.set(id, {handler, delay}); return id;},
        clearTimeout: id => timers.delete(id),
        fetch: (url, options) => {
            calls.push({url, options});
            const response = responses.shift();
            if (response instanceof Error) return Promise.reject(response);
            return response || Promise.resolve({ok: true, status: 200});
        }};
    vm.runInNewContext(fs.readFileSync('static/js/pwa_init.js', 'utf8'), context);
    return {listeners, calls, classes, navigator, document, banner: () => banner,
        interval: () => intervals.forEach(fn => fn()),
        fire(delay) {
            const found = [...timers].find(([, timer]) => timer.delay === delay);
            assert.ok(found, 'Expected timer ' + delay);
            timers.delete(found[0]); found[1].handler();
        }};
}

test('one failed check retries without declaring the application offline', async () => {
    const s = setup([new Error('temporary'), Promise.resolve({ok: true, status: 200})]);
    s.listeners.DOMContentLoaded(); await settle();
    assert.equal(s.classes.has('connection-offline'), false);
    assert.match(s.banner().textContent, /sprawdzam ponownie/);
    s.fire(2000); await settle();
    assert.equal(s.calls.length, 2);
    assert.equal(s.banner().style.display, 'none');
});

test('two failed checks show offline and successful recovery clears the banner', async () => {
    const s = setup([new Error('temporary'), new Error('still unavailable')]);
    s.listeners.DOMContentLoaded(); await settle();
    s.fire(2000); await settle();
    assert.equal(s.classes.has('connection-offline'), true);
    s.listeners.online(); await settle();
    assert.equal(s.classes.has('connection-offline'), false);
    assert.equal(s.banner().style.display, 'none');
});

for (const status of [401, 403, 503]) {
    test('HTTP ' + status + ' is reported as a session or server problem', async () => {
        const s = setup([Promise.resolve({ok: false, status})]);
        s.listeners.DOMContentLoaded(); await settle();
        assert.equal(s.classes.has('connection-offline'), false);
        assert.match(s.banner().textContent, status === 503 ? /HTTP 503/ : /sesję/);
        assert.equal(s.banner().style.display, 'block');
    });
}

test('overlapping checks are coalesced and background intervals do not poll', async () => {
    let resolve;
    const s = setup([new Promise(done => {resolve = done;})]);
    s.listeners.DOMContentLoaded(); s.listeners.online(); s.interval(); await settle();
    assert.equal(s.calls.length, 1);
    resolve({ok: true, status: 200}); await settle();
    s.document.hidden = true; s.interval(); await settle();
    assert.equal(s.calls.length, 1);
    s.document.hidden = false; s.listeners.visibilitychange(); await settle();
    assert.equal(s.calls.length, 2);
});

test('an old successful response cannot override a newer browser offline event', async () => {
    let resolve;
    const s = setup([new Promise(done => {resolve = done;})]);
    s.listeners.DOMContentLoaded(); await settle();
    s.navigator.onLine = false; s.listeners.offline();
    assert.equal(s.classes.has('connection-offline'), true);
    resolve({ok: true, status: 200}); await settle();
    assert.equal(s.classes.has('connection-offline'), true);
});

test('a hung request times out and confirmed repeated timeouts show offline', async () => {
    const s = setup([new Promise(() => {}), new Promise(() => {})]);
    s.listeners.DOMContentLoaded(); await settle();
    s.fire(8000); await settle();
    assert.equal(s.classes.has('connection-offline'), false);
    s.fire(2000); await settle();
    s.fire(8000); await settle();
    assert.equal(s.classes.has('connection-offline'), true);
});
