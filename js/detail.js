/* 政策详情页 + 检索页分面。
   详情页原来永远显示同一份写死的文件;现在按 uid 从 /api/documents/{uid} 取,
   降级时从 overview 已有的列表数据拼一个简版(静态站没有单件接口)。 */

const { esc: E, set: put, API_BASE, ready } = window.PolicyData;

const FORM_LABEL = {};      // legal_form_id → 中文,由 /api/vocab 填充(仅 API 模式)
const REL_LABEL = {
  supersedes: '替代', superseded_by: '被替代', amends: '修订', amended_by: '被修订',
  implements: '落实', implemented_by: '被落实', repeals: '废止', repealed_by: '被废止',
  related: '相关',
};
const CONF_LABEL = { high: '官方原文核对', med: '官方引述/二手一致', low: '单一二手来源', none: '未取得' };

/* 供 data.js 的卡片与检索行调用 */
window.openDetail = async function (uid) {
  go('detail');
  await ready();
  put('detail-body', '<div class="d-body"><p>加载中……</p></div>');
  let d = null;
  if (window.DATA_MODE === 'api') {
    try {
      const r = await fetch(`${API_BASE}/api/documents/${encodeURIComponent(uid)}`,
        { cache: 'no-store' });
      if (r.ok) d = await r.json();
    } catch (err) { console.warn('[detail] API 失败,退回列表数据:', err.message); }
  }
  if (!d) d = (window.POLICIES || []).find(p => p.uid === uid) || null;
  if (!d) {
    put('detail-body', '<div class="d-body"><p>未找到这份文件。静态快照模式下只能查看'
      + '列表里已有的条目。</p></div>');
    return;
  }
  renderDetail(d);
};

function dateRow(k, v, note) {
  if (!v) return '';
  return `<div class="field"><div class="k">${E(k)}</div><div class="v">${E(v)}${
    note ? ` <span style="color:var(--muted);font-size:11.5px">${E(note)}</span>` : ''}</div></div>`;
}

function renderDetail(d) {
  const dates = d.dates || {};
  const conf = d.confidence || {};
  const fields = [
    `<div class="field"><div class="k">发文机关</div><div class="v">${E(d.org)}</div></div>`,
    d.doc_no ? `<div class="field"><div class="k">${E(d.doc_no_label || '文号')}</div>
      <div class="v">${E(d.doc_no)}</div></div>` : '',
    dateRow('内阁决议日', dates.resolved_at),
    dateRow('刊登公报日', dates.published_at),
    dateRow('生效日', dates.effective_from, dates.published_at
      && dates.effective_from < dates.published_at ? '追溯适用' : ''),
    dateRow('失效日', dates.effective_to),
    dateRow('意见截止', dates.comment_deadline),
    `<div class="field"><div class="k">法律层级</div><div class="v">${E(d.legal_form)}</div></div>`,
    `<div class="field"><div class="k">稳定性</div><div class="v">${E(d.stability)} / 5${
      d.stability <= 2 ? ' <span style="color:var(--seal)">易变</span>' : ''}</div></div>`,
    `<div class="field"><div class="k">政策方向</div><div class="v" style="color:${
      d.direction === 'tight' ? 'var(--seal)' : (d.direction === 'loose' ? 'var(--green)' : 'var(--muted)')
    }">${E({ tight: '收紧', loose: '放宽', neutral: '中性' }[d.direction] || d.direction)}</div></div>`,
  ].filter(Boolean).join('');

  const parties = (d.parties || []).length
    ? `<h4>作用对象</h4><ul>${d.parties.map(p =>
        `<li>${E(p.label || p.party_id)} —— ${E({ support: '支持', constrain: '约束', neutral: '中性' }[p.stance])}</li>`
      ).join('')}</ul>` : '';

  const rels = (d.relations || []).length
    ? `<h4>关联文件</h4><ul>${d.relations.map(r =>
        `<li>${E(REL_LABEL[r.type] || r.type)}:<a href="#" onclick="openDetail('${
          E(r.uid)}');return false">${E(r.uid)}</a></li>`).join('')}</ul>` : '';

  /* 溯源块:有官方链接出链,没有就说清楚没有 —— 不留白让人以为有 */
  const official = (d.sources || []).filter(s => s.role === 'official' && s.url);
  const origin = official.length
    ? `<b>泰文原文</b> · ${official.map(s =>
        `<a href="${E(s.url)}" target="_blank" rel="noopener">${E(s.url)} ↗</a>`).join(' · ')}`
    : `<b>泰文原文</b> · <span style="color:var(--seal)">尚未取得官方原文链接</span>
       —— 本条依二手来源整理,文号与日期可信度见下方标注;取得公报原件后回填。`;

  const confNote = `字段可信度:日期 <b>${E(CONF_LABEL[conf.dates] || conf.dates || '未标注')}</b>`
    + (conf.doc_no ? ` · 文号 <b>${E(CONF_LABEL[conf.doc_no] || conf.doc_no)}</b>` : '');

  put('detail-crumb', `检索 / ${E(d.domain_label)} / ${E(d.legal_form)}`);
  put('detail-body', `
    <div class="pc-top">
      <span class="chip ${E(d.domain)}">${E(d.domain_label)}</span>
      <span class="chip bare">${E(d.legal_form)}</span>
      <span class="dir ${E(d.direction)}">${E({ tight: '▲ 收紧', loose: '▼ 放宽', neutral: '● 中性' }[d.direction] || '')}</span>
      ${d.verified ? '<span class="verified">已人工复核</span>'
        : '<span class="chip bare" style="color:var(--muted)">未经人工复核</span>'}
    </div>
    <div class="d-title">${E(d.title_zh)}</div>
    ${d.title_th ? `<div class="d-thai">泰文原题:${E(d.title_th)}</div>` : ''}
    <div class="fields">${fields}</div>
    <div class="d-body">
      <h4>中文摘要</h4>
      <p>${E(d.summary_zh)}</p>
      ${d.note ? `<h4>数据说明</h4><p style="color:var(--ink-2)">${E(d.note)}</p>` : ''}
      ${parties}
      ${rels}
      <h4>稳定性提示(法律形式信号)</h4>
      <p>本文件为 <b>${E(d.legal_form)}</b>。${d.stability <= 2
        ? '公告与决议层调整最快、可诉性弱,重大安排建议按可调整口径做敏感性测算。'
        : '法律与法令层须经更长程序,稳定性较高。'}</p>
    </div>
    <div class="origin">${origin}<br>${confNote}</div>
    <div class="disclaim">免责声明:本页为非官方翻译,仅供参考,如与泰文原文有出入,以泰文原文为准;
      本内容不构成法律或税务意见。本站与泰国政府无隶属关系。</div>`);

  const tl = [
    dates.resolved_at && { d: dates.resolved_at, n: '内阁决议', s: 'done' },
    dates.comment_deadline && { d: dates.comment_deadline, n: '公开征求意见截止', s: 'done' },
    dates.published_at && { d: dates.published_at, n: '刊登皇家公报', s: 'done' },
    dates.effective_from && { d: dates.effective_from, n: '生效适用', s: 'now' },
    dates.effective_to && { d: dates.effective_to, n: '失效', s: '' },
  ].filter(Boolean).sort((a, b) => a.d.localeCompare(b.d));
  put('detail-timeline', tl.length
    ? tl.map(x => `<div class="tl-item ${x.s}"><div class="tl-date">${E(x.d)}</div>
        <div class="tl-name">${E(x.n)}</div></div>`).join('')
    : '<div class="mod-sub">该文件尚无可用日期</div>');
  put('detail-issue', d.issue_id
    ? `<a href="#" onclick="go('lineage');return false">查看「${E(d.issue_id)}」完整演进脉络 →</a>`
    : '<span style="color:var(--muted)">该文件尚未归入议题</span>');
}

/* ── 检索页分面:接 /api/documents 的过滤参数 ── */
const state = { q: '', domain: '', legal_form: '', status: '', direction: '', pending_gazette: false };

function facet(label, key, options, current) {
  const opts = [['', '全部']].concat(options);
  return `<div class="facet">${E(label)}:<select data-key="${E(key)}"
    style="border:0;background:transparent;font:inherit;color:var(--seal);cursor:pointer">
    ${opts.map(([v, t]) =>
      `<option value="${E(v)}"${v === current ? ' selected' : ''}>${E(t)}</option>`).join('')}
  </select></div>`;
}

async function buildFacets() {
  await ready();          // 必须等探测结束,否则 DATA_MODE 还是初始值
  if (window.DATA_MODE !== 'api') {
    put('facets', '<div class="facet" style="color:var(--muted)">静态快照模式:分面检索需要后端接口'
      + '(部署后端后此处变为可用下拉)</div>');
    return;
  }
  let v;
  try {
    v = await (await fetch(`${API_BASE}/api/vocab`, { cache: 'no-store' })).json();
  } catch (err) { console.warn('[facets] 词表加载失败:', err.message); return; }
  v.legal_forms.forEach(f => { FORM_LABEL[f.id] = f.zh; });

  const draw = () => {
    put('facets',
      `<div class="facet"><input id="fq" placeholder="关键词(中/泰文)" value="${E(state.q)}"
         style="border:0;background:transparent;font:inherit;width:150px;outline:none"></div>`
      + facet('领域', 'domain', v.domains.map(d => [d.id, d.zh]), state.domain)
      + facet('法律形式', 'legal_form',
          v.legal_forms.map(f => [f.id, `${f.zh}(稳定性 ${f.stability})`]), state.legal_form)
      + facet('状态', 'status', v.statuses.map(s => [s.id, s.zh]), state.status)
      + facet('方向', 'direction',
          [['tight', '收紧'], ['loose', '放宽'], ['neutral', '中性']], state.direction)
      + `<div class="facet" style="cursor:pointer;${state.pending_gazette
          ? 'border-color:var(--seal);color:var(--seal)' : ''}" id="fpg">
         ${state.pending_gazette ? '✓ ' : '+ '}只看待刊公报窗口期</div>`);
    document.querySelectorAll('#facets select').forEach(el =>
      el.addEventListener('change', () => { state[el.dataset.key] = el.value; run(); }));
    const q = document.getElementById('fq');
    if (q) {
      let t;
      q.addEventListener('input', () => {
        clearTimeout(t);
        t = setTimeout(() => { state.q = q.value.trim(); run(); }, 300);
      });
    }
    const pg = document.getElementById('fpg');
    if (pg) pg.addEventListener('click', () => {
      state.pending_gazette = !state.pending_gazette; draw(); run();
    });
  };

  const run = async () => {
    const p = new URLSearchParams();
    Object.entries(state).forEach(([k, val]) => {
      if (val === '' || val === false) return;
      p.set(k, val === true ? 'true' : val);
    });
    p.set('limit', '50');
    try {
      const r = await fetch(`${API_BASE}/api/documents?${p}`, { cache: 'no-store' });
      const d = await r.json();
      window.renderLib(d.items);
      put('lib-count', `领域 × 法律形式 × 状态 × 方向 × 关键词 分面检索 · 命中 <b>${d.total}</b> 条`
        + (d.total > d.items.length ? `(显示前 ${d.items.length} 条)` : ''));
      if (!d.items.length) {
        put('lib', '<div class="lib-row"><div style="color:var(--muted)">没有命中的条目。'
          + '试着放宽某个分面。</div></div>');
      }
    } catch (err) { console.warn('[facets] 检索失败:', err.message); }
  };

  draw();
}

buildFacets();
