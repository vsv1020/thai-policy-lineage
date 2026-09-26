# -*- coding: utf-8 -*-
"""打赏:PromptPay 二维码数据必须正确 —— 错一位 CRC,读者扫码就失败,钱就丢了。"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="需要 node 运行前端纯函数")


def pp(*args) -> str:
    js = f"const P=require({json.dumps(str(ROOT / 'js' / 'promptpay.js'))});" \
         f"console.log(JSON.stringify(P.payload(...{json.dumps(list(args))})))"
    return json.loads(subprocess.check_output([node, "-e", js], text=True))


def crc(s: str) -> str:
    js = f"const P=require({json.dumps(str(ROOT / 'js' / 'promptpay.js'))});" \
         f"console.log(P.crc16({json.dumps(s)}))"
    return subprocess.check_output([node, "-e", js], text=True).strip()


def test_crc_matches_ccitt_false_check_value():
    assert crc("123456789") == "29B1", "CRC-16/CCITT-FALSE 的标准校验值"


def test_phone_payload_regression():
    """回归:固定输出,防止改动悄悄破坏字段顺序或长度编码。
    结构按 EMVCo/泰国央行规范逐字段构造,CRC 已对标准校验值验证;
    但真实可用性只能用银行 App 实扫确认 —— 上线前务必扫一次 1 泰铢。"""
    assert pp("0812345678") == \
        "00020101021129370016A000000677010111011300668123456785802TH530376463045D82"


def test_amount_makes_single_use_code():
    out = pp("0812345678", 100)
    assert out.startswith("000201010212"), "带金额应为一次性码(12)"
    assert "5406100.00" in out


def test_tax_id_uses_tag_02():
    assert "0213" + "0105551234567" in pp("0105551234567")


def test_every_payload_self_verifies():
    for args in (("0812345678",), ("0812345678", 30), ("0105551234567", 300)):
        out = pp(*args)
        assert crc(out[:-4]) == out[-4:]


def test_bad_id_raises():
    with pytest.raises(subprocess.CalledProcessError):
        pp("12345")


def test_support_disabled_by_default():
    cfg = json.loads((ROOT / "config" / "support.json").read_text(encoding="utf-8"))
    assert cfg["enabled"] is False, "打赏默认关闭,填好渠道再开"
