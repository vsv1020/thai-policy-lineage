/* 首页政策流 / 检索列表 / 风向 / 生效日历 / 演进脉络 / 趋势图数据注入。
   取数与降级由 js/api.js 负责;这里只管把数据变成 DOM。 */

const { getData, esc, set } = window.PolicyData;

const DIR_LABEL = { tight: '▲ 收紧', loose: '▼ 放宽', neutral: '● 中性' };
const STATUS_CLASS = { active: 'st-active', soon: 'st-soon', draft: 'st-draft' };

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

function policyCard(p) {
  const clickable = ` onclick="openDetail('${esc(p.uid)}')" style="cursor:pointer"`;
  const meta = [
    p.org ? `<span>${esc(p.org)}</span>` : '',
    p.doc_no ? `<span>${esc(p.doc_no_label || '文号')} <b>${esc(p.doc_no)}</b></span>` : '',
    p.effective_label ? `<span>${esc(p.effective_label)}</span>` : '',
    originLink(p)
  ].filter(Boolean).join('');
  return `<div class="card policy-card"${clickable}>
    <div class="pc-top">
      <span class="chip ${esc(p.domain)}">${esc(p.domain_label)}</span>
      <span class="dir ${esc(p.direction)}">${DIR_LABEL[p.direction] || ''}</span>
      ${p.verified ? '<span class="verified">已人工复核</span>' : ''}
      ${p.provenance === 'demo' ? '<span class="chip bare">示意</span>' : ''}
    </div>
    <div class="pc-title">${esc(p.title_zh)}</div>
    <div class="pc-sum">${esc(p.summary_zh)}</div>
    <div class="pc-meta">${meta}</div>
  </div>`;
}

function libRow(p) {
  const sub = [
    `<span class="chip ${esc(p.domain)}">${esc(p.domain_label)}</span>`,
    esc(p.legal_form || ''),
    p.doc_no ? `${esc(p.doc_no_label || '文号')} ${esc(p.doc_no)}` : ''
  ].filter(Boolean).join(' · ');
  return `<div class="lib-row" onclick="openDetail('${esc(p.uid)}')" style="cursor:pointer">
    <span class="lib-date">${esc(p.date)}</span>
    <div><div class="lib-title">${esc(p.title_zh)}</div><div class="lib-sub">${sub}</div></div>
    <span class="pill ${STATUS_CLASS[p.status] || 'st-draft'}">${esc(p.status_label)}</span>
  </div>`;
}

function windRow(w) {
  const sign = w.score > 0 ? '+' : '';
  return `<div class="gauge-row"><span class="chip ${esc(w.domain)} bare">${esc(w.label)}</span>
    <span class="dir ${esc(w.direction)}">${DIR_LABEL[w.direction] || ''} ${sign}${esc(w.score)}
    <span style="color:var(--muted);font-weight:400">/ ${esc(w.n)} 件</span></span></div>`;
}

function calRow(c) {
  const tag = c.kind === 'deadline' ? ' <span style="color:var(--muted)">(法定截止)</span>' : '';
  return `<div class="cal-item"><span class="cal-date">${esc(String(c.date).slice(5))}</span><span>${esc(c.text)}${tag}</span></div>`;
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
  if (!issues.length) return;
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

window.renderLib = items => set('lib', (items || []).map(libRow).join(''));

function renderOverview(d) {
  const policies = (d.policies || []).slice()
    .sort((a, b) => String(b.date).localeCompare(String(a.date)));
  window.POLICIES = policies;      // detail.js 在静态模式下从这里取单件数据

  set('feed', policies.filter(p => p.featured).map(policyCard).join(''));
  window.renderLib(policies);
  set('wind', (d.wind || []).map(windRow).join(''));
  set('calendar', (d.calendar || []).map(calRow).join(''));
  set('lib-count', `领域 × 机关 × 法律形式 × 状态 × 时间 五维过滤 · 当前库内 <b>${policies.length}</b> 条`);

  const srcs = d.sources || [];
  const ok = srcs.filter(s => s.status === 'ok').length;
  const research = (d.stats || {}).research || 0;
  const health = srcs.length
    ? (ok ? ` · 源 ${ok}/${srcs.length} 可用` : ` · ${srcs.length} 个源均未接通`)
    : '';
  const mode = window.DATA_MODE === 'api' ? '实时接口' : '静态快照';
  set('stamp', `${mode} · 数据更新 ${fmtStamp(d.updated_at)}${health}`
    + (research ? ` · 实采 ${research} 条` : ' · 全部为示意数据'));
}

getData('overview').then(renderOverview).catch(err => {
  console.warn('[overview] 未加载,页面保留静态示意数据:', err.message);
  window.DATA_MODE = 'inline';
  set('stamp', '静态示意数据(未加载 overview)');
});

getData('trends').then(t => {
  window.TRENDS = t;
  set('trends-sub', t.usable
    ? `基于全库结构化数据聚合 · 覆盖 ${t.months_covered} 个月`
    : `发文量与风向由 <b>${t.months_covered}</b> 个月的真实数据算出,不足 `
      + `${t.min_months_required} 个月,下方四图暂用演示数据`);
  // 真实数据可能比首次进入趋势页更晚到达 —— initCharts 可重复调用
  if (typeof initCharts === 'function' && document.querySelector('#c-stack canvas')) initCharts();
}).catch(err => console.warn('[trends] 未加载,图表用演示数据:', err.message));

getData('lineage').then(renderLineage)
  .catch(err => console.warn('[lineage] 未加载,脉络页保留静态内容:', err.message));
