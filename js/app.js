const MONTHS = ['25-08','25-09','25-10','25-11','25-12','26-01','26-02','26-03','26-04','26-05','26-06','26-07'];
const C = { ink:'#171a1c', ink2:'#55524b', muted:'#8b877c', line:'#dbd6c9', card:'#faf9f5',
  seal:'#b0332a', gold:'#c9973f', blue:'#5b7391', green:'#4f7a4f', gray:'#b9b3a4' };
/* 由 js/data.js 从 data/site/trends.json 注入。usable=false(数据月份不足)时
   下面的图继续用演示数组 —— 三四个点画不出趋势,只会误导。 */
window.TRENDS = null;
const DOMAIN_COLOR = { visa:C.blue, tax:C.seal, biz:C.green, labor:C.gold, land:'#8c3b2f',
  customs:'#7a6a52', finance:'#4a6b78', digital:'#6b5b8c', education:'#7d8a5c', health:'#8a6a6a' };
let inited = false;

function go(v) {
  document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
  document.getElementById('v-' + v).classList.add('active');
  document.querySelectorAll('.nav-item[data-v]').forEach(b => b.classList.toggle('active', b.dataset.v === v));
  window.scrollTo(0, 0);
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
  const charts = [];
  const T = window.TRENDS && window.TRENDS.usable ? window.TRENDS : null;
  const XM = T ? T.months : MONTHS;
  /* 允许重复调用:真实数据到达得比首次渲染晚时,data.js 会再调一次 */
  const mount = id => {
    const dom = document.getElementById(id);
    echarts.dispose(dom);
    return echarts.init(dom);
  };

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
    color: [C.blue, C.seal, C.green, C.gold, C.gray],
    grid: { left: 40, right: 80, top: 34, bottom: 28 },
    legend: { top: 0, left: 0, icon: 'rect', itemWidth: 9, itemHeight: 9, textStyle: { color: C.ink2, fontSize: 11.5 } },
    tooltip: { ...tip, trigger: 'axis' },
    xAxis: { type: 'category', boundaryGap: false, data: XM, ...ax, splitLine: { show: false } },
    yAxis: { type: 'value', name: '件', nameTextStyle: { color: C.muted }, ...ax },
    series: T
      ? T.volume_by_domain.map(s => mk(s.label, DOMAIN_COLOR[s.id] || C.gray, s.data))
      : [
        mk('签证居留', C.blue,  [12,9,11,15,13,18,14,12,16,13,15,17]),
        mk('税务',     C.seal,  [6,7,5,9,12,15,10,8,9,11,13,14]),
        mk('公司投资', C.green, [10,12,14,11,13,12,16,18,15,17,19,21]),
        mk('劳工用工', C.gold,  [5,4,6,8,5,7,6,9,7,8,12,10]),
        mk('其他',     C.gray,  [14,16,13,17,15,19,16,14,18,16,17,18])
      ]
  });
  charts.push(stack);

  const dir = mount('c-direction');
  const mkL = (name, color, data) => ({
    name, type: 'line', smooth: 0.35, symbol: 'circle', symbolSize: 5, showSymbol: false,
    lineStyle: { width: 2, color }, itemStyle: { color },
    endLabel: { show: true, formatter: '{a}', fontSize: 11, color: C.ink2, distance: 6 },
    labelLayout: { moveOverlap: 'shiftY' }, emphasis: { focus: 'series' }, data
  });
  dir.setOption({
    grid: { left: 74, right: 80, top: 34, bottom: 28 },
    legend: { top: 0, left: 0, icon: 'rect', itemWidth: 9, itemHeight: 9, textStyle: { color: C.ink2, fontSize: 11.5 } },
    tooltip: { ...tip, trigger: 'axis' },
    xAxis: { type: 'category', boundaryGap: false, data: XM, ...ax, splitLine: { show: false } },
    yAxis: { type: 'value', min: -1, max: 1, interval: 0.5, ...ax,
      axisLabel: { ...ax.axisLabel, formatter: v => v > 0 ? '+' + v + ' 放宽' : (v < 0 ? v + ' 收紧' : '0 中性') } },
    series: (T
      ? T.wind_by_domain.map(s => mkL(s.label, DOMAIN_COLOR[s.id] || C.gray, s.data))
      : [
        mkL('签证居留', C.blue, [0.2,0.1,-0.1,-0.3,-0.2,0.1,0.2,0.4,0.3,0.2,0.3,0.3]),
        mkL('房产土地', C.seal, [0.1,0,-0.1,-0.2,-0.3,-0.2,-0.4,-0.3,-0.5,-0.4,-0.5,-0.4])
      ]
    ).map((s, i) => i ? s : { ...s, markLine: { silent: true, symbol: 'none',
        lineStyle: { color: C.muted, type: 'solid', width: 1.2 }, label: { show: false },
        data: [{ yAxis: 0 }] } })
  });
  charts.push(dir);

  const heat = mount('c-heat');
  const ORGS = T ? T.activity_by_agency.map(s => s.label)
                 : ['移民局','税务厅','BOI','劳工部','土地厅','DBD'];
  const base = T ? T.activity_by_agency.map(s => s.data)
    : [[3,2,4,5,4,6,4,3,5,4,5,6],[2,3,2,4,5,6,4,3,3,4,5,5],[4,4,5,3,4,4,6,7,5,6,7,8],[2,1,2,3,2,3,2,4,3,3,5,4],[1,1,2,2,3,2,3,3,4,4,5,4],[3,4,4,3,4,3,5,6,4,5,6,7]];
  const hd = []; base.forEach((row, y) => row.forEach((v, x) => hd.push([x, y, v])));
  const hmax = Math.max(8, ...hd.map(p => p[2]));
  heat.setOption({
    grid: { left: 56, right: 14, top: 10, bottom: 54 },
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

  /* 上升话题榜暂无数据来源(需要关键词提取 + 环比),一直是演示数据 */
  const topics = mount('c-topics');
  topics.setOption({
    grid: { left: 110, right: 66, top: 10, bottom: 26 },
    tooltip: { ...tip, formatter: p => `${p.name}<br>环比 <b>+${p.value}%</b>` },
    xAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: '{value}%' } },
    yAxis: { type: 'category', inverse: true,
      data: ['代持排查','境外所得课税','半导体激励','DTV 签证','最低工资'],
      ...ax, splitLine: { show: false }, axisLine: { show: false },
      axisLabel: { color: C.ink2, fontSize: 12 } },
    series: [{ type: 'bar', barWidth: 13,
      itemStyle: { color: C.seal },
      label: { show: true, position: 'right', formatter: '+{c}%', color: C.ink2, fontSize: 11.5 },
      data: [186,142,95,67,41] }]
  });
  charts.push(topics);

  window.addEventListener('resize', () => charts.forEach(c => c.resize()));
}
