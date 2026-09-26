/* 打赏入口。配置见 config/support.json(导出到 data/site/support.json)。
   入口:顶栏按钮、详情页与落地页正文后的 .support-slot。全部渠道为空时整体隐藏。 */

(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const base = (document.currentScript && document.currentScript.dataset.base) || '';
  let cfg = null;

  const usable = ch =>
    (ch.type === 'promptpay' && ch.id) || (ch.type === 'image' && ch.src) ||
    (ch.type === 'link' && /^https?:\/\//.test(ch.href || ''));

  function qrSvg(text) {
    if (!window.qrcode) return '';
    const q = qrcode(0, 'M'); q.addData(text); q.make();
    return q.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }

  function promptpayBlock(ch) {
    const amounts = cfg.amounts_thb || [];
    const btns = [''].concat(amounts).map(a =>
      `<button class="support-amt" data-amt="${esc(a)}">${a ? '฿' + esc(a) : '自定金额'}</button>`).join('');
    return `<div class="support-ch" data-type="promptpay">
      <div class="support-ch-label">${esc(ch.label)}</div>
      <div class="support-amts">${btns}</div>
      <div class="support-qr" data-pp="${esc(ch.id)}"></div>
      <div class="support-hint">选金额后二维码会带上金额;「自定金额」由你在银行 App 里输入</div>
    </div>`;
  }

  function body() {
    const chs = (cfg.channels || []).filter(usable);
    return `<div class="support-msg">${esc(cfg.message)}</div>
      <div class="support-grid">${chs.map(ch =>
        ch.type === 'promptpay' ? promptpayBlock(ch)
        : ch.type === 'image' ? `<div class="support-ch"><div class="support-ch-label">${esc(ch.label)}</div>
            <img src="${esc(base + ch.src)}" alt="${esc(ch.label)}" class="support-img" loading="lazy"></div>`
        : `<div class="support-ch"><a class="btn-solid" href="${esc(ch.href)}" target="_blank"
            rel="noopener">${esc(ch.label)} ↗</a></div>`).join('')}</div>
      <div class="support-note">${esc(cfg.usage_note)}</div>`;
  }

  function wire(root) {
    root.querySelectorAll('.support-qr[data-pp]').forEach(box => {
      const draw = amt => {
        try { box.innerHTML = qrSvg(PromptPay.payload(box.dataset.pp, amt || null)); }
        catch (e) { box.textContent = 'PromptPay 配置有误:' + e.message; }
      };
      draw(null);
      box.closest('.support-ch').querySelectorAll('.support-amt').forEach(b =>
        b.addEventListener('click', () => {
          box.closest('.support-ch').querySelectorAll('.support-amt')
            .forEach(x => x.classList.toggle('on', x === b));
          draw(Number(b.dataset.amt) || null);
          window.PolicyTrack && PolicyTrack.event('tip_amount', b.dataset.amt || 'custom');
        }));
    });
  }

  function openModal(src) {
    window.PolicyTrack && PolicyTrack.event('tip_open', typeof src === 'string' ? src : 'button');
    let m = document.getElementById('support-modal');
    if (!m) {
      m = document.createElement('div');
      m.id = 'support-modal';
      m.className = 'support-modal';
      m.innerHTML = `<div class="support-dialog" role="dialog" aria-modal="true">
        <button class="support-close" aria-label="关闭">×</button>
        <h3 class="mod">${esc(cfg.title)}</h3>${body()}</div>`;
      document.body.appendChild(m);
      m.addEventListener('click', e => { if (e.target === m) m.remove(); });
      m.querySelector('.support-close').addEventListener('click', () => m.remove());
      document.addEventListener('keydown', function k(e) {
        if (e.key === 'Escape') { m.remove(); document.removeEventListener('keydown', k); } });
      wire(m);
    }
  }

  function fillSlots() {
    document.querySelectorAll('.support-slot').forEach(el => {
      if (el.dataset.filled) return;
      el.innerHTML = `<div class="support-inline"><span>这条整理对你有用?本站免费运营,靠读者打赏支撑。</span>
        <button class="btn-solid support-open">打赏支持</button></div>`;
      el.querySelector('.support-open').addEventListener('click', () => openModal('inline'));
      el.dataset.filled = '1';
    });
  }

  fetch(base + 'data/site/support.json', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(c => {
      if (!c || !c.enabled || !(c.channels || []).some(usable)) return;
      cfg = c;
      document.querySelectorAll('[data-support-button]').forEach(b => {
        b.hidden = false; b.addEventListener('click', () => openModal('header')); });
      fillSlots();
      new MutationObserver(fillSlots).observe(document.body, { childList: true, subtree: true });
    })
    .catch(() => {});

  window.PolicySupport = { open: () => cfg && openModal('api') };
})();
