// cspell:ignore dostawa
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function screen(answer) {
    const calls = [];
    const button = {disabled:false};
    const context = vm.createContext({
        window:{PRZYJECIE_RUCHU_CONFIG:{dostawaId:'test-order', totalCount:2}},
        document:{addEventListener(){}, getElementById:id => id.startsWith('reject_btn_') ? button : null},
        prompt(){ throw new Error('Native prompt must not be used'); },
        showToast(){}, setTimeout(){},
        fetch:async (url, options) => {calls.push({url,body:JSON.parse(options.body)}); return {json:async () => ({success:true,accepted_count:0,rejected_count:1})};},
    });
    // The shared dialog is a global const, so window.AppDialog is undefined.
    vm.runInContext(`const AppDialog = {prompt: async () => ${JSON.stringify(answer)}};`, context);
    vm.runInContext(readFileSync('static/js/magazyn_dostawy/przyjecie_ruchu.js','utf8'), context);
    vm.runInContext('markRowAsProcessed = () => {};', context);
    return {context, calls, button};
}

test('rejection opens the app dialog and sends the confirmed reason', async () => {
    const {context,calls} = screen('Missing pallet');
    await context.rejectItem('item-one',0);
    assert.equal(calls.length,1);
    assert.equal(calls[0].url,'/magazyn-dostawy/api/odrzuc-pozycje/test-order');
    assert.deepEqual(calls[0].body,{item_id:'item-one',reason:'Missing pallet'});
});

test('canceling the rejection dialog leaves the pallet unchanged', async () => {
    const {context,calls,button} = screen(null);
    await context.rejectItem('item-one',0);
    assert.equal(calls.length,0);
    assert.equal(button.disabled,false);
});
