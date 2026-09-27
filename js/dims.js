/* 政策维度页:七个维度全部由 /api/dimensions(或 data/site/dimensions.json)渲染。
   每个维度下标注样本量(真实计数),由读者自行判断分量 —— 见 note()。 */

const { getData: getDim, esc: e, set: setEl, insufficientNote: note } = window.PolicyData;

const CLASS_RGB = { blue: '91,115,145', seal: '176,51,42', gold: '183,138,60' };
const CLASS_VAR = { blue: 'var(--blue)', seal: 'var(--seal)', gold: 'var(--gold-deep)' };

function cell(v, max, rgb, red) {
  const frame = red ? ' red-frame' : '';
  if (!v) return `<td class="cell${frame}" style="background:rgba(${rgb},0.06);color:var(--muted)">·</td>`;
  const a = 0.10 + 0.80 * (v / (max || 1));
  return `<td class="cell${frame}" style="background:rgba(${rgb},${a.toFixed(2)});color:${a > 0.55 ? '#fff' : 'var(--ink)'}">${v}</td>`;
}

/* 维度一:工具结构随时间演变 */
function dim1(d) {
  if (!d.groups || !d.groups.length) return;
  const head = `<table class="matrix"><tr><th style="width:158px"></th>${
    d.years_be.map(y => `<th>${e(y)}</th>`).join('')}</tr></table>`;
  const body = d.groups.map(g => {
    const rgb = CLASS_RGB[g.color] || CLASS_RGB.blue;
    const max = Math.max(1, ...g.rows.flatMap(r => r.data));
    return `<div class="grp"><span class="sq" style="background:${CLASS_VAR[g.color] || 'var(--blue)'}"></span>
        <b>${e(g.zh)} · ${e(g.desc)}</b><span>占 ${e(g.share)}% · ${e(g.count)} 次</span></div>
      <table class="matrix">${g.rows.map(r =>
        `<tr><td class="rowname">${e(r.label)}</td>${r.data.map(v => cell(v, max, rgb)).join('')}</tr>`
      ).join('')}</table>`;
  }).join('');
  const shares = d.groups.map(g => `${g.zh} ${g.share}%`).join(' · ');
  setEl('dim1', head + body + note(d, '工具标注')
    + `<div class="reading">读法:格子深浅 = 该年该工具被使用的次数。当前结构 ${e(shares)}。
       环境型占比高说明政策更多靠「规则与激励」而非直接投入 ——
       对企业的含义是合规门槛的变化比补贴变化更值得盯。</div>`);
}

/* 维度二:工具 × 目标,空白格 = 政策空白 */
function dim2(d) {
  if (!d.goals || !d.goals.length) return;
  const gapKeys = new Set(d.gaps.map(g => `${g.class}||${g.goal}`));
  let h = `<tr><th style="width:76px"></th>${d.goals.map(g => `<th>${e(g.label)}</th>`).join('')}</tr>`;
  h += d.matrix.map(row => {
    const rgb = CLASS_RGB[row.color] || CLASS_RGB.blue;
    const max = Math.max(1, ...row.data);
    return `<tr><td class="rowname" style="width:76px">${e(row.label)}</td>${
      row.data.map((v, i) => cell(v, max, rgb,
        gapKeys.has(`${row.label}||${d.goals[i].label}`))).join('')}</tr>`;
  }).join('');
  setEl('dim2', `<table class="matrix">${h}</table>` + note(d, '工具×目标')
    + (d.gaps.length
      ? `<div class="reading">红框 ${e(d.gaps.length)} 处 = 该目标下没有对应类别的工具,
         是政策空白,也是提意见和抢先布局的位置:${
           e(d.gaps.slice(0, 4).map(g => `${g.goal}↔${g.class}`).join('、'))}${
           d.gaps.length > 4 ? ' 等' : ''}。</div>`
      : '<div class="reading">当前样本里每个目标都有对应工具,未检出政策空白。</div>'));
}

/* 维度三:法律形式与强制力金字塔 */
function dim3(d) {
  const shown = d.forms.filter(f => f.count > 0);
  if (!shown.length) return;
  const bg = s => s >= 5 ? 'var(--ink)' : (s === 4 ? 'var(--seal)'
    : (s === 3 ? 'var(--blue)' : (s === 2 ? '#2f3338' : '#cfc9ba')));
  const fg = s => s <= 1 ? ';color:var(--ink)' : '';
  setEl('dim3', shown.map(f =>
    `<div class="pyr-row">
      <div class="pyr-num" style="background:${bg(f.stability)}${fg(f.stability)}">${e(f.stability)}</div>
      <div><div class="pyr-name">${e(f.th || f.abbr)}</div>
        <div class="pyr-desc">${e(f.zh)} · ${e(f.note)}${f.justiciable ? ' · 可诉' : ' · 可诉性弱'}</div></div>
      <div><div class="pyr-count">${e(f.count)}</div><div class="pyr-pct">${e(f.pct)}%</div></div>
    </div>`).join('')
    + note(d, '文件')
    + `<div class="reading" style="margin-top:14px"><b>${e(d.fragile_pct)}%</b> 的政策承载在
       稳定性 ≤2 的公告与决议层上 —— ${e(d.fragile_note)}。</div>`);
}

/* 维度四:谁被支持、谁被约束 */
function dim4(d) {
  if (!d.items || !d.items.length) return;
  const max = Math.max(1, d.max);
  setEl('dim4', d.items.map(i =>
    `<div class="bi-row"><div class="bi-head"><span class="n">${e(i.label)}</span>
      <span class="v">支持 ${e(i.support)} / 约束 ${e(i.constrain)}</span></div>
      <div class="bi-track">
        <div class="bi-l"><i style="width:${(i.support / max * 100).toFixed(0)}%"></i></div>
        <div class="bi-r"><i style="width:${(i.constrain / max * 100).toFixed(0)}%"></i></div>
      </div></div>`).join('') + note(d, '作用对象标注'));
}

/* 维度五:机构协同 */
function dim5(d) {
  const max = Math.max(1, d.max);
  const body = (d.pairs || []).length
    ? d.pairs.map(p => {
        const w = (p.n / max * 100).toFixed(0);
        const color = p.n >= max * 0.6 ? 'var(--seal)' : (p.n >= max * 0.3 ? 'var(--blue)' : 'var(--gold)');
        return `<div class="co-row"><span>${e(p.a)} ↔ ${e(p.b)}</span>
          <div class="co-bar"><i style="width:${w}%;background:${color}"></i></div>
          <span class="co-val">${e(p.n)}</span></div>`;
      }).join('')
    : '<div class="reading">当前样本里没有联署文件 —— 所有文件都由单一机关发出。</div>';
  setEl('dim5', body + note(d, '联署')
    + `<div class="reading" style="margin-top:14px">单一机关发文 <b>${e(d.solo_documents)}</b> 份,
       联署 <b>${e((d.pairs || []).length)}</b> 组。${e(d.note)}。</div>`);
}

/* 维度六:一致性与冲突检测 */
function dim6(d) {
  const items = d.items || [];
  if (!items.length) {
    setEl('dim6', '<div class="reading">当前未检出口径冲突。冲突由规则(如「已决议未刊公报」)'
      + '与人工标注共同产生,样本增大后会自动增多。</div>');
    return;
  }
  const badge = { high: '高危', med: '中', low: '低' };
  setEl('dim6', items.map((c, i) =>
    `<div class="conflict${c.severity === 'high' ? ' high' : ''}"${
      i === items.length - 1 ? ' style="margin-bottom:0"' : ''}>
      <div class="cf-top"><span class="cf-badge">${e(badge[c.severity] || c.severity)}</span>
        <span class="cf-title">${e(c.title_zh)}</span></div>
      <div class="cf-cols">${c.sides.map(s =>
        `<div class="cf-quote">${e(s.quote_zh)}</div>`).join('')}</div>
      <div class="cf-impact">影响:${e(c.impact_zh)}
        <span style="color:var(--muted)"> · 来源:${e(c.detected_by)}</span></div>
    </div>`).join(''));
}

/* 维度七:执行完整度 */
function dim7(d) {
  const stages = d.stages || [];
  if (!stages.length) return;
  const peak = Math.max(1, d.peak);
  setEl('dim7', `<div class="stage-wrap">${stages.map(x => {
    const h = Math.max(4, Math.round(x.count / peak * 160));
    const cls = x.hot ? ' hot' : (x.weak ? ' weak' : '');
    const bg = x.hot || x.weak ? '' : `;background:${x.count >= peak * 0.4 ? '#5b7391' : '#8296ac'}`;
    return `<div class="stage${cls}"><div class="num">${e(x.count)}</div>
      <div class="bar" style="height:${h}px${bg}"></div><div class="lab">${e(x.label)}</div></div>`;
  }).join('')}</div>` + note(d, '环节标注')
    + (d.missing && d.missing.length
      ? `<div class="warn-box">缺环预警:<b>${e(d.missing.join('、'))}</b> 环节
         <b>为 0 件</b> —— 意味着这条链在这里断了。缺「评估与复盘」意味着政策效果没有官方评估基础,
         未来调整更可能是政治周期驱动而非数据驱动;缺「国家规划」意味着上游缺少纲领性依据,
         方向更易反复。这对投资时间表是实质风险。</div>`
      : `<div class="warn-box">六个环节均有文件,链条完整;峰值在「${
         e((stages.find(x => x.hot) || {}).label || '')}」环节。</div>`));
}

getDim('dimensions').then(d => {
  dim1(d.dim1_instruments); dim2(d.dim2_instrument_goal); dim3(d.dim3_legal_forms);
  dim4(d.dim4_parties); dim5(d.dim5_cooperation); dim6(d.dim6_conflicts);
  dim7(d.dim7_implementation);
  setEl('dims-sub', `切片:<b>${e(d.scope)}</b>。发文量回答「多不多」,这一页回答「是什么样的政策」。`
    + ` 每个维度都标注样本量,不足时只出计数、不出结论。`);
}).catch(err => console.warn('[dimensions] 未加载,维度页保留静态内容:', err.message));
