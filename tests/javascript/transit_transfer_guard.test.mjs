import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const utils = readFileSync('static/js/magazyn_dostawy/edycja/utils.js','utf8');
const picker = readFileSync('static/js/magazyn_dostawy/edycja/palletPicker.js','utf8');
const api = readFileSync('static/js/magazyn_dostawy/edycja/api.js','utf8');
function setup(bypass=false) {
    const messages=[];
    const nodes={skip_warehouse_lookup:{checked:bypass},lokalizacja_do:{value:''},scanner_input:{value:'SUR000000000000000001',focus(){}},pallet_count:{value:'1'}};
    const context=vm.createContext({window:{EdycjaConfig:{linia:'PSD',dostawaId:'wrong-mm',wszystkieProdukty:['WPP']}},
        items:[],READ_ONLY_MODE:false,KNOWN_SOURCE_LOCATIONS_SET:new Set(['MS01','MP01','WTRANZYCIEOSIP']),document:{getElementById:id=>nodes[id]||null},
        showToast:(message)=>messages.push(message),URL,console,saveDraftState(){},updateSaveButtonState(){}});
    vm.runInContext(utils,context);
    return {context,messages,nodes};
}

for (const bypass of [false,true]) {
    test(`transit rows are incomplete and block save even when lookup bypass is ${bypass}`,()=>{
        const {context}=setup(bypass);
        const item={productName:'WPP',sourceSpot:'W_TRANZYCIE_OSIP',netWeight:1000,packageForm:'raw',unit:'kg'};
        context.items.push(item);
        assert.equal(context.isItemComplete(item),false);
        assert.ok(context.getSaveBlockers().some(message=>message.includes('tranzycie')));
    });
}

test('a cached picker result cannot append or reserve a pallet in transit',()=>{
    const {context,messages}=setup(true);
    vm.runInContext(picker,context);
    context.appendPalletsToItems([{id:4092,nr_palety:'SSCC',lokalizacja:'W_TRANZYCIE_OSIP'}]);
    assert.equal(context.items.length,0);
    assert.ok(messages[0].includes('tranzycie'));
});

test('lookup displays the server transit reason instead of adding a row',async()=>{
    const {context,messages}=setup();
    context.fetch=async()=>({json:async()=>({success:true,pallets:[],unavailable_reason:'Paleta jest w tranzycie OSIP.'})});
    context.appendPalletsToItems=()=>{throw new Error('must not append');};
    vm.runInContext(api,context);
    await context.lookupAndAddPallets();
    assert.equal(messages[0],'Paleta jest w tranzycie OSIP.');
});

test('a reservation rejection cannot leave a green complete form',async()=>{
    const {context,messages}=setup();
    const item={productName:'WPP',sourceSpot:'MS01',netWeight:1000,packageForm:'raw',unit:'kg',nr_palety:'SSCC'};
    context.items.push(item);
    assert.equal(context.isItemComplete(item),true);
    context.fetch=async()=>({json:async()=>({success:false,error:'Paleta jest w tranzycie.'})});
    vm.runInContext(api,context);
    context.ensureLiveTransferInitialized=async()=> 'wrong-mm';
    await context.addLiveTransferItem(item);
    assert.equal(item.transfer_error,'Paleta jest w tranzycie.');
    assert.equal(context.isItemComplete(item),false);
    assert.ok(context.getSaveBlockers().includes(item.transfer_error));
    assert.equal(messages[0],item.transfer_error);
});
