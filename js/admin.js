/* 统计后台。数据来自 GET /api/admin/stats?days=N(需要 ADMIN_TOKEN)。
   令牌只放 sessionStorage:关标签页就没了,不会长期留在这台电脑上。 */

(function () {
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = n => (n == null ? '—' : Number(n).toLocaleString('zh-CN'));
  const C = { ink: '#171a1c', muted: '#8b877c', line: '#dbd6c9', card: '#faf9f5',
              seal: '#b0332a', blue: '#5b7391', green: '#4f7a4f', gold: '#c9973f' };
  const store = (k, v) => { try { v === undefined ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch (e) {} };
  const load = k => { try { return sessionStorage.getItem(k); } catch (e) { return null; } };

  let days = 30, charts = [];
  const apiBase = () => {
    const q = new URLSearchParams(location.search).get('api');
    return (q !== null ? q : load('adm_api') || '').replace(/\/$/, '');
  };

  async function fetchStats() {
    const r = await fetch(`${apiBase()}/api/admin/stats?days=${days}`, {
      headers: { Authorization: 'Bearer ' + (load('adm_token') || '') }, cache: 'no-store' });
    if (r.status === 401) throw Object.assign(new Error('令牌不对'), { auth: true });
    if (r.status === 404) throw Object.assign(new Error('后台未启用:服务器没有设置 ADMIN_TOKEN,或后端地址不对'), { auth: true });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  function bars(rows, opts = {}) {
    if (!rows || !rows.length) return `<div class="empty">${opts.empty || '暂无数据'}</div>`;
    const max = Math.max(...rows.map(r => r.n)) || 1;
    return rows.map(r => `<div class="bar-row"><div class="bar-lbl" title="${esc(r.title || r.label)}">
        <i style="width:${(r.n / max * 100).toFixed(1)}%"></i><span>${r.html || esc(r.label)}</span></div>
        <div class="bar-n">${fmt(r.n)}${r.sub != null ? `<small>${esc(r.sub)}</small>` : ''}</div></div>`).join('');
  }

  function table(head, rows, empty) {
    if (!rows.length) return `<div class="empty">${empty || '暂无数据'}</div>`;
    return `<table class="t"><thead><tr>${head.map(h => `<th class="${h.n ? 'n' : ''}">${h.t}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(r => `<tr>${r.map((c, i) => `<td class="${head[i].n ? 'n' : ''}">${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  }

  const KPI = [
    ['pv', '浏览量'], ['uv', '访客'], ['pages_per_visitor', '人均浏览'], ['detail_views', '政策阅读'],
    ['searches', '站内检索'], ['outbound', '外链点击'], ['tip_opens', '打赏弹窗打开'], ['ad_clicks', '广告点击'],
  ];

  function render(d) {
    const s = d.summary;
    $('live').innerHTML = `最近 30 分钟在线 <b>${fmt(d.realtime_visitors_30m)}</b>`;
    $('range-note').textContent = `${d.range.start} ~ ${d.range.end},对比上期 ${d.range.prev_start} ~ ${d.range.prev_end} · 生成于 ${d.generated_at.replace('T', ' ').slice(0, 16)}`;
    $('kpis').innerHTML = KPI.map(([k, label]) => {
      const x = s[k] || {}, c = x.change_pct;
      const chg = c == null ? '上期无数据' : `${c >= 0 ? '▲' : '▼'} ${Math.abs(c)}% 较上期`;
      return `<div class="adm-card kpi"><div class="k-label">${label}</div><div class="k-val">${fmt(x.value)}</div>
        <div class="k-chg ${c == null ? '' : c >= 0 ? 'up' : 'down'}">${chg}</div></div>`;
    }).join('');

    $('policies').innerHTML = bars(d.policies.map(p => ({
      n: p.n, sub: p.landing ? `落地页 ${p.landing}` : null, title: p.title,
      html: `<a href="p/${esc(p.uid.toLowerCase())}.html" target="_blank" rel="noopener">${esc(p.uid)}</a> ${esc(p.title || '(已下架)')}` })),
      { empty: '还没有人打开过政策详情' });
    $('pages').innerHTML = bars(d.pages.map(p => ({ n: p.n, sub: `访客 ${p.uv}`, label: p.key })));

    $('direct').textContent = `直接访问 / 未带来源:${fmt(d.direct_pv)} 次浏览`;
    $('referrers').innerHTML = bars(d.referrers.map(r => ({ n: r.n, sub: `访客 ${r.uv}`, label: r.key })),
      { empty: '暂无外部来源' });
    $('campaigns').innerHTML = d.campaigns.length ? '<div class="sub" style="margin-top:14px">推广活动(UTM)</div>'
      + table([{ t: '来源' }, { t: '媒介' }, { t: '活动' }, { t: '浏览', n: 1 }],
        d.campaigns.map(c => [esc(c.source), esc(c.medium), esc(c.campaign), fmt(c.n)])) : '';

    $('searches').innerHTML = bars(d.searches.map(q => ({
      n: q.n, sub: q.avg_hits == null ? null : `平均命中 ${q.avg_hits}`,
      html: esc(q.q) + (q.zero ? '<span class="tag seal">零结果</span>' : '') })),
      { empty: '暂无检索(检索需要后端 API 模式)' });
    $('zero').innerHTML = bars(d.zero_result_searches.map(q => ({ n: q.zero, label: q.q })),
      { empty: '没有零结果检索 👍' });
    $('outbound').innerHTML = bars(d.outbound.map(o => ({
      n: o.n, sub: `访客 ${o.uv}`, html: esc(o.key) + (o.official ? '<span class="tag ok">官方</span>' : '') })));

    $('ads').innerHTML = table(
      [{ t: '槽位' }, { t: '赞助方' }, { t: '曝光', n: 1 }, { t: '点击', n: 1 }, { t: '点击率', n: 1 }],
      d.ads.map(a => [esc(a.slot), esc(a.sponsor), fmt(a.views), fmt(a.clicks), a.ctr == null ? '—' : a.ctr + '%']),
      '暂无广告数据(config/ads.json 未启用或还没有曝光)');

    const t = d.tips;
    $('tips').innerHTML = `<div class="adm-grid g2" style="margin:0 0 12px;grid-template-columns:repeat(3,1fr)">
        <div><div class="k-label" style="font-size:12px;color:var(--ink-2)">弹窗打开</div><div class="k-val" style="font-family:var(--serif);font-size:22px;font-weight:700">${fmt(t.opens)}</div></div>
        <div><div style="font-size:12px;color:var(--ink-2)">打开的访客</div><div style="font-family:var(--serif);font-size:22px;font-weight:700">${fmt(t.open_visitors)}</div></div>
        <div><div style="font-size:12px;color:var(--ink-2)">访客打开率</div><div style="font-family:var(--serif);font-size:22px;font-weight:700">${t.open_rate_pct == null ? '—' : t.open_rate_pct + '%'}</div></div></div>`
      + '<div class="sub">入口</div>' + bars(t.by_entry.map(x => ({ n: x.n, label: ({ header: '顶栏按钮', inline: '正文后', api: '其他' })[x.key] || x.key })))
      + '<div class="sub" style="margin-top:10px">选择的金额</div>' + bars(t.amounts.map(x => ({ n: x.n, label: x.key === 'custom' ? '自定金额' : '฿' + x.key })))
      + (t.links.length ? '<div class="sub" style="margin-top:10px">外部渠道点击</div>' + bars(t.links.map(x => ({ n: x.n, label: x.key }))) : '');

    const DEV = { mobile: '手机', desktop: '电脑', tablet: '平板' };
    $('devices').innerHTML = bars(d.devices.map(x => ({ n: x.n, label: DEV[x.key] || x.key })));
    $('languages').innerHTML = bars(d.languages.map(x => ({ n: x.n, label: x.key })));
    $('countries').innerHTML = bars(d.countries.map(x => ({ n: x.n, label: x.key })), { empty: '未提供(需在 Cloudflare 后面且 TRUST_PROXY=1)' });

    $('note').innerHTML = `口径:不使用 Cookie、不保存 IP;访客为「按天去重」,同一人跨天会被计为多个访客,所以没有回访率。
      开启 Do Not Track / GPC 的浏览器、爬虫不计入。原始记录保留 ${d.config.retention_days} 天。`
      + (d.config.stable_secret ? '' : ' <b style="color:var(--seal)">未设置 STATS_SECRET:服务重启当天的访客会被重复计数。</b>');

    charts.forEach(c => c.dispose());
    charts = [];
    const ax = { axisLabel: { color: C.muted, fontSize: 11 }, axisLine: { lineStyle: { color: C.line } },
                 axisTick: { show: false }, splitLine: { lineStyle: { color: '#e6e2d7' } } };
    const tip = { trigger: 'axis', backgroundColor: C.card, borderColor: C.line, textStyle: { color: C.ink, fontSize: 12 } };
    const daily = echarts.init($('c-daily'));
    daily.setOption({
      grid: { left: 44, right: 16, top: 30, bottom: 28 }, tooltip: tip,
      legend: { top: 0, left: 0, textStyle: { color: C.ink, fontSize: 12 } },
      xAxis: { type: 'category', data: d.series.map(x => x.day.slice(5)), ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', minInterval: 1, ...ax },
      series: [
        { name: '浏览', type: 'bar', data: d.series.map(x => x.pv), itemStyle: { color: 'rgba(91,115,145,.35)' }, barMaxWidth: 18 },
        { name: '访客', type: 'line', data: d.series.map(x => x.uv), smooth: .3, symbolSize: 5,
          lineStyle: { color: C.seal, width: 2 }, itemStyle: { color: C.seal } },
      ],
    });
    const hours = echarts.init($('c-hours'));
    hours.setOption({
      grid: { left: 44, right: 16, top: 12, bottom: 28 }, tooltip: tip,
      xAxis: { type: 'category', data: d.hours.map((_, h) => h + '时'), ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', minInterval: 1, ...ax },
      series: [{ name: '浏览', type: 'bar', data: d.hours, itemStyle: { color: C.gold }, barMaxWidth: 16 }],
    });
    charts.push(daily, hours);
  }

  async function refresh() {
    $('refresh').disabled = true;
    try {
      render(await fetchStats());
      $('login').hidden = true; $('dash').hidden = false; $('logout').hidden = false;
      charts.forEach(c => c.resize());
    } catch (e) {
      if (e.auth) { store('adm_token'); showLogin(e.message); }
      else $('range-note').textContent = '加载失败:' + e.message;
    } finally { $('refresh').disabled = false; }
  }

  function showLogin(msg) {
    $('dash').hidden = true; $('logout').hidden = true; $('login').hidden = false;
    $('api').value = apiBase();
    $('login-err').textContent = msg || '';
  }

  $('login').addEventListener('submit', e => {
    e.preventDefault();
    store('adm_api', $('api').value.trim());
    store('adm_token', $('token').value.trim());
    $('token').value = '';
    refresh();
  });
  $('logout').addEventListener('click', () => { store('adm_token'); showLogin(); });
  $('refresh').addEventListener('click', refresh);
  $('rng').addEventListener('click', e => {
    const b = e.target.closest('button[data-d]');
    if (!b) return;
    days = Number(b.dataset.d);
    $('rng').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    refresh();
  });

  /* 站长自己的访问不计入:在本机写一个标记,js/track.js 看到就不上报 */
  try { $('notrack').checked = localStorage.getItem('policy_notrack') === '1'; } catch (e) {}
  $('notrack').addEventListener('change', e => {
    try { e.target.checked ? localStorage.setItem('policy_notrack', '1') : localStorage.removeItem('policy_notrack'); } catch (err) {}
  });
  window.addEventListener('resize', () => charts.forEach(c => c.resize()));

  if (load('adm_token')) refresh(); else showLogin();
  setInterval(() => { if (!$('dash').hidden && !document.hidden) refresh(); }, 60000);
})();
