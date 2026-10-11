import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';

function setup() {
  const elements = {}, timers = new Map(), lookedUp = [];
  let timerId = 0, calls = 0;
  const element = () => ({style: {}, children: [], hidden: false, handlers: {},
    appendChild(child) {this.children.push(child); if (child.id) elements[child.id] = child;},
    replaceChildren() {this.children = []; this.textContent = '';}, setAttribute() {},
    addEventListener(event, handler) {this.handlers[event] = handler;}});
  const input = {value: '123456', parentNode: element()};
  elements.scanInput = input;
  const context = vm.createContext({
    document: {getElementById: id => elements[id], createElement: element},
    LINIA: 'AGRO', encodeURIComponent,
    setTimeout(callback) {timers.set(++timerId, callback); return timerId;},
    clearTimeout(id) {timers.delete(id);}, lookupPallet: code => lookedUp.push(code),
    scannerResponseMessage: data => data.message,
    fetch: async () => {calls++; return {json: async () => ({success: true, pallets: [
      {nr_palety: 'SUR000001123456', nazwa: 'Hydro', lokalizacja: 'MS01', ilosc: 1000},
      {nr_palety: 'SUR000002123456', nazwa: 'Soja', lokalizacja: 'MP01', ilosc: 500},
    ]})};},
  });
  vm.runInContext(fs.readFileSync('static/js/scanner/modules/scanner_suggestions.js', 'utf8'), context);
  return {context, input, elements, timers, lookedUp, calls: () => calls};
}

test('six digits show all candidates without choosing or moving a pallet', async () => {
  const s = setup();
  await s.context.requestPalletSuggestions('123456');
  assert.equal(s.elements.palletSuggestions.children.length, 3);
  assert.deepEqual(s.lookedUp, []);
  s.elements.palletSuggestions.children[2].handlers.click();
  assert.deepEqual(s.lookedUp, ['SUR000002123456']);
  assert.equal(s.input.value, 'SUR000002123456');
  assert.equal(s.elements.palletSuggestions.hidden, true);
});

test('search waits for exactly six digits and clears when typing continues', () => {
  const s = setup();
  s.context.schedulePalletSuggestions('12345');
  assert.equal(s.timers.size, 0);
  s.context.schedulePalletSuggestions('123456');
  assert.equal(s.timers.size, 1);
  s.context.schedulePalletSuggestions('1234567');
  assert.equal(s.timers.size, 0);
  assert.equal(s.calls(), 0);
});
