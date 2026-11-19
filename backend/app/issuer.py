# -*- coding: utf-8 -*-
"""从泰文标题认出发文机关 —— 数据层(app.enrich.fix_agency、app.collect 采集入库)与页面层
(app.analytics.attribution → 落地页、首页卡片、详情视图、llms-full.txt)共用这一套判断。

公报标题的写法是「文件类型 + 发文机关 + เรื่อง/ว่าด้วย + 事由」:
    ประกาศกรมสรรพากร เรื่อง …                     → 税务厅
    คำสั่งคณะกรรมการว่าด้วยความปลอดภัยของสินค้าและบริการ ที่ 2/2569 เรื่อง …  → 商品与服务安全委员会
    ข้อบังคับของคณะกรรมการการบินพลเรือน ฉบับที่ 105 ว่าด้วย …                  → 民用航空委员会
    ประกาศสำนักนายกรัฐมนตรีและกระทรวงมหาดไทย เรื่อง …                          → 总理府 + 内政部(联合发文)

原则是「宁可认不出,不要认错」:
- 机关名必须紧跟在文件类型之后(中间只允许「ของ」和 อธิบดี / ผู้ว่าการ / ผู้อำนวยการ 这几个署名职务;
  总理、内阁不接受署名职务前缀 —— 「เลขาธิการนายกรัฐมนตรี」「เลขาธิการคณะรัฐมนตรี」是各自的秘书处)。
  没有文件类型时,标题开头就是机关名也认(公报的更正启事「สำนักงาน… ขอแก้ไขข้อความคลาดเคลื่อน」),
  内阁决议数据不适用(allow_bare=False)。
- 机关名之后必须是边界:结束、空白、เรื่อง、ว่าด้วย、ที่、ฉบับ、括号、และ。「คณะกรรมการการเลือกตั้งประจำ
  องค์การบริหารส่วนตำบล…」(地方选举委员会)不会被认成选举委员会。需要吞后缀的名字(各府土地办公室
  「สำนักงานที่ดินจังหวัด…」、府级委员会)在词表里显式标为前缀式别名(`"prefix": true`)。
- 名字里本身含「ว่าด้วย」的委员会按整个名字认,不在「ว่าด้วย」处截断。
- 部令、皇家法令、法律的标题没有发文机关段,后面出现的机关名是事由的一部分,一律认不出。
- 联合发文「A และ B」全部列出;「และ」后面认不出,或「A B และ C」这样不带「และ」的并列,整条认不出
  (不把 agency_ids 覆盖成不完整的一家)。「A + A 的上级部委」是署名写法,只取 A。
- 匹配前统一写法:去空白与零宽字符、「ํา」并回「ำ」(含中间夹声调符的「นํ้า」)、「เเ」并成「แ」、
  声调符与上 / 下元音的顺序。

词表别名(`th_aliases`)的写法:
- 字符串:同一实体的另一种写法,页面上显示机关本身的中文名。
- {"th": …, "zh": …}:附属于该机关、但不是同一个实体的名字(委员会的办公室、厅里的登记处……)。
  数据层归到该机关;页面上标题写的是它时,显示它自己的中文名 —— 页面上显示的机关名必须与标题写的是同一个实体。
- {"th": …, "prefix": true}:前缀式别名(各府 / 分支机构),后面可以接府名、分局名。数据层归到上级机关;
  页面上不算「标题印证的发文者」(标题写的是某府的办公室,不是上级机关本身),机关栏标「相关机关」。
- {"th": …, "official": true}:官员职务称谓(破产财产管理人、交警长官)。数据层归到所属机关;
  页面上同样只算「相关机关」—— 「法律执行厅发布《破产管理人公告》」是推断,不是标题所写。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# 标题以这些开头的没有发文机关段
NO_ISSUER_PREFIXES = ("กฎกระทรวง", "พระราชกฤษฎีกา", "พระราชบัญญัติ", "พระราชกำหนด", "ประมวลกฎหมาย",
                      "รัฐธรรมนูญ")
# 文件类型(长的在前)
DOC_TYPES = ("เทศบัญญัติ", "ข้อบัญญัติ", "ข้อบังคับ", "ข้อกำหนด", "คำวินิจฉัย", "คำแนะนำ", "ประกาศ", "คำสั่ง",
             "ระเบียบ", "กฎ")
# 文件类型和机关名之间允许出现的署名职务:厅长、总裁(央行、电力局)、局长
TITLES = ("อธิบดี", "ผู้ว่าการ", "ผู้อำนวยการ")
NO_TITLE_PREFIX = frozenset({"pm", "cabinet"})
JOINT = "และ"
# 机关名之后允许的边界(空白另算)
BOUNDARY = ("เรื่อง", "ว่าด้วย", "ที่", "ฉบับ", "(", "\uff08", JOINT)
CUT_RE = re.compile(r"เรื่อง|ว่าด้วย")
MIN_NAME = 4                                   # 4 个字符以下的缩写不用

_SPACE_RE = re.compile(r"[\s\u200b\u200c\u200d\u2060\ufeff]+")
_TONE = "\u0e48-\u0e4b"
_ABOVE = "\u0e31\u0e34-\u0e37\u0e47"
_BELOW = "\u0e38-\u0e3a"


def _thai(text: str) -> str:
    """不涉及空白的写法统一。"""
    t = str(text or "")
    t = t.replace("\u0e40\u0e40", "\u0e41")                                   # เเ → แ
    t = re.sub(f"([{_TONE}])([{_ABOVE}{_BELOW}])", r"\2\1", t)                  # 声调符在元音之后
    t = re.sub(f"\u0e4d([{_TONE}]?)\u0e32", "\\1\u0e33", t)                      # ํา / ํ้า → ำ / ้ำ
    t = re.sub(f"([{_TONE}])\u0e4d\u0e32", "\\1\u0e33", t)
    return t


def norm(text: str) -> str:
    return _SPACE_RE.sub("", _thai(text))


def _norm_with_spaces(text: str) -> tuple[str, set[int]]:
    """(去空白后的文字, 原文在哪些位置之前有空白)。边界检查要知道机关名后面是不是空白。"""
    out, spaces = [], set()
    for part in _SPACE_RE.split(_thai(text).strip()):
        if out:
            spaces.add(sum(map(len, out)))
        out.append(part)
    s = "".join(out)
    spaces.add(len(s))
    return s, spaces


@dataclass(frozen=True)
class Rule:
    name: str              # 已归一
    aid: str
    prefix: bool = False   # 前缀式别名:后面可以接任何后缀
    official: bool = False  # 官员职务称谓
    zh: str = ""           # 附属实体自己的中文显示名

    @property
    def confirms(self) -> bool:
        """页面上能不能算「标题印证的发文者」。"""
        return not (self.prefix or self.official)


def alias_entries(a: dict) -> list[dict]:
    """一个机关的全部名称(正式名 + 别名),统一成 {"th", "prefix", "official", "zh"}。"""
    out = [{"th": a.get("th") or ""}]
    for x in a.get("th_aliases") or []:
        out.append({"th": x} if isinstance(x, str) else dict(x))
    return out


def agency_rules(v: dict) -> list[Rule]:
    """词表里机关的泰文名(含别名)→ 规则,长名在前:「สำนักงานคณะกรรมการ…」不会被它包含的短名抢先。"""
    rules = set()
    for a in v["agencies"]:
        for x in alias_entries(a):
            n = norm(x["th"])
            if len(n) >= MIN_NAME:
                rules.add(Rule(n, a["id"], bool(x.get("prefix")), bool(x.get("official")), x.get("zh") or ""))
    return sorted(rules, key=lambda r: (-len(r.name), r.name, r.aid))


@lru_cache(maxsize=4)
def _rules_for(path: str, mtime: float) -> tuple[list[Rule], dict[str, str | None]]:
    v = json.loads(Path(path).read_text(encoding="utf-8"))
    return agency_rules(v), {a["id"]: a.get("ministry") for a in v["agencies"]}


def vocab_rules(path: Path) -> tuple[list[Rule], dict[str, str | None]]:
    """(规则, {id: 上级 id}),按文件修改时间缓存。"""
    return _rules_for(str(path), path.stat().st_mtime)


@dataclass(frozen=True)
class Match:
    rule: Rule
    start: int
    end: int


def _match(s: str, spaces: set[int], pos: int, rules: list[Rule], titled: bool = False) -> Match | None:
    """s[pos:] 开头是哪个机关(长名优先,机关名之后须是边界)。"""
    for r in rules:
        if not s.startswith(r.name, pos) or (titled and r.aid in NO_TITLE_PREFIX):
            continue
        end = pos + len(r.name)
        if r.prefix or end in spaces or s.startswith(BOUNDARY, end):
            return Match(r, pos, end)
    return None


def _start(s: str, allow_bare: bool) -> tuple[int, bool] | None:
    """(发文机关段从第几个字符开始, 是否带署名职务);没有发文机关段返回 None。"""
    if s.startswith(NO_ISSUER_PREFIXES):
        return None
    pos = next((len(t) for t in DOC_TYPES if s.startswith(t)), 0)
    if pos == 0 and not allow_bare:
        return None
    if s.startswith("ของ", pos):
        pos += len("ของ")
    for t in TITLES:
        if s.startswith(t, pos):
            return pos + len(t), True
    return pos, False


def _ancestors(aid: str, parents: dict[str, str | None]) -> set[str]:
    out, cur = set(), parents.get(aid)
    while cur and cur not in out:
        out.add(cur)
        cur = parents.get(cur)
    return out


def parse(title_th: str, rules: list[Rule], parents: dict[str, str | None] | None = None,
          allow_bare: bool = True) -> tuple[list[Match], str]:
    """(认出的发文机关,按标题顺序;发文机关段)。发文机关段 = 第一个不属于机关名的「เรื่อง / ว่าด้วย」之前的文字。"""
    s, spaces = _norm_with_spaces(title_th)
    parents = parents or {}
    found: list[Match] = []
    st = _start(s, allow_bare)
    if st is not None:
        m = _match(s, spaces, st[0], rules, titled=st[1])
        while m:
            found.append(m)
            end = m.end
            if m.rule.prefix:
                break
            if s.startswith(JOINT, end):
                m = _match(s, spaces, end + len(JOINT), rules)
                if not m:
                    found = []          # 「และ」后面认不出:联合发文不完整,整条认不出
                continue
            nxt = _match(s, spaces, end, rules) if end in spaces and end < len(s) else None
            if nxt and nxt.rule.aid in _ancestors(m.rule.aid, parents):
                # 「กรมสรรพากร กระทรวงการคลัง」:署名带上级部委,只取发文的厅局
                found[-1] = Match(m.rule, m.start, nxt.end)
                if s.startswith(JOINT, nxt.end):
                    m = _match(s, spaces, nxt.end + len(JOINT), rules)
                    if not m:
                        found = []
                    continue
                break
            if nxt:
                found = []              # 「A B …」不带「และ」的并列:说不清是谁发的
            break
    end = found[-1].end if found else 0
    cut = CUT_RE.search(s, end)
    return found, (s[:cut.start()] if cut else s)


def issuer_agencies(title_th: str, rules: list[Rule], parents: dict[str, str | None] | None = None,
                    allow_bare: bool = True) -> list[str]:
    """泰文标题写明的发文机关 id(联合发文时按标题顺序列出全部);认不出返回空列表。"""
    out: list[str] = []
    for m in parse(title_th, rules, parents, allow_bare)[0]:
        if m.rule.aid not in out:
            out.append(m.rule.aid)
    return out


def issuer_head(title_th: str, rules: list[Rule]) -> str:
    """发文机关段(已去空白)。空串 = 标题里没有发文机关段可供印证(没有泰文原题,或以「เรื่อง」开头)。"""
    return parse(title_th, rules)[1]


def has_issuer_segment(title_th: str) -> bool:
    """标题的文件类型带不带发文机关段:部令、皇家法令、法律不带。"""
    return not norm(title_th).startswith(NO_ISSUER_PREFIXES)


ISSUER, RELATED = "发文机关", "相关机关"


def attribute(title_th: str, ids: list[str], zh: dict[str, str], rules: list[Rule],
              parents: dict[str, str | None] | None = None, *, verified: bool = False, gazette: bool = False,
              cabinet_resolution: bool = False, uid_agency: str = "") -> tuple[str, list[str], list[str]]:
    """机关栏:(标签, 发文机关的中文名列表, 相关机关的中文名列表)。标签为空串 = 整栏不显示。

    - 标题写明的发文机关(且是同一实体:前缀式别名、职务称谓不算)是该条目的机关之一:这几个按标题顺序
      写成发文机关(附属实体用它自己的中文名),其余的机关另列为相关机关。
    - 人工复核过的:全部照旧算发文机关。
    - 内阁决议:第一个机关是内阁才算(只有内阁算发文者)。
    - 公报条目没有泰文原题可供印证(人工整理的条目):第一个机关算发文者。
    - 官网来源:第一个机关就是这个官网的机关(uid 的第二段),且标题的文件类型带发文机关段
      (官网转载的皇家法令、部令不是这个官网的机关发的)。
    - 印证不了:全部列为相关机关;只有一个缺省的「内阁」时整栏不显示。"""
    if not ids:
        return ISSUER, [], []
    name = lambda aids: [zh.get(a, a) for a in aids]  # noqa: E731
    if verified:
        return ISSUER, name(ids), []
    found, head = parse(title_th, rules, parents, allow_bare=not cabinet_resolution)
    hits = [m for m in found if m.rule.confirms and m.rule.aid in ids]
    if hits:
        issuers, seen = [], []
        for m in hits:
            if m.rule.aid not in seen:
                seen.append(m.rule.aid)
                issuers.append(m.rule.zh or zh.get(m.rule.aid, m.rule.aid))
        return ISSUER, issuers, name([a for a in ids if a not in seen])
    if cabinet_resolution:
        ok = ids[0] == "cabinet"
    elif gazette:
        ok = not head
    else:
        ok = (ids[0] == uid_agency and has_issuer_segment(title_th)) or (not head and ids[0] != "cabinet")
    if ok:
        return ISSUER, name(ids[:1]), name(ids[1:])
    return ("", [], []) if ids == ["cabinet"] else (RELATED, [], name(ids))


def title_issuers(title_th: str, vocab_path: Path) -> list[str]:
    """采集入库时用:按词表文件认标题的发文机关(与 app.enrich.fix_agency 同一口径,入库即是它的不动点)。"""
    try:
        rules, parents = vocab_rules(vocab_path)
    except (OSError, ValueError):
        return []
    return issuer_agencies(title_th, rules, parents)
