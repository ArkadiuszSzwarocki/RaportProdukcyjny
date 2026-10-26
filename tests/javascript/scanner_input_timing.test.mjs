// cspell:words SSCC
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function setup() {
  let time = 0;
  const listeners = {}, globalListeners = {}, timers = new Map(), submitted = [];
  const input = { value: '', dataset: {}, addEventListener(name, callback) { listeners[name] = callback; } };
  let timerId = 0;
  const context = vm.createContext({
    document: { body: { classList: { contains: () => false } }, activeElement: { tagName: 'BUTTON' }, getElementById: id => id === 'scanInput' ? input : null },
    window: { addEventListener(name, callback) { globalListeners[name] = callback; } }, performance: { now: () => time },
    checkPrinter() {}, hidePallet() {}, hideStation() {}, extractSSCCFromScan: value => value,
    setTimeout(callback) { timers.set(++timerId, callback); return timerId; },
    clearTimeout(id) { timers.delete(id); },
  });
  vm.runInContext(readFileSync(new URL('../../static/js/scanner/modules/scanner_flow.js', import.meta.url), 'utf8'), context);
  context.triggerScan = () => submitted.push(input.value);
  return {
    input, submitted, listeners, globalListeners, context,
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

test('open menu keeps keyboard focus, scanner capture resumes after closing', () => {
  const scanner = setup();
  let focusCount = 0;
  scanner.input.focus = () => { focusCount++; };
  scanner.context.document.body.classList.contains = () => true;
  scanner.globalListeners.keydown({ key: 'A' });
  assert.equal(focusCount, 0);
  scanner.context.document.body.classList.contains = () => false;
  scanner.globalListeners.keydown({ key: 'A' });
  assert.equal(focusCount, 1);
});

for (const code of ['OPK000001788773014226', 'SUR000001792400504394', '123456789012345678', '00123456789012345678']) {
  test(`complete SSCC automatically looks up without Enter: ${code}`, () => {
    const scanner = setup();
    scanner.input.value = code;
    scanner.listeners.input.call(scanner.input);
    scanner.settle();
    assert.deepEqual(scanner.submitted, [code]);
  });
}

test('incomplete typed SSCC waits, a completed pasted SSCC submits', () => {
  const scanner = setup();
  scanner.type('OPK000001788', 200); scanner.settle();
  assert.deepEqual(scanner.submitted, []);
  scanner.listeners.paste(); scanner.input.value = 'OPK000001788773014226';
  scanner.listeners.input.call(scanner.input); scanner.settle();
  assert.deepEqual(scanner.submitted, ['OPK000001788773014226']);
});
