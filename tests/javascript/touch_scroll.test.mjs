// cspell:words overscroll
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
function setup(pageTop = 0) {
  const listeners = {};
  const body = { scrollTop: 0 }, root = { scrollTop: pageTop };
  vm.runInNewContext(readFileSync(new URL('../../static/js/common/touch-scroll.js', import.meta.url), 'utf8'), {
    document: { body, documentElement: root, addEventListener(name, handler) { listeners[name] = handler; } },
    window: { pageYOffset: pageTop }, getComputedStyle: element => ({ overflowY: element.overflow || 'visible' }),
  });
  return { body, gesture(target, from, to, extra = {}) {
    let prevented = false;
    listeners.touchstart({ touches: [{ clientY: from }] });
    listeners.touchmove({ target, touches: [{ clientY: to }], cancelable: true, preventDefault() { prevented = true; }, ...extra });
    return prevented;
  } };
}
test('drawer scrolls downward even when the underlying page is at the top', () => {
  const guard = setup();
  const drawer = { overflow: 'auto', scrollHeight: 900, clientHeight: 600, scrollTop: 200, parentElement: guard.body };
  assert.equal(guard.gesture({ parentElement: drawer }, 100, 300), false);
  drawer.scrollTop = 0;
  assert.equal(guard.gesture(drawer, 100, 300), false);
  assert.equal(guard.gesture(drawer, 300, 100), false);
});
test('page pull-to-refresh remains blocked, ordinary page scroll remains available', () => {
  const guard = setup();
  assert.equal(guard.gesture(guard.body, 100, 300), true);
  assert.equal(guard.gesture(guard.body, 300, 100), false);
  assert.equal(guard.gesture(guard.body, 100, 300, { cancelable: false }), false);
  assert.equal(guard.gesture(guard.body, 100, 300, { touches: [{clientY:300}, {clientY:300}] }), false);
  const scrolled = setup(100);
  assert.equal(scrolled.gesture(scrolled.body, 100, 300), false);
});
test('short non-scrollable panels do not bypass the page guard', () => {
  const guard = setup();
  assert.equal(guard.gesture({ overflow:'auto', scrollHeight:100, clientHeight:100, parentElement:guard.body },100,300), true);
});
