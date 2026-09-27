/* 采集状态看板(只在管理后台 /admin 显示,前台不展示)。
   存在的理由 —— 每日采集连续失败却没人看见,站点就会在「看起来正常」的状态下慢慢变旧。
   数据来自 GET /api/admin/ops;由 js/admin.js 取数后调用 PolicyOps.render(o)。 */

(function () {
  const E = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const put = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };

  const STATUS = {
    ok:          { t: '正常', c: 'var(--green)' },
    partial:     { t: '部分成功', c: 'var(--gold-deep)' },
    degraded:    { t: '部分降级', c: 'var(--gold-deep)' },
    stale:       { t: '过期', c: 'var(--gold-deep)' },
    error:       { t: '失败', c: 'var(--seal)' },
    failed:      { t: '失败', c: 'var(--seal)' },
    down:        { t: '中断', c: 'var(--seal)' },
    unattempted: { t: '未尝试', c: 'var(--muted)' },
  };
  const tag = st => {
    const x = STATUS[st] || { t: st, c: 'var(--muted)' };
    return `<span class="pill" style="color:${x.c};border-color:${x.c}">${E(x.t)}</span>`;
  };
  const row = (k, v, hint) => `<div class="cal-item"><span style="min-width:120px;color:var(--ink-2)">${E(k)}</span>
    <span><b>${E(v)}</b>${hint ? ` <span style="color:var(--muted)">${E(hint)}</span>` : ''}</span></div>`;

  function render(o) {
    const c = o.corpus || {}, f = o.freshness || {};
    const stale = f.days_since_newest != null && f.days_since_newest > 14;
    const banner = o.health === 'ok' && !stale ? ''
      : `<div class="warn-box" style="margin-bottom:16px">${
          o.health === 'down' ? '<b>采集管道中断</b>:所有数据源本轮均未成功。'
          : o.health === 'degraded' ? '<b>部分数据源不可用</b>。' : ''}${
          o.failure_streak > 1 ? ` 已连续 <b>${E(o.failure_streak)}</b> 次运行失败。` : ''}${
          stale ? ` 最新一条政策距今已 <b>${E(f.days_since_newest)}</b> 天 —— 页面内容可能已过时。` : ''}
          站点仍按最后一次成功的数据展示,未做任何补造。</div>`;
    put('ops-banner', banner || ' ');
    put('ops-sub', `截至 ${E((o.as_of || '').slice(0, 16).replace('T', ' '))} 曼谷时间 · 管道状态 ${tag(o.health)}`);

    put('ops-sources', (o.sources || []).map(sx =>
      `<div class="cal-item" style="align-items:flex-start"><span style="min-width:60px">${tag(sx.status)}</span>
        <span><b>${E(sx.name)}</b><br><span style="color:var(--muted);font-size:12px">
        上次成功:${E(sx.last_ok ? sx.last_ok.slice(0, 10) : '从未')} · ${E(sx.detail || '')}</span></span></div>`
    ).join('') || '<div class="mod-sub">尚未配置数据源</div>');

    put('ops-corpus',
      row('可呈现条目', c.presentable, '出现在首页与检索里的')
      + row('事实层总记录', c.total_records, 'JSONL 审计记录,含待翻译与已跳过')
      + row('待翻译', c.pending_translation, c.pending_translation ? '每日采集后自动翻译(DEEPSEEK_API_KEY)' : '')
      + row('判定无关已跳过', c.skipped_irrelevant, '人事任免、授勋等')
      + row('模型翻译分类', c.llm_enriched, '数据层记为 verified=false')
      + row('已人工复核', c.verified, '')
      + row('有官方原文链接', c.with_official_link, `共 ${c.presentable || 0} 条可呈现`)
      + row('最新一条政策', f.newest_document || '—',
            f.days_since_newest != null ? `距今 ${f.days_since_newest} 天` : ''));

    const runs = (o.runs || []).slice().reverse();
    put('ops-runs', runs.length ? '' :
      '<div class="mod-sub" style="margin-top:8px">尚无运行记录 —— 定时采集部署后每天会在这里留一条</div>');
    if (runs.length && window.echarts) {
      const el = document.getElementById('c-runs');
      echarts.dispose(el);
      const ch = echarts.init(el);
      const color = st => (STATUS[st] || {}).c || '#b9b3a4';
      const css = v => getComputedStyle(document.documentElement).getPropertyValue(v.slice(4, -1)).trim() || v;
      ch.setOption({
        grid: { left: 30, right: 10, top: 10, bottom: 24 },
        tooltip: { formatter: p => { const r = runs[p.dataIndex];
          return `${E(r.started_at.slice(0, 16).replace('T', ' '))}<br>${E((STATUS[r.status] || {}).t || r.status)}`
            + ` · 新增 ${E(r.added)} · 耗时 ${E(r.duration_s)}s`; } },
        xAxis: { type: 'category', data: runs.map(r => r.started_at.slice(5, 10)),
                 axisLabel: { fontSize: 10, color: '#8b877c' }, axisTick: { show: false } },
        yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10, color: '#8b877c' },
                 splitLine: { lineStyle: { color: '#e6e2d7' } } },
        series: [{ type: 'bar', barMaxWidth: 16,
          data: runs.map(r => ({ value: Math.max(r.added, 0.2), itemStyle: { color: css(color(r.status)) } })) }],
      });
      window.addEventListener('resize', () => ch.resize());
    }

    const q = o.queue_sample || [];
    put('ops-queue', q.length
      ? q.map(x => `<div class="lib-row"><span class="lib-date" style="font-size:11px">${E(x.uid)}</span>
          <div class="lib-title" style="font-weight:400">${E(x.title_th)}</div></div>`).join('')
      : '<div class="mod-sub">队列为空</div>');
  }

  window.PolicyOps = { render };
})();
