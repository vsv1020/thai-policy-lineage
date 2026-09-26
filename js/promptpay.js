/* PromptPay 二维码数据(EMVCo 商户码格式,泰国央行规范)。
   纯函数,不依赖 DOM —— 方便在 node 里测试。二维码图形由 vendor/qrcode-generator 画。

   隐私提醒:用手机号做收款 ID 时,号码会被编码进二维码,任何人扫码解码都能看到;
   扫码付款时银行 App 还会显示收款人真实姓名。见 docs/monetization.md。 */

(function (root) {
  const f = (id, v) => id + String(v.length).padStart(2, '0') + v;

  function crc16(s) {                       // CRC-16/CCITT-FALSE
    let crc = 0xFFFF;
    for (let i = 0; i < s.length; i++) {
      crc ^= s.charCodeAt(i) << 8;
      for (let j = 0; j < 8; j++) crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) : (crc << 1);
      crc &= 0xFFFF;
    }
    return crc.toString(16).toUpperCase().padStart(4, '0');
  }

  /* id: 手机号(10 位,0 开头)、身份证/税号(13 位)或电子钱包号(15 位)
     amount: 泰铢,可省略(省略时付款人自己输入金额) */
  function payload(id, amount) {
    const digits = String(id).replace(/\D/g, '');
    let tag, target;
    if (digits.length >= 15) { tag = '03'; target = digits; }
    else if (digits.length >= 13) { tag = '02'; target = digits; }
    else if (digits.length === 10 && digits[0] === '0') {
      tag = '01'; target = ('66' + digits.slice(1)).padStart(13, '0');
    } else {
      throw new Error('PromptPay ID 格式不对:需要 10 位手机号、13 位身份证/税号或 15 位电子钱包号');
    }
    const amt = amount != null && Number(amount) > 0 ? Number(amount).toFixed(2) : null;
    const body = f('00', '01')
      + f('01', amt ? '12' : '11')          // 12 = 单次(带金额),11 = 可重复使用
      + f('29', f('00', 'A000000677010111') + f(tag, target))
      + f('58', 'TH') + f('53', '764')
      + (amt ? f('54', amt) : '')
      + '6304';
    return body + crc16(body);
  }

  const api = { payload, crc16 };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PromptPay = api;
})(typeof window !== 'undefined' ? window : globalThis);
