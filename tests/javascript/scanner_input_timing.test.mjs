// cspell:words SSCC
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function setup() {
  let time = 0;
  const listeners = {}, timers = new Map(), submitted = [];
  const input = { value: '', addEventListener(name, callback) { listeners[name] = callback; } };
  let timerId = 0;
  const context = vm.createContext({
    document: { getElementById: id => id === 'scanInput' ? input : null },
    window: { addEventListener() {} }, performance: { now: () => time },
    checkPrinter() {}, hidePallet() {}, hideStation() {}, extractSSCCFromScan: value => value,
    setTimeout(callback) { timers.set(++timerId, callback); return timerId; },
    clearTimeout(id) { timers.delete(id); },
  });
  vm.runInContext(readFileSync(new URL('../../static/js/scanner/modules/scanner_flow.js', import.meta.url), 'utf8'), context);
  context.triggerScan = () => submitted.push(input.value);
  return {
    input, submitted, listeners,
    type(text, interval) { for (const character of text) { time += interval; input.value += character; listeners.input.call(input); } },
    settle() { for (const callback of [...timers.values()]) callback(); timers.clear(); },
  };
}

test('slow typing waits for explicit confirmation and never submits MP0', () => {
  const scanner = setup();
  scanner.type('MP01', 200); scanner.settle();
  assert.deepEqual(scanner.submitted, []);
  scanner.listeners.keydown({ key: 'Enter', preventDefault() {} });
  assert.deepEqual(scanner.submitted, ['MP01']);
});

test('fast reader burst submits the complete code once', () => {
  const scanner = setup(); scanner.type('MP01', 8); scanner.settle();
  assert.deepEqual(scanner.submitted, ['MP01']);
});

test('three-character bucket codes also submit from the reader', () => {
  const scanner = setup(); scanner.type('W01', 8); scanner.settle();
  assert.deepEqual(scanner.submitted, ['W01']);
});

test('paste waits for confirmation', () => {
  const scanner = setup(); scanner.listeners.paste(); scanner.input.value = 'MP01';
  scanner.listeners.input.call(scanner.input); scanner.settle();
  assert.deepEqual(scanner.submitted, []);
});
