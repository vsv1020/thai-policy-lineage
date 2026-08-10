/* 数据获取的唯一入口 —— 三级降级:
     ① 后端 API(有实时数据、可分面检索)
     ② data/site/*.json 静态导出(GitHub Pages,后端没部署时)
     ③ index.html 里的静态内容(连 JSON 都取不到时,页面不白屏)

   API 地址来源(按优先级):?api= 查询参数 → window.POLICY_API_BASE → 同源。
   探测只做一次(/api/health),避免每个数据文件都失败一遍。 */

(function () {
  const ENDPOINTS = {
    overview:   { api: 'overview',   file: 'data/site/policies.json' },
    trends:     { api: 'trends',     file: 'data/site/trends.json' },
    lineage:    { api: 'lineage',    file: 'data/site/lineage.json' },
    dimensions: { api: 'dimensions', file: 'data/site/dimensions.json' },
  };

  const API_BASE = (() => {
    const q = new URLSearchParams(location.search).get('api');
    if (q !== null) return q.replace(/\/$/, '');
    if (typeof window.POLICY_API_BASE === 'string') return window.POLICY_API_BASE.replace(/\/$/, '');
    return location.protocol.startsWith('http') ? '' : null;   // file:// 直接走静态
  })();

  window.DATA_MODE = 'static';   // 'api' | 'static' | 'inline'

  const _probe = (async () => {
    if (API_BASE === null) return false;
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 2500);
      const r = await fetch(`${API_BASE}/api/health`, { signal: ctrl.signal, cache: 'no-store' });
      clearTimeout(t);
      if (!r.ok) return false;
      window.DATA_MODE = 'api';
      return true;
    } catch { return false; }
  })();

  async function getData(name) {
    const ep = ENDPOINTS[name];
    if (!ep) throw new Error('未知数据源 ' + name);
    if (await _probe) {
      try {
        const r = await fetch(`${API_BASE}/api/${ep.api}`, { cache: 'no-store' });
        if (r.ok) return await r.json();
        console.warn(`[api] /${ep.api} → HTTP ${r.status},回退静态文件`);
      } catch (err) {
        console.warn(`[api] /${ep.api} 失败,回退静态文件:`, err.message);
      }
    }
    const r = await fetch(ep.file, { cache: 'no-store' });
    if (!r.ok) throw new Error(`${ep.file} → HTTP ${r.status}`);
    return await r.json();
  }

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* 只在有内容时替换 —— 空字符串会把 HTML 兜底内容也擦掉 */
  function set(id, html) {
    const el = document.getElementById(id);
    if (el && html) el.innerHTML = html;
  }

  /* 样本不足时统一的提示条,而不是画一张看起来很确定的图 */
  function insufficientNote(d, what) {
    if (d.sufficient === false) {
      return `<div class="reading" style="border-color:var(--gold-deep)">
        数据不足:当前仅 <b>${esc(d.n)}</b> 条${esc(what)}样本(建议 ≥${esc(d.min_n)} 条再据此判断)。
        下方数字是真实计数,但不足以支撑结论。</div>`;
    }
    return '';
  }

  window.PolicyData = { getData, esc, set, insufficientNote, API_BASE, ENDPOINTS };
})();
