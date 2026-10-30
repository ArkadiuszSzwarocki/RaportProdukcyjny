import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../../static/js/sidebar.js',import.meta.url),'utf8').replace(/\r\n/g,'\n');
const start=source.indexOf("        ['mag-sub', 'osip-sub'].forEach(id => {");
const end=source.indexOf('\n    }\n    let sidebarBadgesPending',start);
const code=source.slice(start,end);
for(const [name,badges,expected] of [
    ['hidden zero does not create a dot',[{textContent:'0',hidden:false,style:{display:'none'}}],0],
    ['visible zero does not create a dot',[{textContent:'0',hidden:false,style:{display:'inline-flex'}}],0],
    ['positive visible badge creates a dot',[{textContent:'1/3',hidden:false,style:{display:'inline-flex'}}],1],
    ['hidden positive badge does not create a dot',[{textContent:'3',hidden:true,style:{display:'inline-flex'}}],0],
])test(name,()=>{
    let dots=0;
    const label={querySelectorAll:()=>[],appendChild:()=>dots++};
    const sub={querySelectorAll:()=>badges,parentElement:{querySelector:()=>label}};
    vm.runInNewContext(code,{document:{getElementById:id=>id==='mag-sub'?sub:null,createElement:()=>({setAttribute(){}})},getComputedStyle:badge=>badge.style});
    assert.equal(dots,expected);
});
