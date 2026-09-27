/* 管理后台「SEO / GEO」标签:收录、爬虫抓取、搜索与 AI 来源、每日监控日报。
   数据来自 GET /api/admin/seo(服务器实时数据 + 每天 03:00 监控任务写入的 data/seo/latest.json);
   由 js/admin.js 取数后调用 PolicySeo.render(d)。 */

(function () {
  const E = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const put = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
  const LV = { error: ['严重', 'var(--seal)'], warn: ['需处理', 'var(--gold-deep)'], info: ['建议', 'var(--muted)'] };
  const CH = { search: '搜索引擎', ai: 'AI 助手', social: '社交', referral: '其他网站', direct: '直接访问' };
  let chart = null;

  const kpi = (label, val, sub) => `<div class="adm-card kpi"><div class="k-label">${E(label)}</div>
    <div class="k-val">${val == null ? '—' : E(val)}</div><div class="k-chg">${E(sub || '')}</div></div>`;
  const list = (rows, empty) => rows.length ? rows.map(r => `<div class="bar-row"><div class="bar-lbl"><span>${r[0]}</span></div>
    <div class="bar-n">${E(r[1])}</div></div>`).join('') : `<div class="empty">${E(empty)}</div>`;

  function render(d) {
    const mon = d.monitor || null, m = (mon && mon.metrics) || {};
    const bots = d.crawlers.bots || [];
    const sum = g => bots.filter(b => b.group === g).reduce((a, b) => a + b.hits, 0);
    const cov = d.coverage || {};
    put('seo-sub', `统计区间 ${d.range.start} ~ ${d.range.end}` + (mon
      ? ` · 最近一次监控:${E(mon.date)}(每天曼谷时间 03:00 自动运行)`
      : ' · 还没有监控日报:合并后每天 03:00 由 GitHub Actions「SEO / GEO 每日监控」生成'));

    put('seo-kpis', [
      kpi('Google 已确认收录', m.gsc_checked ? `${m.gsc_indexed || 0} / ${m.gsc_checked}` : null,
        m.gsc_checked ? '已收录 / 已检查(URL 检查接口)' : '未接入 Search Console'),
      kpi('Bing 已收录', m.bing_in_index, m.bing_in_index == null ? '未接入 Bing Webmaster' : 'Bing 站长平台'),
      kpi('搜索爬虫抓取', sum('search'), `落地页覆盖 ${cov.search_pct == null ? '—' : cov.search_pct + '%'}`),
      kpi('AI 爬虫抓取', sum('ai'), 'GPTBot、ClaudeBot、PerplexityBot 等'),
      kpi('搜索来访', (d.channels || {}).search || 0, '从搜索结果点进来'),
      kpi('AI 来访', (d.channels || {}).ai || 0, '从 ChatGPT、Perplexity 等点进来'),
      kpi('Google 曝光 / 点击', m.gsc_impressions_28d == null ? null : `${m.gsc_impressions_28d} / ${m.gsc_clicks_28d}`, '近 28 天'),
      kpi('AI 实测引用', m.geo_asked ? `${m.geo_cited || 0} / ${m.geo_asked}` : null, m.geo_asked ? '引用本站的问题数' : '未配置 PERPLEXITY_API_KEY'),
    ].join(''));

    const issues = (mon && mon.issues) || [];
    put('seo-issues', mon ? (issues.length ? issues.map(i => {
      const [t, c] = LV[i.level] || [i.level, 'var(--muted)'];
      return `<div style="padding:8px 0;border-bottom:1px dashed var(--line);font-size:13px">
        <span class="tag" style="border-color:${c};color:${c}">${E(t)}</span> ${E(i.msg)}
        ${i.fix ? `<div style="color:var(--ink-2);font-size:12px;margin-top:3px">建议:${E(i.fix)}</div>` : ''}
        ${i.items && i.items.length ? `<details style="font-size:12px;color:var(--muted);margin-top:3px"><summary>明细 ${i.items.length} 项</summary>${i.items.map(x => `<div>${E(x)}</div>`).join('')}</details>` : ''}
      </div>`;
    }).join('') : '<div class="empty">今天没有发现问题。</div>')
      + ((mon.disabled || []).length ? `<div class="note" style="margin-top:12px"><b>未启用的数据源</b><br>${mon.disabled.map(E).join('<br>')}</div>` : '')
      : '<div class="empty">暂无日报。</div>');

    put('seo-bots', bots.length
      ? `<table class="t"><thead><tr><th>爬虫</th><th>类型</th><th class="n">次数</th><th class="n">页面</th><th class="n">最近</th></tr></thead><tbody>`
        + bots.map(b => `<tr><td>${E(b.bot)}</td><td>${b.group === 'ai' ? 'AI' : '搜索'}</td><td class="n">${b.hits}</td><td class="n">${b.pages}</td><td class="n">${E(b.last_seen)}</td></tr>`).join('')
        + '</tbody></table>'
      : '<div class="empty">这段时间没有爬虫来过。新站通常要在站长平台提交 sitemap 后 1–4 周才开始被抓取。</div>');

    const ch = d.channels || {};
    put('seo-channels', list(Object.keys(CH).filter(k => ch[k]).map(k => [E(CH[k]), ch[k]]), '暂无访问')
      + '<h3 style="margin-top:14px">搜索引擎</h3>' + list((d.search_sources || []).map(x => [E(x.key), x.n]), '暂无搜索来访')
      + '<h3 style="margin-top:14px">AI 助手</h3>' + list((d.ai_sources || []).map(x => [E(x.key), x.n]), '暂无 AI 来访'));
    put('seo-landings', list([...(d.search_landings || []).map(x => [`<span class="tag">搜索</span> ${E(x.key)}`, x.n]),
                              ...(d.ai_landings || []).map(x => [`<span class="tag ok">AI</span> ${E(x.key)}`, x.n])],
                             '还没有从搜索或 AI 进来的访问'));
    const errs = d.crawlers.errors || [];
    put('seo-errors', errs.length ? list(errs.map(x => [`${x.status} ${E(x.path)} <small style="color:var(--muted)">${E(x.bots)}</small>`, x.n]), '')
      : '<div class="empty">爬虫没有遇到报错页面。</div>');

    const q = ((mon && mon.sections && mon.sections.gsc) || {}).top_queries || [];
    put('seo-queries', q.length ? `<table class="t"><thead><tr><th>搜索词</th><th class="n">曝光</th><th class="n">点击</th><th class="n">排名</th></tr></thead><tbody>`
      + q.map(x => `<tr><td>${E(x.q)}</td><td class="n">${x.impr}</td><td class="n">${x.clicks}</td><td class="n">${x.pos}</td></tr>`).join('') + '</tbody></table>'
      : '<div class="empty">接入 Search Console 后显示 Google 搜索词。</div>');

    const geo = ((mon && mon.sections && mon.sections.geo) || {}).results || [];
    put('seo-geo', geo.length ? geo.map(x => `<div style="font-size:13px;padding:4px 0">${x.cited ? '✅' : '❌'} ${E(x.q)}
      <div style="font-size:12px;color:var(--muted)">${E((x.sources || []).slice(0, 5).join('、') || x.error || '')}</div></div>`).join('')
      : '<div class="empty">配置 PERPLEXITY_API_KEY 后,每天实测几个问题,看 AI 回答是否引用本站。</div>');

    const trend = (mon && mon.trend) || [];
    const el = document.getElementById('c-seo');
    if (el && window.echarts) {
      chart = chart || echarts.init(el);
      const s = d.crawlers.series || [];
      chart.setOption({
        tooltip: { trigger: 'axis' }, legend: { top: 0, textStyle: { fontSize: 11 } },
        grid: { left: 36, right: 12, top: 30, bottom: 24 },
        xAxis: { type: 'category', data: s.map(x => x.day.slice(5)) }, yAxis: { type: 'value', minInterval: 1 },
        series: [{ name: '搜索爬虫', type: 'bar', stack: 'c', data: s.map(x => x.search), itemStyle: { color: '#5b7391' } },
                 { name: 'AI 爬虫', type: 'bar', stack: 'c', data: s.map(x => x.ai), itemStyle: { color: '#b0332a' } }],
      }, true);
      window.addEventListener('resize', () => chart.resize());
    }
    put('seo-trend', trend.length > 1 ? `<table class="t"><thead><tr><th>日期</th><th class="n">收录/检查</th><th class="n">Googlebot</th><th class="n">AI 爬虫</th><th class="n">搜索来访</th><th class="n">AI 来访</th><th class="n">问题</th></tr></thead><tbody>`
      + trend.slice().reverse().slice(0, 14).map(h => { const x = h.metrics || {}, i = h.issues || {};
        return `<tr><td>${E(h.date)}</td><td class="n">${x.gsc_checked ? `${x.gsc_indexed || 0}/${x.gsc_checked}` : '—'}</td><td class="n">${x.googlebot_7d ?? '—'}</td>
          <td class="n">${x.crawl_ai_7d ?? '—'}</td><td class="n">${x.visits_search_7d ?? '—'}</td><td class="n">${x.visits_ai_7d ?? '—'}</td>
          <td class="n">${(i.error || 0) + (i.warn || 0)}</td></tr>`; }).join('') + '</tbody></table>'
      : '<div class="empty">监控运行两天以上后显示每日变化。</div>');
  }

  window.PolicySeo = { render, resize: () => chart && chart.resize() };
})();
