# -*- coding: utf-8 -*-
"""从泰文标题认出发文机关 —— app.enrich(数据层:重定 agency_ids)与 app.seo(页面层:能不能说「发文机关」)共用这一套判断。

公报标题的写法是「文件类型 + 发文机关 + เรื่อง/ว่าด้วย + 事由」:
    ประกาศกรมสรรพากร เรื่อง …                     → 税务厅
    คำสั่งคณะกรรมการว่าด้วยความปลอดภัยของสินค้าและบริการ ที่ 2/2569 เรื่อง …  → 商品与服务安全委员会
    ข้อบังคับของคณะกรรมการการบินพลเรือน ฉบับที่ 105 ว่าด้วย …                  → 民用航空委员会
    ประกาศสำนักนายกรัฐมนตรีและกระทรวงมหาดไทย เรื่อง …                          → 总理府 + 内政部(联合发文)

原则是「宁可认不出,不要认错」:
- 机关名必须紧跟在文件类型之后(中间只允许「ของ」和「อธิบดี / เลขาธิการ / ผู้ว่าการ / ผู้อำนวยการ」这类署名职务)。
  原先在「เรื่อง」之前的整段里找任意位置的机关名:词表里没有的厅局后面跟着上级部委时(「ประกาศกรมควบคุมโรค กระทรวงสาธารณสุข」),
  会把上级部委当成发文者;「ประกาศสำนักงานที่ดินกรุงเทพมหานคร」(曼谷土地办公室,属土地厅)被认成曼谷市。
- 名字里本身含「ว่าด้วย」的委员会(商品与服务安全委员会、商品与服务价格中央委员会、合同委员会)按整个名字认,
  不在「ว่าด้วย」处截断;词表里没有的这类委员会照旧在「ว่าด้วย」处截断,认不出。
- 部令(กฎกระทรวง)、皇家法令(พระราชกฤษฎีกา)、法律(พระราชบัญญัติ / พระราชกำหนด)的标题没有发文机关段,
  后面出现的机关名是事由的一部分(「กฎกระทรวงแบ่งส่วนราชการกรมวิชาการเกษตร กระทรวงเกษตรและสหกรณ์」),一律认不出。
- 匹配前去掉空白、把拆开写的「ํา」并回「ำ」:公报标题的空格和元音写法并不统一。
"""
from __future__ import annotations

import re

# 标题以这些开头的没有发文机关段
NO_ISSUER_PREFIXES = ("กฎกระทรวง", "พระราชกฤษฎีกา", "พระราชบัญญัติ", "พระราชกำหนด", "ประมวลกฎหมาย",
                      "รัฐธรรมนูญ")
# 文件类型(长的在前)
DOC_TYPES = ("ข้อบัญญัติ", "ข้อบังคับ", "ข้อกำหนด", "คำวินิจฉัย", "คำแนะนำ", "ประกาศ", "คำสั่ง", "ระเบียบ", "กฎ")
# 文件类型和机关名之间允许出现的署名职务:厅长、秘书长、总裁(央行、电力局)、局长
TITLES = ("อธิบดี", "เลขาธิการ", "ผู้ว่าการ", "ผู้อำนวยการ")
JOINT = "และ"
CUT_RE = re.compile(r"เรื่อง|ว่าด้วย")
MIN_NAME = 4                                   # 4 个字符以下的缩写不用


def norm(text: str) -> str:
    return re.sub(r"[\s​‌‍﻿]+", "", str(text or "")).replace("ํา", "ำ")


def agency_rules(v: dict) -> list[tuple[str, str]]:
    """词表里机关的泰文名(含别名)→ id,长名在前:「สำนักงานคณะกรรมการ…」不会被它包含的短名抢先。"""
    return rules_from_names({a["id"]: [a.get("th") or "", *(a.get("th_aliases") or [])] for a in v["agencies"]})


def rules_from_names(names: dict[str, list[str]]) -> list[tuple[str, str]]:
    rules = {(norm(n), aid) for aid, ns in names.items() for n in ns if len(norm(n)) >= MIN_NAME}
    return sorted(rules, key=lambda r: (-len(r[0]), r[0], r[1]))


def _match(s: str, rules: list[tuple[str, str]]) -> tuple[str, int] | None:
    """s 开头就是哪个机关(长名优先):(id, 名称长度)。"""
    for name, aid in rules:
        if s.startswith(name):
            return aid, len(name)
    return None


def _issuer_start(s: str) -> int | None:
    """标题里发文机关段从第几个字符开始;没有发文机关段(部令、皇家法令)返回 None。"""
    if s.startswith(NO_ISSUER_PREFIXES):
        return None
    pos = 0
    for t in DOC_TYPES:
        if s.startswith(t):
            pos = len(t)
            break
    if s.startswith("ของ", pos):
        pos += len("ของ")
    for t in TITLES:
        if s.startswith(t, pos):
            pos += len(t)
            break
    return pos


def _parse(title_th: str, rules: list[tuple[str, str]]) -> tuple[list[str], str]:
    """(认出的发文机关 id 列表, 发文机关段)。发文机关段 = 第一个不属于机关名的「เรื่อง / ว่าด้วย」之前的文字。"""
    s = norm(title_th)
    start = _issuer_start(s)
    ids: list[str] = []
    end = 0
    if start is not None:
        pos = start
        while True:
            m = _match(s[pos:], rules)
            if not m:
                break
            if m[0] not in ids:
                ids.append(m[0])
            pos = end = pos + m[1]
            if not s.startswith(JOINT, pos):
                break
            pos += len(JOINT)
    cut = CUT_RE.search(s, end)
    return ids, (s[:cut.start()] if cut else s)


def issuer_agencies(title_th: str, rules: list[tuple[str, str]]) -> list[str]:
    """泰文标题写明的发文机关(联合发文时按标题顺序列出全部);认不出返回空列表。"""
    return _parse(title_th, rules)[0]


def issuer_head(title_th: str, rules: list[tuple[str, str]]) -> str:
    """发文机关段(已去空白)。空串 = 标题里没有发文机关段可供印证(没有泰文原题,或以「เรื่อง」开头)。"""
    return _parse(title_th, rules)[1]
