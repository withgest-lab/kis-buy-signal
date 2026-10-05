/* iOS 풀다운 메뉴 — 모든 <select>를 둥근 팝오버(접힘 ≤480px은 아래에서 올라오는 시트)로 연다.
   원본 <select>는 그대로 두고(값·onchange·클래스·레이아웃 불변) OS 기본 목록이 뜨는 것만 가로채 커스텀 메뉴로 바꾼다.
   새 select는 그냥 <select>로 쓰면 자동 적용된다. 제외: multiple/size>1, data-native 속성.
   같은 파일을 포트폴리오·현금흐름·매매전략(signals/ios-select.js 복사본)이 쓴다 — 고칠 때 두 곳을 같이 갱신. */
(function () {
  if (window.iosSelect) return;
  var SKIP = function (s) { return s.multiple || s.size > 1 || s.hasAttribute('data-native'); };
  var CHEV = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238e8e93' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E\")";
  var CSS = [
    /* 닫힌 모양: 필터·통화·건보료 입력의 네이티브 외형을 iOS(회색 채움·둥근 모서리·쉐브론)로. .sort-select/.fm-select/.ymon-select는 자기 규칙 유지 */
    'select.ios-sel:not(.sort-select):not(.fm-select):not(.ymon-select){-webkit-appearance:none;appearance:none;border:0;border-radius:10px;',
    'background-color:rgba(118,118,128,.12);background-image:' + CHEV + ';background-repeat:no-repeat;background-position:right 8px center;padding-right:24px;cursor:pointer;}',
    '.ios-menu-dim{position:fixed;inset:0;z-index:2147483000;background:rgba(0,0,0,.28);opacity:0;transition:opacity .18s;}',
    '.ios-menu-dim.in{opacity:1;}',
    '.ios-menu{position:fixed;z-index:2147483001;box-sizing:border-box;overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;',
    'background:var(--surface-1,var(--color-card,#fff));color:var(--text-primary,var(--color-text,#1c1c1e));font-family:inherit;',
    'border:.5px solid var(--hairline,rgba(60,60,67,.18));border-radius:14px;box-shadow:0 12px 32px rgba(0,0,0,.18),0 2px 6px rgba(0,0,0,.06);',
    'padding:4px;opacity:0;transform:scale(.97);transform-origin:var(--ox,50%) var(--oy,0);transition:opacity .12s,transform .12s;}',
    '.ios-menu.in{opacity:1;transform:none;}',
    '.ios-menu.sheet{left:0!important;right:0;bottom:0;top:auto!important;width:auto!important;max-height:62vh!important;border-radius:16px 16px 0 0;border-bottom:0;',
    'padding:6px 6px calc(8px + env(safe-area-inset-bottom));transform:translateY(100%);transition:transform .22s cubic-bezier(.2,.9,.3,1),opacity .12s;}',
    '.ios-menu.sheet.in{transform:none;}',
    '.ios-menu-item{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;box-sizing:border-box;min-height:40px;padding:9px 12px;border:0;background:transparent;',
    'color:inherit;font:inherit;font-size:15px;line-height:1.25;text-align:left;border-radius:10px;cursor:pointer;white-space:nowrap;}',
    '.ios-menu.sheet .ios-menu-item{min-height:48px;font-size:16px;}',
    '.ios-menu-item{position:relative;}',
    '.ios-menu-item + .ios-menu-item::before{content:"";position:absolute;left:12px;right:12px;top:0;height:.5px;background:var(--hairline,rgba(60,60,67,.16));pointer-events:none;}',
    '.ios-menu-item:hover::before,.ios-menu-item.act::before,.ios-menu-item:hover + .ios-menu-item::before,.ios-menu-item.act + .ios-menu-item::before{opacity:0;}',
    '.ios-menu-item:hover,.ios-menu-item.act{background:rgba(118,118,128,.12);}',
    '.ios-menu-item[aria-selected=true]{color:var(--accent,var(--color-accent,#007aff));font-weight:600;}',
    '.ios-menu-item[disabled]{opacity:.38;cursor:default;}',
    '.ios-menu-item svg{flex:0 0 auto;width:16px;height:16px;}',
    '.ios-menu-grp{padding:8px 12px 3px;font-size:11px;font-weight:600;color:var(--text-muted,var(--color-tertiary,#8e8e93));}'
  ].join('');
  var st = document.createElement('style'); st.textContent = CSS; (document.head || document.documentElement).appendChild(st);

  // 스크립트가 값을 직접 바꿔도(.value=…) 메뉴의 선택 표시가 맞도록 — 열 때마다 select의 현재 값을 읽으므로 별도 동기화 불필요

  var cur = null; // {sel, dim, menu, items, idx, onDoc, onKey, onScroll}
  function isNarrow() { return window.innerWidth <= 480 && window.parent === window; }   // 나란히 비교의 iframe(폭 좁음)은 시트 대신 팝오버
  function setVal(sel, v) {
    var d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
    d && d.set ? d.set.call(sel, v) : (sel.value = v);
    sel.dispatchEvent(new Event('input', { bubbles: true }));
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function close(refocus) {
    if (!cur) return; var c = cur; cur = null;
    document.removeEventListener('pointerdown', c.onDoc, true);
    document.removeEventListener('keydown', c.onKey, true);
    window.removeEventListener('resize', c.onClose); window.removeEventListener('scroll', c.onScroll, true);
    c.menu.classList.remove('in'); if (c.dim) c.dim.classList.remove('in');
    setTimeout(function () { c.menu.remove(); if (c.dim) c.dim.remove(); }, 200);
    c.sel.removeAttribute('aria-expanded');
    if (refocus) { try { c.sel.focus({ preventScroll: true }); } catch (e) { c.sel.focus(); } }
  }
  function open(sel) {
    if (cur) { var same = cur.sel === sel; close(); if (same) return; }
    if (sel.disabled) return;
    var menu = document.createElement('div'); menu.className = 'ios-menu'; menu.setAttribute('role', 'listbox');
    var items = [], selIdx = sel.selectedIndex;
    function add(o, i) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'ios-menu-item'; b.setAttribute('role', 'option');
      var on = i === selIdx; b.setAttribute('aria-selected', on ? 'true' : 'false'); b.disabled = !!o.disabled;
      var t = document.createElement('span'); t.textContent = o.textContent; b.appendChild(t);
      if (on) b.insertAdjacentHTML('beforeend', '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="5 12.5 10 17.5 19 7"/></svg>');
      b.addEventListener('click', function (e) { e.stopPropagation(); if (b.disabled) return; setVal(sel, o.value); close(e.detail === 0); });   // 키보드로 골랐을 때만 포커스 복귀(마우스는 포커스 링 없음)
      menu.appendChild(b); items.push(b);
    }
    var opts = sel.options, lastGrp = null;
    for (var i = 0; i < opts.length; i++) {
      var g = opts[i].parentNode && opts[i].parentNode.tagName === 'OPTGROUP' ? opts[i].parentNode : null;
      if (g && g !== lastGrp) { var gl = document.createElement('div'); gl.className = 'ios-menu-grp'; gl.textContent = g.label; menu.appendChild(gl); }
      lastGrp = g; add(opts[i], i);
    }
    var dim = null, sheet = isNarrow();
    if (sheet) { dim = document.createElement('div'); dim.className = 'ios-menu-dim'; document.body.appendChild(dim); menu.classList.add('sheet'); }
    document.body.appendChild(menu);
    var r = sel.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight;
    if (!sheet) {
      var w = Math.max(r.width, 132); menu.style.minWidth = w + 'px';
      var mw = menu.offsetWidth, mh = Math.min(menu.scrollHeight, Math.min(vh * 0.6, 360)); menu.style.maxHeight = mh + 'px';
      var left = Math.min(Math.max(8, r.left), vw - mw - 8);
      if (r.right - mw >= 8 && r.left + mw > vw - 8) left = r.right - mw;        // 오른쪽 끝 select는 오른쪽 맞춤
      var below = vh - r.bottom - 8, above = r.top - 8, top;
      if (mh <= below || below >= above) { top = r.bottom + 6; menu.style.maxHeight = Math.min(mh, below) + 'px'; menu.style.setProperty('--oy', '0'); }
      else { var h2 = Math.min(mh, above); top = r.top - h2 - 6; menu.style.maxHeight = h2 + 'px'; menu.style.setProperty('--oy', '100%'); }
      menu.style.left = left + 'px'; menu.style.top = top + 'px'; menu.style.setProperty('--ox', Math.max(0, Math.min(100, (r.left + r.width / 2 - left) / mw * 100)) + '%');
    }
    var c = { sel: sel, dim: dim, menu: menu, items: items, idx: Math.max(0, selIdx) };
    c.onClose = function () { close(false); };
    c.onScroll = function (e) { if (!menu.contains(e.target)) close(false); };
    c.onDoc = function (e) { if (!menu.contains(e.target) && e.target !== sel) close(false); };
    c.onKey = function (e) {
      var k = e.key, n = items.length; if (!n) return;
      function go(d) { var j = c.idx; for (var s = 0; s < n; s++) { j = (j + d + n) % n; if (!items[j].disabled) break; } hl(j); }
      function hl(j) { items[c.idx] && items[c.idx].classList.remove('act'); c.idx = j; items[j].classList.add('act'); items[j].scrollIntoView({ block: 'nearest' }); }
      if (k === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); }
      else if (k === 'ArrowDown') { e.preventDefault(); go(1); } else if (k === 'ArrowUp') { e.preventDefault(); go(-1); }
      else if (k === 'Home') { e.preventDefault(); hl(0); } else if (k === 'End') { e.preventDefault(); hl(n - 1); }
      else if (k === 'Enter' || k === ' ') { e.preventDefault(); e.stopPropagation(); items[c.idx].click(); }
      else if (k === 'Tab') close(false);
    };
    cur = c;
    document.addEventListener('pointerdown', c.onDoc, true); document.addEventListener('keydown', c.onKey, true);
    window.addEventListener('resize', c.onClose); window.addEventListener('scroll', c.onScroll, true);
    sel.setAttribute('aria-expanded', 'true');
    items[c.idx] && items[c.idx].classList.add('act');
    requestAnimationFrame(function () { menu.classList.add('in'); if (dim) dim.classList.add('in'); var a = items[c.idx]; if (a) a.scrollIntoView({ block: 'nearest' }); });
    if (dim) dim.addEventListener('click', function () { close(true); });
  }

  // OS 기본 목록이 뜨는 것을 막고 우리 메뉴를 연다(위임 — 나중에 생기는 select도 자동)
  function target(e) { var t = e.target; return t && t.tagName === 'SELECT' && !SKIP(t) ? t : null; }
  document.addEventListener('mousedown', function (e) { var s = target(e); if (s && e.button === 0) { e.preventDefault(); open(s); } }, true);
  document.addEventListener('click', function (e) { var s = target(e); if (s) e.preventDefault(); }, true);
  var tstart = null;
  document.addEventListener('touchstart', function (e) { var s = target(e); tstart = s ? { s: s, x: e.touches[0].clientX, y: e.touches[0].clientY, moved: false } : null; }, { passive: true, capture: true });
  document.addEventListener('touchmove', function (e) { if (tstart && (Math.abs(e.touches[0].clientX - tstart.x) > 8 || Math.abs(e.touches[0].clientY - tstart.y) > 8)) tstart.moved = true; }, { passive: true, capture: true });
  document.addEventListener('touchend', function (e) { var t = tstart; tstart = null; if (t && !t.moved && e.cancelable) { e.preventDefault(); open(t.s); } }, { passive: false, capture: true });
  document.addEventListener('keydown', function (e) {
    if (cur) return; var s = target(e); if (!s) return;
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); open(s); }
  }, true);

  // 닫힌 모양 클래스(.ios-sel) — 지금 있는 select와 나중에 생기는 select 모두
  function mark(root) {
    var list = root.tagName === 'SELECT' ? [root] : (root.querySelectorAll ? root.querySelectorAll('select') : []);
    for (var i = 0; i < list.length; i++) if (!SKIP(list[i])) list[i].classList.add('ios-sel');
  }
  function init() {
    mark(document);
    new MutationObserver(function (ms) { ms.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) mark(n); }); }); }).observe(document.documentElement, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  window.iosSelect = { open: open, close: close };
})();
