const C = { ink:'#171a1c', ink2:'#55524b', muted:'#8b877c', line:'#dbd6c9', card:'#faf9f5',
  seal:'#b0332a', gold:'#c9973f', blue:'#5b7391', green:'#4f7a4f', gray:'#b9b3a4' };
/* 由 js/data.js 从 data/site/trends.json 注入。四张图全部来自真实数据,没有演示数组 */
window.TRENDS = null;
const DOMAIN_COLOR = { visa:C.blue, tax:C.seal, biz:C.green, labor:C.gold, land:'#8c3b2f',
  customs:'#7a6a52', finance:'#4a6b78', digital:'#6b5b8c', education:'#7d8a5c', health:'#8a6a6a' };
let inited = false;

function go(v) {
  document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
  document.getElementById('v-' + v).classList.add('active');
  document.querySelectorAll('.nav-item[data-v]').forEach(b => b.classList.toggle('active', b.dataset.v === v));
  window.scrollTo(0, 0);
  // 单页切换记一次虚拟浏览;详情页由 openDetail 带着 uid 自己记
  if (v !== 'detail') window.PolicyTrack && PolicyTrack.page(location.pathname.replace(/index\.html$/, '') + '#' + v);
  if (v === 'trends' && !inited) { inited = true; setTimeout(initCharts, 30); }
}
document.querySelectorAll('.nav-item[data-v]').forEach(b => b.addEventListener('click', () => go(b.dataset.v)));

/* 维度页的矩阵/双向条渲染已移到 js/dims.js —— 那里的数据来自真实聚合,
   不再是这里写死的 EV 演示数组。 */

const ax = {
  axisLabel: { color: C.muted, fontSize: 11 },
  axisLine: { lineStyle: { color: C.line } },
  axisTick: { show: false },
  splitLine: { lineStyle: { color: '#e6e2d7' } }
};
const tip = { backgroundColor: C.card, borderColor: C.line, textStyle: { color: C.ink, fontSize: 12 } };

function initCharts() {
  const T = window.TRENDS;
  if (!T) return;                  // 数据未到时不画;data.js 取到 trends 后会再调用一次
  const charts = [];
  const XM = T.months;
  /* 允许重复调用:真实数据到达得比首次渲染晚时,data.js 会再调一次 */
  const mount = id => {
    const dom = document.getElementById(id);
    echarts.dispose(dom);
    return echarts.init(dom);
  };
  const empty = (id, msg) => { const el = document.getElementById(id);
    echarts.dispose(el); el.innerHTML = `<div class="mod-sub" style="padding:40px 0;text-align:center">${msg}</div>`; };

  if (T.volume_by_domain.length) {
    const stack = mount('c-stack');
    const mk = (name, color, data) => ({
      name, type: 'line', stack: 't', smooth: 0.3, symbol: 'none',
      lineStyle: { width: 2, color: C.card },
      areaStyle: { color, opacity: 0.95 },
      emphasis: { focus: 'series' },
      endLabel: { show: true, formatter: '{a}', fontSize: 11, color: C.ink2, distance: 6 },
      labelLayout: { moveOverlap: 'shiftY' }, data
    });
    stack.setOption({
      grid: { left: 40, right: 80, top: 34, bottom: 28 },
      legend: { top: 0, left: 0, icon: 'rect', itemWidth: 9, itemHeight: 9, textStyle: { color: C.ink2, fontSize: 11.5 } },
      tooltip: { ...tip, trigger: 'axis' },
      xAxis: { type: 'category', boundaryGap: false, data: XM, ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', name: '件', minInterval: 1, nameTextStyle: { color: C.muted }, ...ax },
      series: T.volume_by_domain.map(s => mk(s.label, DOMAIN_COLOR[s.id] || C.gray, s.data))
    });
    charts.push(stack);
  } else empty('c-stack', '暂无发文数据');

  const mkL = (name, color, data) => ({
    name, type: 'line', smooth: 0.35, symbol: 'circle', symbolSize: 5, showSymbol: false, connectNulls: true,
    lineStyle: { width: 2, color }, itemStyle: { color },
    endLabel: { show: true, formatter: '{a}', fontSize: 11, color: C.ink2, distance: 6 },
    labelLayout: { moveOverlap: 'shiftY' }, emphasis: { focus: 'series' }, data
  });
  if (T.wind_by_domain.length) {
    const dir = mount('c-direction');
    dir.setOption({
      grid: { left: 74, right: 80, top: 34, bottom: 28 },
      legend: { top: 0, left: 0, icon: 'rect', itemWidth: 9, itemHeight: 9, textStyle: { color: C.ink2, fontSize: 11.5 } },
      tooltip: { ...tip, trigger: 'axis' },
      xAxis: { type: 'category', boundaryGap: false, data: XM, ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', min: -1, max: 1, interval: 0.5, ...ax,
        axisLabel: { ...ax.axisLabel, formatter: v => v > 0 ? '+' + v + ' 放宽' : (v < 0 ? v + ' 收紧' : '0 中性') } },
      series: T.wind_by_domain.map(s => mkL(s.label, DOMAIN_COLOR[s.id] || C.gray, s.data))
        .map((s, i) => i ? s : { ...s, markLine: { silent: true, symbol: 'none',
          lineStyle: { color: C.muted, type: 'solid', width: 1.2 }, label: { show: false },
          data: [{ yAxis: 0 }] } })
    });
    charts.push(dir);
  } else empty('c-direction', '暂无带方向标注的政策');

  /* 机关太多时只画发文最多的 10 个,热力图才看得清 */
  const orgs = T.activity_by_agency.slice()
    .sort((a, b) => b.data.reduce((x, y) => x + y, 0) - a.data.reduce((x, y) => x + y, 0)).slice(0, 10);
  if (orgs.length) {
    const heat = mount('c-heat');
    const ORGS = orgs.map(s => s.label);
    const hd = []; orgs.forEach((row, y) => row.data.forEach((v, x) => hd.push([x, y, v])));
    const hmax = Math.max(1, ...hd.map(p => p[2]));
    heat.setOption({
      grid: { left: 96, right: 14, top: 10, bottom: 54 },
      tooltip: { ...tip, formatter: p => `${ORGS[p.value[1]]} · ${XM[p.value[0]]}<br>发文 <b>${p.value[2]}</b> 件` },
      xAxis: { type: 'category', data: XM, ...ax, splitLine: { show: false }, axisLine: { show: false } },
      yAxis: { type: 'category', data: ORGS, ...ax, splitLine: { show: false }, axisLine: { show: false } },
      visualMap: { min: 0, max: hmax, orient: 'horizontal', left: 'center', bottom: 0,
        itemHeight: 90, itemWidth: 10, textStyle: { color: C.muted, fontSize: 10.5 },
        inRange: { color: ['#e3e0d5', '#b9c2cd', '#8296ac', '#5b7391', '#3f556f'] } },
      series: [{ type: 'heatmap', data: hd,
        itemStyle: { borderColor: C.card, borderWidth: 2 },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(23,26,28,.3)' } } }]
    });
    charts.push(heat);
  } else empty('c-heat', '暂无机关发文数据');

  /* 上升话题:领域 / 政策工具 / 政策目标标签,近 90 天 vs 前 90 天被提及的文件数 */
  const R = T.rising || [];
  if (R.length) {
    const topics = mount('c-topics');
    const val = r => r.growth_pct == null ? 100 : Math.min(r.growth_pct, 300);
    topics.setOption({
      grid: { left: 110, right: 90, top: 10, bottom: 26 },
      tooltip: { ...tip, formatter: p => { const r = R[p.dataIndex];
        return `${r.label}<br>近 90 天 <b>${r.current}</b> 份 · 前 90 天 ${r.previous} 份`; } },
      xAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: '{value}%' } },
      yAxis: { type: 'category', inverse: true, data: R.map(r => r.label),
        ...ax, splitLine: { show: false }, axisLine: { show: false },
        axisLabel: { color: C.ink2, fontSize: 12 } },
      series: [{ type: 'bar', barWidth: 13, itemStyle: { color: C.seal },
        label: { show: true, position: 'right', color: C.ink2, fontSize: 11.5,
          formatter: p => { const r = R[p.dataIndex];
            return r.growth_pct == null ? `新出现 · ${r.current} 份` : `+${r.growth_pct}%`; } },
        data: R.map(val) }]
    });
    charts.push(topics);
  } else empty('c-topics', '近 90 天没有明显上升的话题');

  window.addEventListener('resize', () => charts.forEach(c => c.resize()));
}
