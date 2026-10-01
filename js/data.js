/* 首页(最新收录、数据覆盖、各领域条数)/ 演进脉络 / 趋势图数据注入。
   「找政策」的检索与列表在 js/search.js。取数与降级由 js/api.js 负责;这里只管把数据变成 DOM。 */

const { getData, esc, set } = window.PolicyData;

const DIR_LABEL = { tight: '▲ 收紧', loose: '▼ 放宽' };

/* 一律按曼谷时间显示 —— 泰国政策的生效时点以泰国当地时间为准,
   按访客本地时区渲染会让「今天刊登」看起来像昨天。 */
function fmtStamp(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  return d.toLocaleString('sv-SE', { timeZone: 'Asia/Bangkok', hour12: false }).slice(0, 16)
    + ' 曼谷时间';
}

function originLink(p) {
  if (!p.source_url) return '';
  return `<span><a href="${esc(p.source_url)}" target="_blank" rel="noopener"
    onclick="event.stopPropagation()">泰文原文 ↗</a></span>`;
}

const STANCE_PREFIX = { constrain: '约束 · ', support: '利好 · ', neutral: '' };

/* 影响对象 chip,最多 2 个 */
function partyChips(p, max = 2) {
  return (p.parties || []).slice(0, max).map(x =>
    `<span class="party ${esc(x.stance)}">${esc(STANCE_PREFIX[x.stance] || '')}${esc(x.label)}</span>`).join('');
}

function cut(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n) + '…' : s; }

function policyCard(p) {
  const clickable = ` onclick="openDetail('${esc(p.uid)}')" style="cursor:pointer"`;
  const pub = (p.dates && p.dates.published_at) || p.date;
  const points = (p.key_points || []).slice(0, 2);
  const meta = [
    p.org ? `<span>${esc(p.org)}</span>` : '',
    p.doc_no ? `<span>${esc(p.doc_no_label || '文号')} <b>${esc(p.doc_no)}</b></span>` : '',
    pub ? `<span>刊登 ${esc(pub)}</span>` : '',
    originLink(p)
  ].filter(Boolean).join('');
  // 方向只显示收紧 / 放宽;「中性」满屏都是,只是噪音
  const dir = p.direction === 'tight' || p.direction === 'loose'
    ? `<span class="dir ${esc(p.direction)}">${DIR_LABEL[p.direction]}</span>` : '';
  return `<div class="card policy-card"${clickable}>
    <div class="pc-top">
      <span class="chip ${esc(p.domain)}">${esc(p.domain_label)}</span>
      ${dir}${partyChips(p)}
      ${p.verified ? '<span class="verified">已人工复核</span>' : ''}
    </div>
    <a class="pc-title" href="p/${esc(String(p.uid).toLowerCase())}.html"
      onclick="if (event.ctrlKey || event.metaKey || event.shiftKey || event.button === 1) { event.stopPropagation(); } else { event.preventDefault(); }">${esc(p.title_zh)}</a>
    ${points.length
      ? `<div class="pc-sum">${esc(p.summary_zh)}</div><ul class="pc-points">${points.map(k => `<li>${esc(k)}</li>`).join('')}</ul>`
      : `<div class="pc-sum"><span class="thin-tag">摘要仅据标题</span>${esc(cut(p.summary_zh, 90))}</div>`}
    <div class="pc-meta">${meta}</div>
  </div>`;
}

/* ── 演进脉络:议题可切换 ── */
function lineageChain(issue) {
  return issue.stages.map(s => `<div class="ln-item${s.milestone ? ' milestone' : ''}">
    <div class="ln-stage">${esc(s.stage)}</div>
    <div class="ln-card"${s.uid ? '' : ' style="border-style:dashed"'}>
      <div class="ln-title">${esc(s.title)}</div>
      ${s.meta ? `<div class="ln-meta">${esc(s.meta)}</div>` : ''}
      ${s.note ? `<div class="ln-note">${esc(s.note)}</div>` : ''}
    </div></div>`).join('');
}

function renderLineage(data) {
  const issues = (data.issues || []).filter(i => i.stages && i.stages.length);
  if (!issues.length) {
    // 议题必须挂在已考证的官方文件上;还没有时明说,不留旧的占位内容
    set('lineage-sub', '把同一议题的草案、决议、公报、修订串成一条可追溯的链。');
    set('lineage-picker', ' ');
    set('lineage', '<div class="reading">暂无可展示的议题脉络:每个议题至少要关联一份带官方原文(泰国政府网站)的文件才会在这里出现。'
      + '随着公报每日入库与翻译,议题会陆续上线。</div>');
    return;
  }
  let current = issues[0].issue_id;
  const draw = () => {
    const it = issues.find(i => i.issue_id === current) || issues[0];
    set('lineage-picker', issues.map(i =>
      `<div class="facet" data-issue="${esc(i.issue_id)}"${i.issue_id === current
        ? ' style="border-color:var(--seal);color:var(--seal)"' : ''}>${esc(i.title_zh)}
       <span style="color:var(--muted)">${i.stages.length}</span></div>`).join(''));
    set('lineage-sub', `当前议题:<b>${esc(it.title_zh)}</b> · ${esc(it.summary_zh)}`
      + (it.watch ? ` <span style="color:var(--muted)">前瞻:${esc(it.watch)}</span>` : ''));
    set('lineage', lineageChain(it));
    document.querySelectorAll('#lineage-picker .facet').forEach(el =>
      el.addEventListener('click', () => { current = el.dataset.issue; draw(); }));
  };
  draw();
}

function monthDay(d) { return d ? String(d).slice(0, 10) : '—'; }

function renderOverview(d) {
  // 顺序以后端为准(有要点的在前,同组日期倒序),前后端同一规则
  const policies = (d.policies || []).slice();
  window.POLICIES = policies;      // detail.js / search.js 从这里取数据
  window.OVERVIEW_STATS = d.stats || {};
  const st = d.stats || {};
  const total = st.total || policies.length;
  const updated = d.updated_at ? fmtStamp(d.updated_at).slice(0, 10) : '—';

  set('feed', policies.filter(p => p.featured).map(policyCard).join('')
    || '<div class="card"><div class="pc-sum">暂无可展示的政策。</div></div>');
  if (window.PolicyAds) window.PolicyAds.injectFeed(document.getElementById('feed'));
  set('today-sub', `最近收录的 <b>${total}</b> 条公报,读过原文、有要点的排在前面。`);
  set('feed-more', `查看全部 ${total} 条 →`);
  set('lag-note', `泰国官方公报数据集(data.go.th)通常比刊登日晚几个月开放。本站现已收录到 <b>${esc(monthDay(st.date_to))}</b> 刊登的公报,`
    + `最近一次采集 ${esc(updated)}。不是停更,是官方数据集的节奏。`);
  set('coverage', `<div class="cov-row"><span>收录</span><b>${total} 条</b></div>`
    + `<div class="cov-row"><span>已读原文、有要点</span><b>${st.with_points || 0} 条</b></div>`
    + `<div class="cov-row"><span>公报日期</span><b>${esc(st.date_from || '—')} 至 ${esc(st.date_to || '—')}</b></div>`
    + `<div class="cov-row"><span>最近采集</span><b>${esc(updated)}</b></div>`);
  set('domain-counts', (st.by_domain || []).map(x =>
    `<a class="cov-row dom-count" href="#search?domain=${esc(x.id)}" data-domain="${esc(x.id)}">`
    + `<span><span class="chip ${esc(x.id)} bare">${esc(x.zh)}</span></span><b>${x.n}</b></a>`).join('')
    || '<div class="mod-sub">暂无数据</div>');
  if (window.PolicySearch) window.PolicySearch.dataReady();

  // 采集管道的运行状态只在管理后台(/admin)显示,前台只告诉读者数据更新到什么时候
  set('stamp', `数据更新 ${fmtStamp(d.updated_at)}`);
}

getData('overview').then(renderOverview).catch(err => {
  console.warn('[overview] 未加载,页面保留静态示意数据:', err.message);
  window.DATA_MODE = 'inline';
  set('stamp', '');
});

/* 订阅卡片:全站 RSS、按领域 RSS、Telegram 频道(配置了才显示)、按周汇总 */
fetch('data/site/subscribe.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(sub => {
  if (!sub) return;
  const feeds = (sub.feeds || []).map(f => `<a href="${esc(f.href)}">${esc(f.zh)}</a>`).join(' · ');
  const weeks = (sub.weeks || []).map(w =>
    `<a class="cov-row" href="${esc(w.href)}"><span>${esc(w.from.slice(5))} 至 ${esc(w.to.slice(5))}</span><b>${w.n} 条</b></a>`).join('');
  set('subscribe',
    (sub.telegram_channel_url
      ? `<a class="btn-solid sub-tg" href="${esc(sub.telegram_channel_url)}" target="_blank" rel="noopener">Telegram 频道 · 新政策推送</a>` : '')
    + `<div class="sub-line"><a href="feed.xml">RSS 订阅全站更新</a></div>`
    + (feeds ? `<details class="sub-more"><summary>按领域订阅 RSS</summary><div>${feeds}</div></details>` : '')
    + (weeks ? `<div class="mod-sub" style="margin-top:10px">按周汇总(按公报刊登日)</div>${weeks}`
      + `<div style="margin-top:6px;font-size:12.5px"><a href="p/week/index.html">全部周汇总 →</a></div>` : ''));
}).catch(() => { /* 订阅卡片保留静态的 RSS 链接 */ });

getData('trends').then(t => {
  window.TRENDS = t;
  set('trends-sub', `基于库内 <b>${t.total_documents}</b> 条政策聚合 · 数据截至 <b>${t.data_through}</b>`
    + (t.gazette_through ? ` · 泰国官方公报数据集目前更新至 ${t.gazette_through}` : ''));
  // 真实数据可能比首次进入趋势页更晚到达 —— initCharts 可重复调用
  if (typeof initCharts === 'function' && document.querySelector('#c-stack canvas')) initCharts();
}).catch(err => console.warn('[trends] 未加载:', err.message));

getData('lineage').then(renderLineage)
  .catch(err => console.warn('[lineage] 未加载,脉络页保留静态内容:', err.message));

/* 首页简介条:关闭后记住,隐私模式下存储不可用就每次都显示 */
(function () {
  const bar = document.getElementById('intro');
  if (!bar) return;
  try { if (localStorage.getItem('intro_closed') === '1') bar.hidden = true; } catch (e) { /* 忽略 */ }
  const x = document.getElementById('intro-close');
  if (x) x.addEventListener('click', () => {
    bar.hidden = true;
    try { localStorage.setItem('intro_closed', '1'); } catch (e) { /* 忽略 */ }
  });
})();
