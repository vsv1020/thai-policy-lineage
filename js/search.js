/* 找政策:前端本地检索。
   全部可呈现的政策(几百条)已随首页数据加载到 window.POLICIES,在浏览器里筛选即可 ——
   API 模式与静态降级模式行为一致,不依赖 /api/documents。
   地址栏 #search?q=…&domain=…&party=…&form=… 可分享、可回退。 */

(function () {
  const { esc, set } = window.PolicyData;
  const state = { q: '', domain: '', party: '', form: '' };
  const MAX_ROWS = 300;
  let ready = false;
  let pendingOpen = null;
  let lastTracked = '';

  const norm = s => String(s == null ? '' : s).toLowerCase();
  const hay = p => norm([p.title_zh, p.title_th, p.summary_zh, (p.key_points || []).join(' '),
    p.doc_no, p.org].join(' '));

  function matches(p, terms) {
    if (state.domain && p.domain !== state.domain) return false;
    if (state.party && !(p.parties || []).some(x => x.id === state.party)) return false;
    if (state.form && p.legal_form !== state.form) return false;
    if (!terms.length) return true;
    const h = p._hay || (p._hay = hay(p));
    return terms.every(t => h.includes(t));
  }

  function row(p) {
    const parties = (p.parties || []).slice(0, 2).map(x => `<span class="party ${esc(x.stance)}">${esc(x.label)}</span>`).join('');
    return `<div class="lib-row" onclick="openDetail('${esc(p.uid)}')" style="cursor:pointer">
      <span class="lib-date">${esc(p.date)}</span>
      <div><div class="lib-title">${esc(p.title_zh)}</div>
        <div class="lib-sub"><span class="chip ${esc(p.domain)}">${esc(p.domain_label)}</span>${parties}</div></div>
      <span class="pill ${(p.key_points || []).length ? 'st-active' : 'st-draft'}">${(p.key_points || []).length ? '✓ 有要点' : '仅据标题'}</span>
    </div>`;
  }

  function options(list, cur, all) {
    return [`<option value="">${esc(all)}</option>`].concat(list.map(([v, t]) =>
      `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(t)}</option>`)).join('');
  }

  function drawFacets() {
    const P = window.POLICIES || [];
    const doms = new Map(), parties = new Map(), forms = new Map();
    P.forEach(p => {
      if (p.domain) doms.set(p.domain, p.domain_label);
      (p.parties || []).forEach(x => parties.set(x.id, x.label));
      if (p.legal_form) forms.set(p.legal_form, p.legal_form);
    });
    const sorted = m => [...m.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1]), 'zh'));
    set('facets',
      `<label class="facet">领域 <select data-key="domain">${options(sorted(doms), state.domain, '全部')}</select></label>`
      + `<label class="facet">影响对象 <select data-key="party">${options(sorted(parties), state.party, '全部')}</select></label>`
      + `<label class="facet">法律形式 <select data-key="form">${options(sorted(forms), state.form, '全部')}</select></label>`
      + `<button type="button" class="facet facet-reset" id="facet-reset">清空条件</button>`);
    document.querySelectorAll('#facets select').forEach(el =>
      el.addEventListener('change', () => { state[el.dataset.key] = el.value; run(true); }));
    const r = document.getElementById('facet-reset');
    if (r) r.addEventListener('click', () => {
      Object.assign(state, { q: '', domain: '', party: '', form: '' });
      const q = document.getElementById('sq'); if (q) q.value = '';
      drawFacets(); run(true);
    });
  }

  function syncHash() {
    const p = new URLSearchParams();
    Object.entries(state).forEach(([k, v]) => { if (v) p.set(k, v); });
    const h = '#search' + (p.toString() ? '?' + p : '');
    if (location.hash !== h) history.replaceState(null, '', h);
  }

  function run(track) {
    if (!ready) return;
    const P = window.POLICIES || [];
    const terms = norm(state.q).split(/\s+/).filter(Boolean);
    const hits = P.filter(p => matches(p, terms));
    const st = window.OVERVIEW_STATS || {};
    syncHash();
    const cond = [state.q && `含「${esc(state.q)}」`,
      state.domain && (P.find(p => p.domain === state.domain) || {}).domain_label,
      state.party && ((P.flatMap(p => p.parties || []).find(x => x.id === state.party)) || {}).label,
      state.form].filter(Boolean).join(' · ');
    set('lib-count', `找到 <b>${hits.length}</b> 条${cond ? ',' + cond : ''}`
      + (hits.length > MAX_ROWS ? `(显示前 ${MAX_ROWS} 条)` : ''));
    set('lib', hits.length ? hits.slice(0, MAX_ROWS).map(row).join('')
      : `<div class="lib-row"><div class="empty-hint">没有找到${state.q ? `包含「${esc(state.q)}」的` : '符合条件的'}政策。`
        + `试试更短的词(如 土地、进口、利率),或按领域浏览。本站目前收录 ${st.total || P.length} 条,公报日期到 ${esc(st.date_to || '—')}。</div></div>`);
    if (track && state.q && state.q !== lastTracked && window.PolicyTrack) {
      lastTracked = state.q;
      PolicyTrack.search(state.q, hits.length);
    }
  }

  function parseHash() {
    const m = location.hash.match(/^#search(?:\?(.*))?$/);
    if (!m) return null;
    const p = new URLSearchParams(m[1] || '');
    return { q: p.get('q') || '', domain: p.get('domain') || '', party: p.get('party') || '', form: p.get('form') || '' };
  }

  /* 打开「找政策」并带上条件;数据没到时先记下,到了再执行 */
  function open(params) {
    Object.assign(state, { q: '', domain: '', party: '', form: '' }, params || {});
    if (typeof go === 'function') go('search');
    const q = document.getElementById('sq'); if (q) q.value = state.q;
    if (!ready) { pendingOpen = true; return; }
    drawFacets(); run(true);
  }

  function dataReady() {
    ready = true;
    drawFacets();
    if (pendingOpen) { pendingOpen = null; run(true); } else run(false);
  }

  // 搜索框:回车或按钮立即执行;输入时 300ms 防抖同步
  const form = document.getElementById('search-form');
  const sq = document.getElementById('sq');
  if (form) form.addEventListener('submit', e => { e.preventDefault(); state.q = sq.value.trim(); run(true); });
  if (sq) { let t; sq.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { state.q = sq.value.trim(); run(false); }, 300); }); }

  const home = document.getElementById('home-search');
  if (home) home.addEventListener('submit', e => {
    e.preventDefault(); open({ q: document.getElementById('home-q').value.trim() });
  });
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-domain]');
    if (b && (b.classList.contains('dom-btn') || b.classList.contains('dom-count'))) {
      e.preventDefault(); open({ domain: b.dataset.domain });
    }
  });
  window.addEventListener('hashchange', () => { const h = parseHash(); if (h) open(h); });
  const initial = parseHash();
  if (initial) open(initial);

  window.PolicySearch = { open, dataReady };
})();
