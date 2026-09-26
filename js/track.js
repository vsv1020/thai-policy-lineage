/* 站点统计上报。配置见 config/analytics.json(导出到 data/site/analytics.json)。
   第一方统计走后端 /api/t:无 Cookie、不用 localStorage 识别用户,访客在服务端按天哈希。
   浏览器开了 Do Not Track / Global Privacy Control 就什么都不发;
   站长在 /admin 里可以勾选「不统计本机」,写的是本地的 policy_notrack 标记。

   对外:PolicyTrack.page(path) · PolicyTrack.event(name, label, value) · PolicyTrack.search(q, hits)
   在配置加载前调用也没关系 —— 先进队列,确定上报地址后再一起发。 */

(function () {
  const base = (document.currentScript && document.currentScript.dataset.base) || '';
  const queue = [];
  let send = null;             // null = 还没决定;false = 不上报;function = 上报
  let searchTimer = null;

  // /index.html 与 / 是同一页,统一记成 /
  const here = () => location.pathname.replace(/index\.html$/, '');

  const optedOut = () => {
    if (navigator.doNotTrack === '1' || window.doNotTrack === '1' || navigator.globalPrivacyControl) return true;
    try { return localStorage.getItem('policy_notrack') === '1'; } catch (e) { return false; }
  };

  function push(payload) {
    if (send === false) return;
    if (send) send(payload); else queue.push(payload);
  }

  function utm() {
    const q = new URLSearchParams(location.search);
    return { us: q.get('utm_source') || q.get('ref') || '', um: q.get('utm_medium') || '',
             uc: q.get('utm_campaign') || '' };
  }

  const T = {
    page(path) {
      push({ k: 'pv', p: path || here() });
    },
    event(name, label, value) {
      push({ k: 'event', n: name, p: here(),
             l: label == null ? '' : String(label).slice(0, 160),
             v: typeof value === 'number' ? value : undefined });
    },
    /* 检索框是边打边搜的:只记停下来 1.5 秒后的最终关键词,不记「签」「签证」「签证续」 */
    search(q, hits) {
      clearTimeout(searchTimer);
      if (!q) return;
      searchTimer = setTimeout(() => T.event('search', q, hits), 1500);
    },
  };
  window.PolicyTrack = T;

  async function endpoint(cfg) {
    const sh = cfg.self_hosted || {};
    if (!sh.enabled) return null;
    if (sh.endpoint) return sh.endpoint.replace(/\/$/, '') + '/api/t';
    if (window.PolicyData) {                 // 主页:沿用 api.js 的探测结果
      return (await PolicyData.ready()) ? PolicyData.API_BASE + '/api/t' : null;
    }
    if (!location.protocol.startsWith('http')) return null;
    // 落地页没有 api.js:每个标签页探测一次同源后端,结果缓存在 sessionStorage
    const KEY = 'policy_api_ok';
    let ok = null;
    try { ok = sessionStorage.getItem(KEY); } catch (e) {}
    if (ok === null) {
      try {
        const r = await fetch(base + 'api/health', { cache: 'no-store' });
        ok = r.ok ? '1' : '0';
      } catch (e) { ok = '0'; }
      try { sessionStorage.setItem(KEY, ok); } catch (e) {}
    }
    return ok === '1' ? new URL(base + 'api/t', location.href).href : null;
  }

  function thirdParty(cfg) {
    const cf = (cfg.cloudflare || {}).token;
    if (cf && /^[0-9a-f]{32}$/i.test(cf)) {
      const s = document.createElement('script');
      s.defer = true;
      s.src = 'https://static.cloudflareinsights.com/beacon.min.js';
      s.setAttribute('data-cf-beacon', JSON.stringify({ token: cf }));
      document.head.appendChild(s);
    }
    const pl = cfg.plausible || {};
    if (pl.domain && /^https:\/\//.test(pl.src || '')) {
      const s = document.createElement('script');
      s.defer = true; s.src = pl.src; s.setAttribute('data-domain', pl.domain);
      document.head.appendChild(s);
    }
  }

  /* 点击统计:外链(含官方原文)、广告、打赏渠道、分享。只记域名,不记完整 URL */
  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    let url;
    try { url = new URL(a.href, location.href); } catch (err) { return; }
    const box = a.closest('.ad-box');
    if (box) {
      const sp = a.querySelector('.ad-sponsor');
      T.event('ad_click', `${box.dataset.slot || ''}|${sp ? sp.textContent.trim() : 'adsense'}`);
    } else if (a.closest('#detail-share')) {
      T.event('share', (a.getAttribute('href') || '').replace(/^.*\/p\/|\.html$/g, ''));
    } else if (a.closest('.support-ch')) {
      T.event('tip_link', a.textContent.replace('↗', '').trim());
    } else if (url.host && url.host !== location.host && /^https?:$/.test(url.protocol)) {
      T.event('outbound', url.hostname);
    }
  }, true);

  (async () => {
    let cfg = null;
    try {
      const r = await fetch(base + 'data/site/analytics.json', { cache: 'no-store' });
      if (r.ok) cfg = await r.json();
    } catch (e) {}
    if (!cfg || (cfg.respect_dnt !== false && optedOut())) { send = false; queue.length = 0; return; }
    thirdParty(cfg);
    const url = await endpoint(cfg);
    if (!url) { send = false; queue.length = 0; return; }

    const first = { r: document.referrer, lang: (navigator.language || '').slice(0, 8), ...utm() };
    let firstSent = false;
    send = payload => {
      // 来源与 UTM 只随本次打开的第一次浏览上报,之后的站内切换不重复计来源
      const body = JSON.stringify(!firstSent && payload.k === 'pv' ? { ...payload, ...first }
        : { ...payload, lang: first.lang });
      if (payload.k === 'pv') firstSent = true;
      // text/plain 是「简单请求」,跨域也不触发预检
      if (!(navigator.sendBeacon && navigator.sendBeacon(url, body))) {
        fetch(url, { method: 'POST', body, keepalive: true, mode: 'no-cors' }).catch(() => {});
      }
    };
    // 首屏浏览先发,再发加载期间排队的事件
    const pending = queue.splice(0);
    send({ k: 'pv', p: here() });
    pending.forEach(send);
  })();
})();
