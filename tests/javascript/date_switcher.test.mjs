import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function setup(initialized = false) {
    const events = {}, tileEvents = {}, redirects = [];
    const attributes = {'data-current-date': '2026-09-28', 'data-date-mode': 'url', 'data-date-param': 'data'};
    const label = {textContent: '28.09.26'};
    let openings = 0;
    const input = {value: '2026-09-28', matches: () => true, closest: () => picker,
        showPicker() {openings++;}};
    const tile = {addEventListener(name, fn) {tileEvents[name] = fn;}};
    const picker = {getAttribute: name => attributes[name], setAttribute(name, value) {attributes[name] = value;},
        querySelector: selector => selector.includes('label') ? label : selector.includes('input') ? input : selector.includes('tile') ? tile : null};
    const document = {readyState: 'complete', querySelectorAll: () => initialized ? [picker] : [],
        addEventListener(name, fn) {events[name] = fn;}};
    const window = {scrollY: 50, location: {href: 'http://localhost:18084/?sekcja=Zasyp&linia=AGRO&data=2026-09-28&data_od=2026-09-01&data_do=2026-10-31',
        assign: url => redirects.push(url)}};
    vm.runInNewContext(fs.readFileSync('static/js/common/date-switcher.js', 'utf8'), {window, document, URL, console,
        localStorage: {setItem() {}}});
    return {input, label, events, tileEvents, redirects, openings: () => openings};
}

test('selecting October 11 in a dynamically inserted picker changes dashboard date', () => {
    const s = setup();
    s.input.value = '2026-10-11';
    s.events.change({target: s.input});
    assert.equal(s.label.textContent, '11.10.26');
    const url = new URL(s.redirects[0]);
    assert.equal(url.searchParams.get('data'), '2026-10-11');
    assert.equal(url.searchParams.get('sekcja'), 'Zasyp');
    assert.equal(url.searchParams.get('linia'), 'AGRO');
    assert.equal(url.searchParams.has('data_od'), false);
    assert.equal(url.searchParams.has('data_do'), false);
});

test('input and change from one selection navigate only once', () => {
    const s = setup(true);
    s.input.value = '2026-10-11';
    s.events.input({target: s.input});
    s.events.change({target: s.input});
    assert.equal(s.redirects.length, 1);
});

test('initialized picker opens calendar once and stops duplicate delegated click', () => {
    const s = setup(true);
    let stopped = false;
    s.tileEvents.click({stopPropagation() {stopped = true;}});
    assert.equal(s.openings(), 1);
    assert.equal(stopped, true);
});
