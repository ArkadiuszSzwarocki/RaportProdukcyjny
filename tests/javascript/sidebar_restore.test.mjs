import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const scripts=readFileSync('static/js/sidebar.js','utf8');
const restore=scripts.slice(scripts.indexOf('    function restoreSidebarState()'),scripts.indexOf('    // Save scroll position'))+'restoreSidebarState();';
const template=readFileSync('templates/includes/sidebar.html','utf8');
const inline=template.slice(template.indexOf('            var states = {};'),template.indexOf('            // Restore sidebar scroll position'));

for (const [name,source] of [['module',restore],['inline',inline]]) {
    test(`${name}: collapsed preference applies to active section as well`,()=>{
        const sections=[section('active',true,false),section('expanded',false,false),section('closed',false,true)];
        run(source,sections,JSON.stringify({active:false,expanded:true,closed:false}));
        assert.deepEqual(sections.map(s=>s.open),[false,true,false]);
        assert.equal(sections[0].aria,'false');
    });
    test(`${name}: active page is not forcibly expanded without saved state`,()=>{
        for (const saved of [null,'broken','null','[]']) {
            const sections=[section('active',true,false),section('other',false,false)];
            run(source,sections,saved);
            assert.deepEqual(sections.map(s=>s.open),[false,false]);
        }
    });
}
function section(id,active,open) {
    const section={id,open,querySelector:()=>active?{}:null,querySelectorAll:()=>[],
        previousElementSibling:{classList:{contains:()=>true},setAttribute:(_key,value)=>section.aria=value}};
    section.classList={contains:()=>section.open,toggle:(_key,value)=>section.open=value};
    return section;
}
function run(source,sections,saved) {
    vm.runInNewContext(source,{SIDEBAR_STATE_KEY:'sidebar_submenus_state',
        document:{querySelectorAll:()=>sections},localStorage:{getItem:()=>saved},console:{warn(){}}});
}


test('each new login collapses every section and nested group before restoring preferences',()=>{
    const code=template.slice(template.indexOf('            var loginToken ='),template.indexOf('            // Restore sidebar scroll position'));
    const sections=[section('active',true,true),section('other',false,true)];
    const groups=[{open:true},{open:true}];
    const saved=new Map([['sidebar_login_session','old'],['sidebar_submenus_state','{"active":true,"other":true}']]);
    const context={document:{getElementById:()=>({getAttribute:()=> 'new'}),
        querySelectorAll:selector=>selector==='.nav-sub'?sections:groups},
        localStorage:{getItem:key=>saved.get(key),setItem:(key,value)=>saved.set(key,value)}};
    for (const sub of sections) sub.classList.remove=()=>sub.open=false;
    vm.runInNewContext(code,context);
    assert.deepEqual(sections.map(s=>s.open),[false,false]);
    assert.deepEqual(groups.map(s=>s.open),[false,false]);
    sections[0].open=true;
    saved.set('sidebar_submenus_state','{"active":true,"other":false}');
    vm.runInNewContext(code,context);
    assert.equal(sections[0].open,true,'a page transition during the same login preserves manual expansion');
});
