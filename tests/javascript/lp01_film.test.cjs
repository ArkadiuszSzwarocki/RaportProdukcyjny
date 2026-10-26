const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static/js/lp01_film.js', 'utf8');
function setup(prefix = 'lp01') {
  class Option {
    constructor(text, value) { this.textContent = text; this.value = String(value); this.dataset = {}; this.disabled = false; }
  }
  function select(options) {
    return {options, dataset: {}, value: options[0].value, disabled: false,
      get selectedOptions() {return this.options.filter(o => o.value === this.value);},
      replaceChildren(...items) {this.options = items; this.value = items[0].value;},
      add(item) {this.options.push(item);},
      querySelector(selector) {return this.options.find(o => selector === '[value=' + o.value + ']');}
    };
  }
  const fields = Object.fromEntries(['error', 'status', 'retry'].map(k => [k, {textContent: '', hidden: true, style: {}}]));
  const panel = {hidden: true, setAttribute() {}, querySelector(s) {return fields[s.slice(11, -1)];}};
  const elements = {
    [prefix+'FilmFields']: panel,
    [prefix+'FilmPlan']: select([new Option('', '')]),
    [prefix+'FilmRole']: select(['active','prepared','replace'].map(v => new Option(v,v))),
    [prefix+'PreviousWrap']: {hidden: true},
    [prefix+'PreviousRemaining']: {value: '', required: false},
    [prefix === 'lp01' ? 'btnConfirmLP01' : 'dispConfirmBtn']: {disabled: false}
  };
  const requests = [];
  const timers = [];
  const window = {crypto: {randomUUID: (() => {let n=0; return () => String(++n);})()}};
  vm.runInNewContext(source, {window, document: {getElementById: id => elements[id]}, Option, AbortController,
    setTimeout(fn) {timers.push(fn); return timers.length;}, clearTimeout() {},
    fetch(url, {signal}) {return new Promise((resolve,reject) => {
      requests.push({resolve: plans => resolve({ok:true,json:async()=>({success:true,plans})}), reject});
      signal.addEventListener('abort', () => reject(Object.assign(new Error(), {name:'AbortError'})));
    });}
  });
  return {api:window.Lp01Film, elements, fields, requests, timers,
    load: () => window.Lp01Film.load(prefix, 'Film', true, 1),
    plan:elements[prefix+'FilmPlan'], role:elements[prefix+'FilmRole'],
    previous:elements[prefix+'PreviousWrap'], remaining:elements[prefix+'PreviousRemaining'],
    submit:elements[prefix === 'lp01' ? 'btnConfirmLP01' : 'dispConfirmBtn']};
}
const plan = {id:322, produkt:'Test',status:'w toku',data_planu:'2026-10-25',wymagana_folia:'Film',used_rolls:1,total_rolls:1};
(async () => {
  for (const prefix of ['lp01','dispatch']) {
    const s = setup(prefix);
    const pending = s.load();
    assert.equal(s.submit.disabled,true);
    assert.equal(s.plan.disabled,true);
    assert.equal(s.role.disabled,true);
    assert.equal(s.api.ready(prefix),false);
    s.requests[0].resolve([plan]); await pending;
    assert.equal(s.submit.disabled,false);
    assert.equal(s.plan.value,'322');
    assert.equal(s.role.disabled,false);
    s.role.value='replace'; s.role.onchange();
    assert.equal(s.previous.hidden,false);
    assert.equal(s.remaining.required,true);
    assert.equal(s.api.selection(prefix).roll_role,'replace');
    s.plan.value=''; s.plan.onchange();
    assert.equal(s.role.disabled,true);
    assert.equal(s.previous.hidden,true);
    assert.equal(s.remaining.required,false);
    assert.equal(s.api.selection(prefix),null);
  }
  const s = setup();
  let pending=s.load(); s.timers[0](); await pending;
  assert.equal(s.submit.disabled,true);
  assert.equal(s.fields.retry.hidden,false);
  assert.equal(s.api.ready('lp01'),false);
  pending=s.fields.retry.onclick(); s.requests[1].resolve([]); await pending;
  assert.equal(s.submit.disabled,false);
  assert.equal(s.fields.retry.hidden,true);
  assert.equal(s.role.disabled,true);
  assert.equal(s.api.ready('lp01'),true);
  const old=s.load(); const newer=s.load();
  await old;
  assert.equal(s.submit.disabled,true,'aborted request must not unlock a newer request');
  s.requests[3].resolve([{...plan,total_rolls:'2',used_rolls:'1'}]); await newer;
  assert.equal(s.role.value,'replace');
  assert.equal(s.previous.hidden,false);
  console.log('LP01 UI: loading, assignment, replacement, no order, timeout, retry and stale requests passed.');
})().catch(error => {console.error(error);process.exitCode=1;});
