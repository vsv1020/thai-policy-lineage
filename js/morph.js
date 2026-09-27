/* 形态分析页:政策形态画像。数据来自 /api/morphology(或 data/site/morphology.json),
   全部由库里聚合,解读文字也由后端按数据生成 —— 这里只负责画。首次进入该页时才加载与绘图。 */

(function () {
  const { getData, esc: E, set: put } = window.PolicyData;
  const C = { ink: '#171a1c', ink2: '#55524b', muted: '#8b877c', line: '#dbd6c9', card: '#faf9f5',
              seal: '#b0332a', gold: '#c9973f', blue: '#5b7391', blueDeep: '#3f556f', green: '#4f7a4f', gray: '#b9b3a4' };
  const TIER_COLOR = ['#3f556f', '#5b7391', '#8296ac', '#c9973f', '#d9c7a4'];   // 法律 → 决议/指引
  const ax = { axisLabel: { color: C.muted, fontSize: 11 }, axisLine: { lineStyle: { color: C.line } },
               axisTick: { show: false }, splitLine: { lineStyle: { color: '#e6e2d7' } } };
  const tip = { backgroundColor: C.card, borderColor: C.line, textStyle: { color: C.ink, fontSize: 12 } };
  let charts = [];

  const mount = id => { const el = document.getElementById(id); echarts.dispose(el); const c = echarts.init(el); charts.push(c); return c; };
  const empty = (id, msg) => { const el = document.getElementById(id); echarts.dispose(el);
    el.innerHTML = `<div class="mod-sub" style="padding:40px 0;text-align:center">${E(msg)}</div>`; };

  function kpis(k) {
    const card = (label, v, sub) => `<div class="k"><div class="k-l">${E(label)}</div><div class="k-v">${E(v)}</div><div class="k-s">${E(sub)}</div></div>`;
    put('morph-kpis',
      card('收录政策', k.total, '全库')
      + card('平均层级', k.avg_stability, '稳定性 1–5,越高越难改')
      + card('高层级占比', k.high_tier_pct + '%', '法律 / 皇家法令')
      + card('可诉占比', k.binding_pct + '%', '强制力较强')
      + card('现行有效', k.in_force_pct + '%', '已生效仍在执行')
      + card('收紧 / 放宽', `${k.tight} / ${k.loose}`, '按政策方向标注'));
  }

  function draw(m) {
    charts.forEach(c => c.dispose()); charts = [];
    put('morph-sub', `政策形态画像 · 基于库内 <b>${E(m.n)}</b> 条政策:法律层级 × 强制力 × 政策工具类型 × 生命周期状态`);
    kpis(m.kpis);
    put('morph-insights', (m.insights || []).map(t => `<p style="margin:4px 0">${E(t)}</p>`).join('') || '暂无足够数据生成解读');

    // 法律层级分布:横向条形,可诉的深色
    const forms = m.legal_forms.filter(f => f.n);
    if (forms.length) {
      mount('c-morph-forms').setOption({
        grid: { left: 90, right: 70, top: 6, bottom: 22 },
        tooltip: { ...tip, formatter: p => { const f = forms[p.dataIndex];
          return `${E(f.zh)} · 稳定性 ${f.stability}<br>${f.n} 条(${f.pct}%)· ${f.justiciable ? '可诉' : '可诉性弱'}`; } },
        xAxis: { type: 'value', minInterval: 1, ...ax },
        yAxis: { type: 'category', inverse: true, data: forms.map(f => `${f.zh} · ${f.stability}`), ...ax,
                 splitLine: { show: false }, axisLabel: { color: C.ink2, fontSize: 12 } },
        series: [{ type: 'bar', barWidth: 14,
          data: forms.map(f => ({ value: f.n, itemStyle: { color: f.justiciable ? C.blueDeep : '#b9c2cd' } })),
          label: { show: true, position: 'right', color: C.ink2, fontSize: 11.5,
                   formatter: p => `${forms[p.dataIndex].pct}%` } }]
      });
    } else empty('c-morph-forms', '暂无数据');

    // 政策工具类型:环形图 + 最常用工具
    const cls = m.instrument_classes.filter(c => c.n);
    if (cls.length) {
      mount('c-morph-class').setOption({
        tooltip: { ...tip, formatter: p => `${E(p.name)}<br>${p.value} 条政策使用(${cls[p.dataIndex].pct}%)` },
        legend: { bottom: 0, textStyle: { color: C.ink2, fontSize: 12 }, itemWidth: 10, itemHeight: 10 },
        series: [{ type: 'pie', radius: ['42%', '68%'], center: ['50%', '44%'],
          label: { formatter: '{b}\n{d}%', color: C.ink2, fontSize: 11.5 },
          data: cls.map((c, i) => ({ name: c.zh, value: c.n, itemStyle: { color: [C.blue, C.seal, C.gold][i % 3] } })) }]
      });
    } else empty('c-morph-class', '暂无政策工具标注');
    put('morph-instr', (m.top_instruments || []).length
      ? `<div class="mod-sub" style="margin-top:6px">最常用的政策工具:${m.top_instruments.map(t =>
          `${E(t.zh)}(${E(t.class)})×${E(t.n)}`).join(' · ')}</div>` : '');

    // 领域 × 法律形式:热力
    const mx = m.matrix;
    if (mx.rows.length && mx.cols.length) {
      const data = []; mx.cells.forEach((row, y) => row.forEach((v, x) => data.push([x, y, v])));
      mount('c-morph-matrix').setOption({
        grid: { left: 76, right: 12, top: 8, bottom: 56 },
        tooltip: { ...tip, formatter: p => `${E(mx.rows[p.value[1]].zh)} · ${E(mx.cols[p.value[0]].zh)}<br><b>${p.value[2]}</b> 条` },
        xAxis: { type: 'category', data: mx.cols.map(c => c.zh), ...ax, splitLine: { show: false }, axisLine: { show: false },
                 axisLabel: { ...ax.axisLabel, interval: 0, rotate: mx.cols.length > 5 ? 30 : 0 } },
        yAxis: { type: 'category', inverse: true, data: mx.rows.map(r => r.zh), ...ax, splitLine: { show: false }, axisLine: { show: false } },
        visualMap: { show: false, min: 0, max: Math.max(1, ...data.map(d => d[2])),
                     inRange: { color: ['#eeebe3', '#b9c2cd', '#5b7391', '#3f556f'] } },
        series: [{ type: 'heatmap', data, label: { show: true, color: C.ink, fontSize: 11, formatter: p => p.value[2] || '' },
                   itemStyle: { borderColor: C.card, borderWidth: 2 } }]
      });
    } else empty('c-morph-matrix', '暂无数据');

    // 生命周期状态
    const st = m.statuses.filter(x => x.n);
    if (st.length) {
      mount('c-morph-status').setOption({
        grid: { left: 90, right: 60, top: 6, bottom: 22 },
        tooltip: { ...tip, formatter: p => `${E(st[p.dataIndex].zh)}<br>${st[p.dataIndex].n} 条(${st[p.dataIndex].pct}%)` },
        xAxis: { type: 'value', minInterval: 1, ...ax },
        yAxis: { type: 'category', inverse: true, data: st.map(x => x.zh), ...ax, splitLine: { show: false },
                 axisLabel: { color: C.ink2, fontSize: 12 } },
        series: [{ type: 'bar', barWidth: 14, itemStyle: { color: C.green },
          label: { show: true, position: 'right', color: C.ink2, fontSize: 11.5, formatter: p => `${st[p.dataIndex].pct}%` },
          data: st.map(x => x.n) }]
      });
    } else empty('c-morph-status', '暂无数据');

    // 形态演变:按季度的层级构成(堆叠)+ 平均稳定性(折线)
    const ev = m.evolution || [];
    if (ev.some(e => e.n)) {
      const tiers = Object.keys(ev[0].tiers);
      mount('c-morph-evo').setOption({
        grid: { left: 40, right: 50, top: 34, bottom: 28 },
        legend: { top: 0, left: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: C.ink2, fontSize: 11.5 } },
        tooltip: { ...tip, trigger: 'axis' },
        xAxis: { type: 'category', data: ev.map(e => e.quarter), ...ax, splitLine: { show: false } },
        yAxis: [{ type: 'value', name: '件', minInterval: 1, nameTextStyle: { color: C.muted }, ...ax },
                { type: 'value', name: '平均稳定性', min: 1, max: 5, nameTextStyle: { color: C.muted }, ...ax, splitLine: { show: false } }],
        series: tiers.map((t, i) => ({ name: t, type: 'bar', stack: 'tier', barMaxWidth: 34,
                   itemStyle: { color: TIER_COLOR[i] }, data: ev.map(e => e.tiers[t]) }))
          .concat([{ name: '平均稳定性', type: 'line', yAxisIndex: 1, connectNulls: true, smooth: 0.3,
                     symbolSize: 6, lineStyle: { color: C.seal, width: 2 }, itemStyle: { color: C.seal },
                     data: ev.map(e => e.avg_stability) }])
      });
    } else empty('c-morph-evo', '暂无带日期的政策');

    // 各领域形态指纹
    const pr = m.domain_profiles || [];
    put('morph-profile', pr.length ? `<table class="morph-table"><thead><tr>
        <th>领域</th><th class="n">条数</th><th>平均层级</th><th class="n">可诉</th><th>主要形式</th>
        <th class="hide-sm">主要工具类型</th><th class="n hide-sm">收紧 / 放宽</th></tr></thead><tbody>${
      pr.map(p => `<tr><td>${E(p.zh)}</td><td class="n">${E(p.n)}</td>
        <td><span class="stab-bar" style="width:${Math.round(p.avg_stability / 5 * 60)}px"></span>${E(p.avg_stability)}</td>
        <td class="n">${E(p.binding_pct)}%</td><td>${E(p.dominant_form)} <span style="color:var(--muted)">${E(p.dominant_form_pct)}%</span></td>
        <td class="hide-sm">${E(p.dominant_class || '—')}</td><td class="n hide-sm">${E(p.tight)} / ${E(p.loose)}</td></tr>`).join('')
      }</tbody></table>` : '<div class="mod-sub">暂无数据</div>');
  }

  let data = null, loading = null;
  function show() {
    if (data) { draw(data); return; }
    loading = loading || getData('morphology')
      .then(m => { data = m; draw(m); })
      .catch(err => { put('morph-insights', '形态数据未能加载,请稍后刷新。'); console.warn('[morph]', err.message); });
  }
  // 首次进入形态分析页时才取数与绘图(隐藏状态下 echarts 量不到尺寸)
  document.querySelectorAll('.nav-item[data-v="morph"]').forEach(b => b.addEventListener('click', () => setTimeout(show, 30)));
  window.addEventListener('resize', () => charts.forEach(c => c.resize()));
  window.PolicyMorph = { show };
})();
