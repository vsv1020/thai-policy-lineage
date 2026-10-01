/* 政策详情页(「找政策」的检索在 js/search.js)。
   详情页原来永远显示同一份写死的文件;现在按 uid 从 /api/documents/{uid} 取,
   降级时从 overview 已有的列表数据拼一个简版(静态站没有单件接口)。 */

const { esc: E, set: put, API_BASE, ready } = window.PolicyData;

const REL_LABEL = {
  supersedes: '替代', superseded_by: '被替代', amends: '修订', amended_by: '被修订',
  implements: '落实', implemented_by: '被落实', repeals: '废止', repealed_by: '被废止',
  related: '相关',
};
const CONF_LABEL = { high: '官方原文核对', med: '官方引述/二手一致', low: '单一二手来源', none: '未取得' };

/* 供 data.js 的卡片与检索行调用 */
window.openDetail = async function (uid) {
  go('detail');
  window.PolicyTrack && PolicyTrack.page(location.pathname.replace(/index\.html$/, '') + '#detail/' + uid);
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

  /* 溯源块:前台只收录有官方原文的文件(入库规则保证),这里列出原文链接与公报卷期 */
  const official = (d.sources || []).filter(s => s.role === 'official' && s.url);
  const srcs = official.length ? official : (d.source_url ? [{ url: d.source_url }] : []);
  const origin = `<b>泰文原文(官方)</b> · ${d.doc_no ? `${E(d.doc_no_label || '文号')} ${E(d.doc_no)} · ` : ''}`
    + srcs.map(s => `<a href="${E(s.url)}" target="_blank" rel="noopener">${E(s.url)} ↗</a>`).join(' · ');

  const confNote = `字段可信度:日期 <b>${E(CONF_LABEL[conf.dates] || conf.dates || '未标注')}</b>`
    + (conf.doc_no ? ` · 文号 <b>${E(CONF_LABEL[conf.doc_no] || conf.doc_no)}</b>` : '');

  put('detail-crumb', `<a href="#search">找政策</a> / ${E(d.domain_label)} / ${E(d.legal_form)}`);
  put('detail-body', `
    <div class="pc-top">
      <span class="chip ${E(d.domain)}">${E(d.domain_label)}</span>
      <span class="chip bare">${E(d.legal_form)}</span>
      <span class="dir ${E(d.direction)}">${E({ tight: '▲ 收紧', loose: '▼ 放宽', neutral: '● 中性' }[d.direction] || '')}</span>
      ${d.verified ? '<span class="verified">已人工复核</span>' : ''}
    </div>
    <div class="d-title">${E(d.title_zh)}</div>
    ${d.title_th ? `<div class="d-thai">泰文原题:${E(d.title_th)}</div>` : ''}
    <div class="fields">${fields}</div>
    <div class="d-body">
      <h4>中文摘要</h4>
      <p>${E(d.summary_zh)}</p>
      ${(d.key_points || []).length ? `<h4>正文要点</h4><ul class="points">${d.key_points.map(k => `<li>${E(k)}</li>`).join('')}</ul>` : ''}
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
  put('detail-share', `<a href="p/${E(d.uid.toLowerCase())}.html" target="_blank" rel="noopener">`
    + `打开可分享的独立页面 ↗</a> <span style="color:var(--muted)">(无需 JS,可被搜索引擎收录)</span>`);
  put('detail-issue', d.issue_id
    ? `<a href="#" onclick="go('lineage');return false">查看「${E(d.issue_id)}」完整演进脉络 →</a>`
    : '<span style="color:var(--muted)">该文件尚未归入议题</span>');
}
