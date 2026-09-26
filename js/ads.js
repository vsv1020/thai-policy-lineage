/* 广告位渲染。配置见 config/ads.json(导出到 data/site/ads.json)。
   规则:明确标注「广告」;只渲染 allowed_categories 内的类别;过期或未到期不显示;
   rel="sponsored nofollow" 让搜索引擎不把付费链接当推荐。默认整体关闭。 */

(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const base = document.currentScript && document.currentScript.dataset.base || '';
  let cfg = null, adsenseLoaded = false;

  const today = new Date().toISOString().slice(0, 10);
  const live = it => (!it.start || it.start <= today) && (!it.end || today <= it.end);
  const allowed = it => cfg.allowed_categories && it.category in cfg.allowed_categories;

  function pick(slot) {
    const s = (cfg.slots || {})[slot];
    if (!s) return null;
    const items = (s.items || []).filter(it => allowed(it) && live(it) && /^https?:\/\//.test(it.href || ''));
    if (items.length) return items[Math.floor(Math.random() * items.length)];
    return null;
  }

  function adsenseHtml(slot) {
    const a = cfg.adsense || {};
    const id = (a.slots || {})[slot];
    if (!a.client || !id) return '';
    if (!adsenseLoaded) {
      const sc = document.createElement('script');
      sc.async = true; sc.crossOrigin = 'anonymous';
      sc.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(a.client)}`;
      document.head.appendChild(sc);
      adsenseLoaded = true;
    }
    setTimeout(() => { try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {} }, 0);
    return `<ins class="adsbygoogle" style="display:block" data-ad-client="${esc(a.client)}"
      data-ad-slot="${esc(id)}" data-ad-format="auto" data-full-width-responsive="true"></ins>`;
  }

  function html(slot) {
    if (!cfg || !cfg.enabled) return '';
    const it = pick(slot);
    const inner = it
      ? `<a href="${esc(it.href)}" target="_blank" rel="sponsored nofollow noopener" class="ad-link">
           <div class="ad-title">${esc(it.title)}</div>
           ${it.text ? `<div class="ad-text">${esc(it.text)}</div>` : ''}
           <div class="ad-sponsor">${esc(it.sponsor)}</div></a>`
      : adsenseHtml(slot);
    if (!inner) return '';
    window.PolicyTrack && PolicyTrack.event('ad_view', `${slot}|${it ? it.sponsor : 'adsense'}`);
    return `<div class="ad-box" data-slot="${esc(slot)}"><span class="ad-label">${esc(cfg.label || '广告')}</span>${inner}</div>`;
  }

  function fill() {
    document.querySelectorAll('.ad-slot[data-slot]').forEach(el => {
      if (el.dataset.filled) return;
      const h = html(el.dataset.slot);
      if (h) { el.innerHTML = h; el.dataset.filled = '1'; }
    });
  }

  /* 首页政策流行内广告:由 data.js 渲染完 feed 后调用 */
  function injectFeed(feedEl) {
    if (!cfg || !cfg.enabled || !feedEl) return;
    const n = ((cfg.slots || {}).home_feed_inline || {}).after_index || 3;
    const cards = feedEl.querySelectorAll('.policy-card');
    const h = html('home_feed_inline');
    if (h && cards.length > n) cards[n - 1].insertAdjacentHTML('afterend', h);
  }

  window.PolicyAds = { injectFeed, fill, ready: fetch(base + 'data/site/ads.json', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(c => { cfg = c; fill(); const f = document.getElementById('feed'); if (f) injectFeed(f); return c; })
    .catch(() => null) };
})();
