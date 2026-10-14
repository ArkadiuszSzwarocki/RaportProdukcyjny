import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const code = readFileSync(new URL('../../static/js/sidebar.js', import.meta.url), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

test('receipt refresh bypasses draft cache and hides cleared counts', async () => {
  const badge = {style: {}, getAttribute: () => 'ALL'};
  const storage = new Map([['magazyn_dostawy_draft_ALL_new', JSON.stringify({items: [{nr_palety: 'PHYSICAL-CODE'}]})]]);
  const calls = [];
  let count = 2;
  const context = vm.createContext({
    URL, Date, console, setTimeout, setInterval() {},
    localStorage: {},
    document: {
      readyState: 'loading', addEventListener() {}, getElementById() {return null;},
      querySelectorAll(selector) {return selector === '.nav-draft-badge' ? [badge] : [];}
    },
    window: {
      addEventListener() {}, location: {origin: 'http://localhost'},
      localStorage: {length: storage.size, key: i => [...storage.keys()][i], getItem: key => storage.get(key)}
    },
    async fetch(url) {
      calls.push(url);
      return {ok: true, json: async () => url.includes('draft/check') ?
        {success: true, counts: {ALL: count}, documents: {ALL: count ? 1 : 0}} : {success: true}};
    }
  });
  vm.runInContext(code, context);
  await context.window.updateSidebarDraftBadges();
  assert.equal(badge.textContent, 'SZKIC 1/2');
  count = 0;
  context.window.refreshSidebarBadges();
  await settle();
  assert.equal(badge.style.display, 'none');
  assert.ok(calls.includes('/warehouse-v2/api/sidebar-badges?fresh=1'));
  assert.equal(calls.filter(url => url.includes('draft/check')).length, 2);
});

test('offline message stays inside navbar and clears on recovery', async () => {
  const listeners = {};
  let banner;
  const classes = new Set();
  const bar = {querySelector() {return {};}, insertBefore(element) {banner = element;},
    classList: {toggle(name, enabled) {if (enabled) classes.add(name); else classes.delete(name);}}};
  const context = vm.createContext({
    navigator: {onLine: false}, localStorage: {setItem() {}}, console, setInterval() {}, AbortSignal,
    window: {location: {pathname: '/scanner', search: ''}, addEventListener(name, callback) {listeners[name] = callback;}},
    document: {addEventListener(name, callback) {listeners[name] = callback;},
      getElementById() {return banner;}, querySelector() {return bar;},
      createElement() {return {style: {}, setAttribute() {}};}, body: {prepend() {throw Error('Overlay outside navbar');}}},
    fetch: async () => ({ok: true})
  });
  vm.runInContext(readFileSync(new URL('../../static/js/pwa_init.js', import.meta.url), 'utf8'), context);
  listeners.DOMContentLoaded();
  assert.equal(banner.style.display, 'block');
  assert.ok(classes.has('connection-offline'));
  assert.ok(!banner.style.cssText.includes('position:fixed'));
  context.navigator.onLine = true;
  listeners.online();
  await settle();
  assert.equal(banner.style.display, 'none');
  assert.ok(!classes.has('connection-offline'));
});
