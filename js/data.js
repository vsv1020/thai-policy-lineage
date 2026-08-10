/* 数据层:从 data/site/policies.json 渲染政策流 / 检索列表 / 风向 / 生效日历。
   —— 页面里保留的静态 HTML 是兜底:fetch 失败(离线打开、文件缺失)时原样保留,不白屏。
   —— 该 JSON 由 .claude/skills/autoresearch 定时写入,前端只读。 */

const DATA_URL = 'data/site/policies.json';

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const DIR_LABEL = { tight: '▲ 收紧', loose: '▼ 放宽', neutral: '● 中性' };
const STATUS_CLASS = { active: 'st-active', soon: 'st-soon', draft: 'st-draft' };

/* 一律按曼谷时间显示 —— 泰国政策的生效时点以泰国当地时间为准,
   按访客本地时区渲染会让"今天刊登"看起来像昨天。 */
function fmtStamp(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  const s = d.toLocaleString('sv-SE', { timeZone: 'Asia/Bangkok', hour12: false });
  return s.slice(0, 16) + ' 曼谷时间';
}

/* 原文链接:有 source_url 出真链,否则不出链(不做假链接) */
function originLink(p) {
  if (!p.source_url) return '';
  return `<span><a href="${esc(p.source_url)}" target="_blank" rel="noopener"
    onclick="event.stopPropagation()">泰文原文 ↗</a></span>`;
}

function policyCard(p) {
  const clickable = p.detail_ready ? ` onclick="go('detail')" style="cursor:pointer"` : '';
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
  return `<div class="lib-row">
    <span class="lib-date">${esc(p.date)}</span>
    <div><div class="lib-title">${esc(p.title_zh)}</div><div class="lib-sub">${sub}</div></div>
    <span class="pill ${STATUS_CLASS[p.status] || 'st-draft'}">${esc(p.status_label)}</span>
  </div>`;
}

function windRow(w) {
  const sign = w.score > 0 ? '+' : '';
  return `<div class="gauge-row"><span class="chip ${esc(w.domain)} bare">${esc(w.label)}</span>
    <span class="dir ${esc(w.direction)}">${DIR_LABEL[w.direction] || ''} ${sign}${esc(w.score)}</span></div>`;
}

function calRow(c) {
  return `<div class="cal-item"><span class="cal-date">${esc(String(c.date).slice(5))}</span><span>${esc(c.text)}</span></div>`;
}

function set(id, html) {
  const el = document.getElementById(id);
  if (el && html) el.innerHTML = html;
}

function render(d) {
  const policies = (d.policies || []).slice()
    .sort((a, b) => String(b.date).localeCompare(String(a.date)));

  set('feed', policies.filter(p => p.featured).map(policyCard).join(''));
  set('lib', policies.map(libRow).join(''));
  set('wind', (d.wind || []).map(windRow).join(''));
  set('calendar', (d.calendar || []).map(calRow).join(''));

  const n = policies.length;
  set('lib-count', `领域 × 机关 × 法律形式 × 状态 × 时间 五维过滤 · 当前库内 <b>${n}</b> 条`);

  const srcs = d.sources || [];
  const ok = srcs.filter(s => s.status === 'ok').length;
  const research = policies.filter(p => p.provenance !== 'demo').length;
  const health = srcs.length
    ? (ok ? ` · 源 ${ok}/${srcs.length} 可用` : ` · ${srcs.length} 个源均未接通`)
    : '';
  set('stamp', `数据更新 ${fmtStamp(d.updated_at)}${health}`
    + (research ? ` · 实采 ${research} 条` : ' · 全部为示意数据'));
}

fetch(DATA_URL, { cache: 'no-store' })
  .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
  .then(render)
  .catch(err => {
    console.warn('[policies.json] 未加载,页面保留静态示意数据:', err.message);
    set('stamp', '静态示意数据(未加载 policies.json)');
  });
