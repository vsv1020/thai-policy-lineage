# -*- coding: utf-8 -*-
"""全部聚合分析:首页、趋势看板、政策维度七维。

原则:**每个结果都带 `n` 和 `sufficient`**。样本不够时前端显示「数据不足」而不是画一张
看起来很确定的图 —— 这是整个项目「可溯源」承诺的一部分,不是可选的礼貌。
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from .config import BKK, CONF_WEIGHT, settings
from .ingest import split_summary
from .models import (Agency, Conflict, Deadline, Document, DocumentAgency, DocumentDomain,
                     DocumentGoal, DocumentInstrument, DocumentParty, Domain, Goal,
                     ImplementationStage, Instrument, InstrumentClass, Issue, LegalForm,
                     Party, SourceHealth, Status)

DIR_SIGN = {"tight": -1, "loose": 1, "neutral": 0}

# 各维度认为「算得出结论」的最小样本量。低于此只出数字、不出结论。
MIN_N = {"instruments": 12, "goals": 12, "legal_forms": 20, "parties": 10,
         "coop": 8, "stages": 12}


def _today(s: Session) -> date:
    """「今天」取最近一次采集时间,没有则取系统时间。让分析结果与数据快照同步。"""
    last = s.scalar(select(func.max(SourceHealth.last_attempt_at)))
    if last:
        return (last.astimezone(BKK) if last.tzinfo else last.replace(tzinfo=BKK)).date()
    return datetime.now(BKK).date()


def _months(n: int, today: date) -> list[str]:
    y, m, out = today.year, today.month, []
    for _ in range(n):
        out.append(f"{y % 100:02d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _mk(d: date) -> str:
    return f"{d.year % 100:02d}-{d.month:02d}"


def iso_bkk(dt: datetime | None) -> str | None:
    """SQLite 不保存时区,读回来是 naive 的。一律按曼谷时间补回时区再序列化 ——
    否则前端把它当 UTC 解析,「数据更新时间」会整整偏 7 小时。"""
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=BKK)).replace(microsecond=0).isoformat()


# ─────────────────────── 首页 ───────────────────────

def document_view(s: Session, doc: Document, today: date) -> dict:
    domains = sorted(doc.domains, key=lambda x: x.seq)
    agencies = sorted(doc.agencies, key=lambda x: x.seq)
    dom = s.get(Domain, domains[0].domain_id) if domains else None

    def org_name(aid: str) -> str:
        a = s.get(Agency, aid)
        abbr = (a.abbr or "").replace("-", "")
        return f"{a.zh} ({a.abbr})" if abbr.isascii() and abbr.isalpha() else a.zh

    lf, st = doc.legal_form, doc.status
    if doc.effective_from:
        eff = "已生效" if doc.effective_from <= today else f"生效 {doc.effective_from.isoformat()}"
    elif doc.status_id == "pending_gazette":
        eff = "待刊公报后生效"
    elif doc.comment_deadline:
        eff = f"意见截止 {doc.comment_deadline.isoformat()}"
    else:
        eff = st.zh

    status_label = st.zh
    if doc.status_id == "gazetted" and doc.effective_from and doc.effective_from > today:
        status_label = f"{doc.effective_from.isoformat()[5:]} 起施行"

    official = next((x.url for x in doc.sources if x.role == "official" and x.url), "")
    return {
        "uid": doc.uid,
        "issue_id": doc.issue_id,
        "date": doc.display_date.isoformat() if doc.display_date else "",
        "domain": dom.chip if dom else "",
        "domain_label": dom.zh if dom else "",
        "direction": doc.direction,
        "title_zh": doc.title_zh,
        "title_th": doc.title_th,
        "summary_zh": split_summary(doc.summary_zh)[0],
        "key_points": split_summary(doc.summary_zh)[1],
        "org": " · ".join(org_name(a.agency_id) for a in agencies),
        "doc_no": doc.doc_no,
        "doc_no_label": "公报" if doc.gazette_series else "文号",
        "legal_form": f"{lf.zh} · {lf.abbr} 层级",
        "stability": lf.stability,
        "effective_label": eff,
        "status": {"in_force": "active", "gazetted": "soon"}.get(doc.status_id, "draft"),
        "status_label": status_label,
        "source_url": official,
        "verified": doc.verified,
        "detail_ready": doc.has_detail_page,
        "provenance": doc.pipeline,
        # 四类日期与可信度也带在列表里 —— 静态导出没有单件接口,
        # 带上它们前端在降级模式下也能画出生命周期时间线并标注可信度
        "dates": {
            "resolved_at": doc.resolved_at.isoformat() if doc.resolved_at else None,
            "published_at": doc.published_at.isoformat() if doc.published_at else None,
            "effective_from": doc.effective_from.isoformat() if doc.effective_from else None,
            "effective_to": doc.effective_to.isoformat() if doc.effective_to else None,
            "comment_deadline": (doc.comment_deadline.isoformat()
                                 if doc.comment_deadline else None),
        },
        "confidence": {"dates": doc.confidence_dates, "doc_no": doc.confidence_doc_no},
        # 影响对象(卡片与「找政策」的筛选用)。按 party_id 排序:自增主键在增量入库与
        # 全新建库时顺序可能不同,用它排序会让导出漂移
        "parties": [{"id": x.party_id, "party_id": x.party_id, "stance": x.stance,
                     "label": (p.zh if (p := s.get(Party, x.party_id)) else x.party_id)}
                    for x in sorted(doc.parties, key=lambda x: x.party_id)],
    }


def wind_now(s: Session, today: date) -> list[dict]:
    """近 90 天按领域的风向指数,加权 + 收缩。"""
    cutoff = today - timedelta(days=90)
    rows = s.execute(
        select(Domain.chip, Domain.zh, Document.direction, Document.direction_confidence)
        .join(DocumentDomain, DocumentDomain.domain_id == Domain.id)
        .join(Document, Document.uid == DocumentDomain.uid)
        .where(Document.display_date.is_not(None), Document.display_date >= cutoff)
    ).all()
    num, den, cnt, labels = defaultdict(float), defaultdict(float), defaultdict(int), {}
    for chip, zh, direction, conf in rows:
        w = CONF_WEIGHT.get(conf, 0.2)
        num[chip] += DIR_SIGN.get(direction, 0) * w
        den[chip] += w
        cnt[chip] += 1
        labels[chip] = zh
    out = []
    for chip in sorted(den, key=lambda k: -cnt[k]):
        score = round(num[chip] / (den[chip] + settings.wind_shrink), 2)
        out.append({"domain": chip, "label": labels[chip], "score": score, "n": cnt[chip],
                    "direction": "loose" if score > 0.15 else ("tight" if score < -0.15 else "neutral")})
    return out


def _next_occurrence(rec: dict, today: date) -> str | None:
    if rec.get("type") == "once":
        return rec.get("date")
    if rec.get("type") == "yearly":
        for year in (today.year, today.year + 1):
            try:
                cand = date(year, rec["month"], rec["day"])
            except ValueError:
                continue
            if cand >= today:
                return cand.isoformat()
    return None


def calendar(s: Session, today: date) -> list[dict]:
    horizon = today + timedelta(days=settings.calendar_days)
    items: list[dict] = []
    for doc in s.scalars(select(Document)).all():
        for value, verb in ((doc.effective_from, "生效"), (doc.comment_deadline, "意见截止")):
            if value and today <= value <= horizon:
                items.append({"date": value.isoformat(), "text": f"{doc.title_zh[:34]} · {verb}",
                              "uid": doc.uid, "kind": "document"})
    for dl in s.scalars(select(Deadline)).all():
        val = _next_occurrence(json.loads(dl.recurrence_json or "{}"), today)
        if val and today.isoformat() <= val <= horizon.isoformat():
            items.append({"date": val, "text": dl.title_zh, "uid": None, "kind": "deadline"})
    return sorted(items, key=lambda x: x["date"])


# 上次成功距今超过这么多天,即使状态写着 ok 也按「过期」算 ——
# 一个 6 周前成功过、此后再没跑过的源,不能在页面上显示为「可用」
SOURCE_STALE_DAYS = 3


def source_health(s: Session) -> tuple[str | None, list[dict]]:
    rows = s.scalars(select(SourceHealth)).all()
    last = max((r.last_attempt_at for r in rows if r.last_attempt_at), default=None)
    today = _today(s)
    out = []
    for r in rows:
        status = r.status
        if status == "ok" and r.last_ok_at is not None:
            ok_day = (r.last_ok_at if r.last_ok_at.tzinfo else r.last_ok_at.replace(tzinfo=BKK))
            if (today - ok_day.astimezone(BKK).date()).days > SOURCE_STALE_DAYS:
                status = "stale"
        out.append({"id": r.id, "name": r.name, "url": r.url, "status": status,
                    "last_ok": iso_bkk(r.last_ok_at), "detail": r.detail})
    return iso_bkk(last), out


def _neg_date(d: str) -> str:
    """把 YYYY-MM-DD 变成可升序排列的「倒序键」;空日期排最后。"""
    return "".join(chr(ord("9") - int(c) + ord("0")) if c.isdigit() else c for c in d) if d else "~"


def overview(s: Session) -> dict:
    today = _today(s)
    docs = s.scalars(select(Document).order_by(Document.display_date.desc().nullslast(),
                                               Document.uid)).all()
    views = [document_view(s, d, today) for d in docs]
    # 首页排序:读过原文、有要点的排前面;同组内日期倒序,再按 uid —— 导出必须确定
    views.sort(key=lambda v: (not v["key_points"], _neg_date(v["date"]), v["uid"]))
    # 首页精选:同一发文机关最多 2 条,超出的顺延给后面的条目,避免一家机关刷屏;
    # policies 数组本身的顺序不变
    per_org: dict[str, int] = defaultdict(int)
    picked = 0
    for v in views:
        v["featured"] = False
        if picked < settings.feed_size and per_org[v["org"]] < 2:
            v["featured"] = True
            per_org[v["org"]] += 1
            picked += 1
    last_run, _ = source_health(s)
    dates = sorted(v["date"] for v in views if v["date"] and v["date"] <= today.isoformat())
    by_domain: dict[str, dict] = {}
    for v in views:
        key = v["domain"] or "other"
        e = by_domain.setdefault(key, {"id": key, "zh": v["domain_label"] or "其他", "n": 0})
        e["n"] += 1
    return {
        "schema_version": 4,
        "updated_at": last_run or datetime.now(BKK).replace(microsecond=0).isoformat(),
        "stats": {"total": len(views),
                  "research": sum(1 for v in views if v["provenance"] == "research"),
                  "demo": sum(1 for v in views if v["provenance"] == "demo"),
                  # 首页「数据覆盖」:有要点的条数、公报日期范围(到数据截止日为止)、各领域条数
                  "with_points": sum(1 for v in views if v["key_points"]),
                  "date_from": dates[0] if dates else None,
                  "date_to": dates[-1] if dates else None,
                  "by_domain": sorted(by_domain.values(), key=lambda e: (-e["n"], e["id"]))},
        "wind": wind_now(s, today),
        "calendar": calendar(s, today),
        "policies": views,
    }


# ─────────────────────── 趋势看板 ───────────────────────

def trends(s: Session) -> dict:
    today = _today(s)
    # 时间窗以「数据实际截止的月份」为终点,而不是今天:官方公报数据集滞后数月,
    # 以今天为终点会在最近几个月画出一段假的「断崖」
    latest = s.scalar(select(func.max(Document.display_date)).where(Document.display_date <= today))
    anchor = latest or today
    months = _months(settings.trend_months, anchor)
    mset = set(months)

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    wnum: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wden: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    labels: dict[str, str] = {}
    covered: set[str] = set()

    for did, zh, dd, direction, conf in s.execute(
        select(Domain.id, Domain.zh, Document.display_date, Document.direction,
               Document.direction_confidence)
        .join(DocumentDomain, DocumentDomain.domain_id == Domain.id)
        .join(Document, Document.uid == DocumentDomain.uid)
        .where(Document.display_date.is_not(None))
    ).all():
        mk = _mk(dd)
        if mk not in mset:
            continue
        covered.add(mk)
        labels[did] = zh
        w = CONF_WEIGHT.get(conf, 0.2)
        counts[did][mk] += 1
        wnum[did][mk] += DIR_SIGN.get(direction, 0) * w
        wden[did][mk] += w

    org: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    org_labels: dict[str, str] = {}
    for aid, zh, dd in s.execute(
        select(Agency.id, Agency.zh, Document.display_date)
        .join(DocumentAgency, DocumentAgency.agency_id == Agency.id)
        .join(Document, Document.uid == DocumentAgency.uid)
        .where(Document.display_date.is_not(None))
    ).all():
        mk = _mk(dd)
        if mk in mset:
            org[aid][mk] += 1
            org_labels[aid] = zh

    def series(store, lbl):
        return [{"id": k, "label": lbl[k], "data": [store[k].get(m, 0) for m in months]}
                for k in store if any(store[k].get(m) for m in months)]

    wind = []
    for did in wnum:
        pts = [round(wnum[did][m] / (wden[did][m] + settings.wind_shrink), 2)
               if wden[did].get(m) else None for m in months]
        if any(p is not None for p in pts):
            wind.append({"id": did, "label": labels[did], "data": pts})

    gazette_through = s.scalar(select(func.max(Document.published_at))
                               .where(Document.pipeline == "gazette_json"))
    return {"months": months, "months_covered": len(covered),
            "usable": len(covered) >= settings.min_trend_months,
            "min_months_required": settings.min_trend_months,
            "data_through": anchor.isoformat()[:7],
            "gazette_through": gazette_through.isoformat()[:7] if gazette_through else None,
            "total_documents": s.scalar(select(func.count(Document.uid))),
            "volume_by_domain": series(counts, labels),
            "wind_by_domain": wind,
            "activity_by_agency": series(org, org_labels),
            "rising": rising_topics(s, anchor)}


RISING_WINDOW_DAYS = 90


def rising_topics(s: Session, anchor: date, top: int = 8) -> list[dict]:
    """上升话题:领域 / 政策工具 / 政策目标标签,在最近 90 天与前 90 天各被多少份文件提及,按增幅排序。
    以数据截止日为基准(不是今天),否则官方数据集的发布滞后会让所有话题都显示为下降。"""
    cur_from = anchor - timedelta(days=RISING_WINDOW_DAYS)
    prev_from = cur_from - timedelta(days=RISING_WINDOW_DAYS)
    cur: dict[str, int] = defaultdict(int)
    prev: dict[str, int] = defaultdict(int)
    for link, vocab, col in ((DocumentDomain, Domain, DocumentDomain.domain_id),
                             (DocumentInstrument, Instrument, DocumentInstrument.instrument_id),
                             (DocumentGoal, Goal, DocumentGoal.goal_id)):
        for zh, dd in s.execute(
                select(vocab.zh, Document.display_date)
                .join(link, col == vocab.id).join(Document, Document.uid == link.uid)
                .where(Document.display_date > prev_from, Document.display_date <= anchor)).all():
            (cur if dd > cur_from else prev)[zh] += 1
    rows = []
    for label, n in cur.items():
        if n < 2:                          # 只被一份文件提到,谈不上「上升」
            continue
        p = prev.get(label, 0)
        rows.append({"label": label, "current": n, "previous": p,
                     "growth_pct": round((n - p) / p * 100) if p else None})
    # 前 90 天为 0 的「新出现」话题排最前,其余按增幅,再按提及次数
    rows.sort(key=lambda r: (r["growth_pct"] is None, r["growth_pct"] or 0, r["current"]), reverse=True)
    return [r for r in rows if r["growth_pct"] is None or r["growth_pct"] > 0][:top]


# ─────────────────────── 政策维度 七维 ───────────────────────

def _sufficient(key: str, n: int) -> dict:
    need = MIN_N[key]
    return {"n": n, "sufficient": n >= need, "min_n": need}


def dim1_instrument_structure(s: Session) -> dict:
    """维度一:政策工具结构随时间演变(按类别分组,行=工具,列=年)。"""
    rows = s.execute(
        select(InstrumentClass.id, InstrumentClass.zh, InstrumentClass.desc,
               InstrumentClass.color, Instrument.id, Instrument.zh, Document.display_date)
        .join(Instrument, Instrument.class_id == InstrumentClass.id)
        .join(DocumentInstrument, DocumentInstrument.instrument_id == Instrument.id)
        .join(Document, Document.uid == DocumentInstrument.uid)
        .where(Document.display_date.is_not(None))
    ).all()
    seen_years = {r[6].year for r in rows}
    # 年份要连续 —— 中间「没有任何文件的那一年」本身就是信号,不能被压缩掉
    years = list(range(min(seen_years), max(seen_years) + 1)) if seen_years else []
    cells: dict[tuple[str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    meta: dict[str, dict] = {}
    inst_zh: dict[str, str] = {}
    class_total: dict[str, int] = defaultdict(int)
    for cid, czh, cdesc, ccolor, iid, izh, dd in rows:
        meta[cid] = {"id": cid, "zh": czh, "desc": cdesc, "color": ccolor}
        inst_zh[iid] = izh
        cells[(cid, iid)][dd.year] += 1
        class_total[cid] += 1
    total = sum(class_total.values()) or 1

    groups = []
    for cid in sorted(meta, key=lambda c: -class_total[c]):
        rows_out = [{"id": iid, "label": inst_zh[iid],
                     "data": [cells[(c, iid)].get(y, 0) for y in years]}
                    for (c, iid) in sorted(cells) if c == cid]
        groups.append({**meta[cid], "share": round(class_total[cid] / total * 100),
                       "count": class_total[cid], "rows": rows_out})
    return {"years": [str(y) for y in years],
            "years_be": [f"{y + 543}/{y % 100:02d}" for y in years],
            "groups": groups, **_sufficient("instruments", total)}


def dim2_instrument_x_goal(s: Session) -> dict:
    """维度二:工具类别 × 政策目标;计数为 0 的格子是政策空白。"""
    rows = s.execute(
        select(InstrumentClass.id, InstrumentClass.zh, InstrumentClass.color,
               Goal.id, Goal.zh, func.count(func.distinct(Document.uid)))
        .join(Instrument, Instrument.class_id == InstrumentClass.id)
        .join(DocumentInstrument, DocumentInstrument.instrument_id == Instrument.id)
        .join(Document, Document.uid == DocumentInstrument.uid)
        .join(DocumentGoal, DocumentGoal.uid == Document.uid)
        .join(Goal, Goal.id == DocumentGoal.goal_id)
        .group_by(InstrumentClass.id, InstrumentClass.zh, InstrumentClass.color, Goal.id, Goal.zh)
    ).all()
    # 只展示实际出现过的目标列,否则一屏全是空列
    goals = [{"id": g, "label": z} for g, z in
             sorted({(r[3], r[4]) for r in rows}, key=lambda x: x[0])]
    classes: dict[str, dict] = {}
    grid: dict[tuple[str, str], int] = {}
    for cid, czh, ccolor, gid, _gzh, n in rows:
        classes[cid] = {"id": cid, "label": czh, "color": ccolor}
        grid[(cid, gid)] = n
    matrix = [{**classes[cid], "data": [grid.get((cid, g["id"]), 0) for g in goals]}
              for cid in sorted(classes)]
    gaps = [{"class": classes[cid]["label"], "goal": g["label"]}
            for cid in sorted(classes) for g in goals if grid.get((cid, g["id"]), 0) == 0]
    total = sum(grid.values())
    return {"goals": goals, "matrix": matrix, "gaps": gaps, **_sufficient("goals", total)}


def dim3_legal_forms(s: Session) -> dict:
    """维度三:法律形式与强制力 —— 稳定性金字塔。"""
    rows = s.execute(
        select(LegalForm.id, LegalForm.zh, LegalForm.th, LegalForm.abbr, LegalForm.stability,
               LegalForm.justiciable, LegalForm.note, func.count(Document.uid))
        .outerjoin(Document, Document.legal_form_id == LegalForm.id)
        .group_by(LegalForm.id, LegalForm.zh, LegalForm.th, LegalForm.abbr,
                  LegalForm.stability, LegalForm.justiciable, LegalForm.note)
        .order_by(LegalForm.stability.desc(), func.count(Document.uid).desc())
    ).all()
    total = sum(r[7] for r in rows) or 1
    forms = [{"id": i, "zh": zh, "th": th, "abbr": abbr, "stability": stab,
              "justiciable": bool(just), "note": note, "count": n,
              "pct": round(n / total * 100)} for i, zh, th, abbr, stab, just, note, n in rows]
    fragile = sum(f["count"] for f in forms if f["stability"] <= 2)
    return {"forms": forms, "total": total,
            "fragile_pct": round(fragile / total * 100),
            "fragile_note": "承载在公告与内阁决议层的比例 —— 调整快、可诉性弱,"
                            "投资测算应按可撤回处理",
            **_sufficient("legal_forms", total)}


def dim4_affected_parties(s: Session) -> dict:
    """维度四:谁被支持、谁被约束。"""
    rows = s.execute(
        select(Party.id, Party.zh, DocumentParty.stance, func.count(DocumentParty.uid))
        .join(DocumentParty, DocumentParty.party_id == Party.id)
        .group_by(Party.id, Party.zh, DocumentParty.stance)
    ).all()
    agg: dict[str, dict] = {}
    for pid, zh, stance, n in rows:
        e = agg.setdefault(pid, {"id": pid, "label": zh, "support": 0, "constrain": 0, "neutral": 0})
        e[stance] = e.get(stance, 0) + n
    items = sorted(agg.values(), key=lambda e: -(e["support"] + e["constrain"]))
    total = sum(e["support"] + e["constrain"] + e["neutral"] for e in items)
    return {"items": items, "max": max((max(e["support"], e["constrain"]) for e in items),
                                       default=0), **_sufficient("parties", total)}


def dim5_agency_cooperation(s: Session) -> dict:
    """维度五:机构协同 —— 同一文件上并列署名的机关对。"""
    # 别名一律小写且互不相同 —— SQLite 的标识符比较不区分大小写,"a"/"A" 会撞车
    da1 = aliased(DocumentAgency, name="da1")
    da2 = aliased(DocumentAgency, name="da2")
    ag1 = aliased(Agency, name="ag1")
    ag2 = aliased(Agency, name="ag2")
    rows = s.execute(
        select(ag1.zh, ag2.zh, func.count().label("n"))
        .join(da2, (da1.uid == da2.uid) & (da1.agency_id < da2.agency_id))
        .join(ag1, ag1.id == da1.agency_id)
        .join(ag2, ag2.id == da2.agency_id)
        .select_from(da1)
        .group_by(ag1.zh, ag2.zh).order_by(func.count().desc())
    ).all()
    pairs = [{"a": x, "b": y, "n": n} for x, y, n in rows]
    solo = s.execute(
        select(func.count()).select_from(
            select(DocumentAgency.uid).group_by(DocumentAgency.uid)
            .having(func.count() == 1).subquery())
    ).scalar_one()
    return {"pairs": pairs, "max": max((p["n"] for p in pairs), default=0),
            "solo_documents": solo,
            "note": "联署少而各自单独规定同一事项,是维度六冲突的来源",
            **_sufficient("coop", sum(p["n"] for p in pairs))}


def dim6_conflicts(s: Session) -> dict:
    """维度六:一致性与冲突检测。"""
    order = {"high": 0, "med": 1, "low": 2}
    items = []
    visible = set(s.scalars(select(Document.uid)).all())
    for c in s.scalars(select(Conflict)).all():
        # 只展示所涉文件都已考证(在库里)的冲突;引用了未考证文件的冲突不上前台
        uids = [x.get("uid") for x in json.loads(c.sides_json or "[]") if x.get("uid")]
        if not uids or any(u not in visible for u in uids):
            continue
        items.append({"id": c.id, "severity": c.severity, "title_zh": c.title_zh,
                      "domains": c.domains_csv.split(",") if c.domains_csv else [],
                      "impact_zh": c.impact_zh, "detected_by": c.detected_by,
                      "confidence": c.confidence,
                      "sides": json.loads(c.sides_json or "[]")})
    items.sort(key=lambda x: order.get(x["severity"], 9))
    return {"items": items, "n": len(items),
            "by_severity": {k: sum(1 for i in items if i["severity"] == k)
                            for k in ("high", "med", "low")}}


def dim7_implementation(s: Session) -> dict:
    """维度七:执行完整度 —— 六环节各有多少文件,缺环即落地风险。"""
    rows = s.execute(
        select(ImplementationStage.id, ImplementationStage.zh, ImplementationStage.seq,
               func.count(Document.uid))
        .outerjoin(Document, Document.implementation_stage_id == ImplementationStage.id)
        .group_by(ImplementationStage.id, ImplementationStage.zh, ImplementationStage.seq)
        .order_by(ImplementationStage.seq)
    ).all()
    stages = [{"id": i, "label": zh, "seq": seq, "count": n} for i, zh, seq, n in rows]
    total = sum(x["count"] for x in stages)
    peak = max((x["count"] for x in stages), default=0)
    for x in stages:
        x["hot"] = peak > 0 and x["count"] == peak
        # 「缺环」= 明显低于峰值,说明链条在这里断了
        x["weak"] = peak > 0 and x["count"] <= max(1, peak * 0.15)
    missing = [x["label"] for x in stages if x["count"] == 0]
    return {"stages": stages, "total": total, "peak": peak, "missing": missing,
            **_sufficient("stages", total)}


def dimensions(s: Session) -> dict:
    return {
        "scope": "全库(尚未按议题/领域切片)",
        "dim1_instruments": dim1_instrument_structure(s),
        "dim2_instrument_goal": dim2_instrument_x_goal(s),
        "dim3_legal_forms": dim3_legal_forms(s),
        "dim4_parties": dim4_affected_parties(s),
        "dim5_cooperation": dim5_agency_cooperation(s),
        "dim6_conflicts": dim6_conflicts(s),
        "dim7_implementation": dim7_implementation(s),
    }


# ─────────────────────── 演进脉络 ───────────────────────

def lineage(s: Session) -> dict:
    docs = {d.uid: d for d in s.scalars(select(Document)).all()}
    out = []
    for it in s.scalars(select(Issue)).all():
        stages = []
        for st in json.loads(it.stages_json or "[]"):
            # 指向未考证文件(不在库里)的阶段不展示;没有指向具体文件的背景说明保留
            if st.get("uid") and st["uid"] not in docs:
                continue
            doc = docs.get(st.get("uid")) if st.get("uid") else None
            meta = ""
            if doc:
                meta = f"{doc.legal_form.abbr} 层级" + (f" · {doc.doc_no}" if doc.doc_no else "")
            stages.append({"stage": st["stage"],
                           "title": doc.title_zh if doc else st.get("label", ""),
                           "uid": st.get("uid"), "milestone": bool(st.get("milestone")),
                           "note": st.get("note", ""), "meta": meta})
        # 议题至少要有一份已考证的官方文件,才作为演进脉络展示
        if any(x["uid"] for x in stages):
            out.append({"issue_id": it.issue_id, "title_zh": it.title_zh,
                        "summary_zh": it.summary_zh, "watch": it.watch,
                        "domains": [s.get(Domain, d).zh for d in it.domains_csv.split(",")
                                    if d and s.get(Domain, d)],
                        "stages": stages})
    out.sort(key=lambda x: -len(x["stages"]))
    return {"issues": out}


# ─────────────────────── 采集运行状态(运维看板) ───────────────────────

def ops(s: Session) -> dict:
    """把自动化本身呈现出来:最近运行、源健康、翻译队列、数据新鲜度。

    这一页存在的理由:每日采集如果连续失败却没人看见,站点就会在「看起来正常」的
    状态下慢慢变旧。这里的每个数字都应该能让人一眼判断「管道是不是还活着」。
    """
    from .config import POLICIES_DIR
    from .ingest import read_jsonl
    from .models import CollectRun

    today = _today(s)
    last_run, sources = source_health(s)

    runs = s.scalars(select(CollectRun).order_by(CollectRun.started_at.desc()).limit(30)).all()
    run_items = [{"started_at": iso_bkk(r.started_at), "status": r.status, "trigger": r.trigger,
                  "added": r.added, "updated": r.updated,
                  "duration_s": round(r.duration_s or 0, 1)} for r in runs]
    # 连续失败天数:从最近一次往回数,直到遇到一次 ok/partial
    streak = 0
    for r in runs:
        if r.status == "failed":
            streak += 1
        else:
            break

    from .ingest import official_sources
    records = read_jsonl(POLICIES_DIR / "documents.jsonl")
    pending = [r for r in records if not (r.get("titles") or {}).get("zh")
               and not (r.get("flags") or {}).get("skip") and official_sources(r)]
    # 缺官方原文:不上前台、也不翻译,等补上 *.go.th 原文链接后自动恢复
    no_source = [r for r in records if not (r.get("flags") or {}).get("skip") and not official_sources(r)]
    skipped = [r for r in records if (r.get("flags") or {}).get("skip")]
    by_pipeline: dict[str, int] = defaultdict(int)
    for r in records:
        by_pipeline[(r.get("provenance") or {}).get("pipeline", "manual")] += 1

    presentable = s.scalar(select(func.count(Document.uid))) or 0
    verified = s.scalar(select(func.count(Document.uid)).where(Document.verified.is_(True))) or 0
    llm = s.scalar(select(func.count(Document.uid))
                   .where(Document.direction_method == "llm")) or 0
    from .models import DocumentSource
    with_official = s.scalar(
        select(func.count(func.distinct(DocumentSource.uid)))
        .where(DocumentSource.role == "official", DocumentSource.url != "")) or 0
    newest = s.scalar(select(func.max(Document.display_date)))

    ok_sources = [x for x in sources if x["status"] == "ok"]
    health = ("down" if sources and not ok_sources
              else "degraded" if len(ok_sources) < len(sources) else "ok")
    return {
        "as_of": last_run,
        "health": health,
        "failure_streak": streak,
        "sources": sources,
        "runs": run_items,
        "corpus": {
            "total_records": len(records),
            "presentable": presentable,
            "pending_translation": len(pending),
            "skipped_irrelevant": len(skipped),
            "verified": verified,
            "llm_enriched": llm,
            "with_official_link": with_official,
            "missing_official_source": len(no_source),
            "by_pipeline": dict(by_pipeline),
        },
        "freshness": {
            "newest_document": newest.isoformat() if newest else None,
            "days_since_newest": (today - newest).days if newest else None,
        },
        "queue_sample": [{"uid": r["uid"], "title_th": (r.get("titles") or {}).get("th", "")[:80]}
                         for r in pending[:10]],
        "missing_source": [{"uid": r["uid"],
                            "title": ((r.get("titles") or {}).get("zh") or (r.get("titles") or {}).get("th", ""))[:80],
                            "doc_no": r.get("doc_no", "")} for r in no_source[:50]],
    }


# ─────────────────────── 形态分析(政策形态画像)───────────────────────

TIER_LABEL = {5: "法律", 4: "皇家法令", 3: "部令", 2: "公告 / 规程", 1: "决议 / 指引"}
STATUS_ORDER = ["draft", "pending_gazette", "gazetted", "in_force", "superseded", "repealed", "expired"]
CLASS_ORDER = ["supply", "environment", "demand"]


def _ordered(items, order: list[str]):
    """按给定顺序排,不在列表里的按 id 排在后面 —— 顺序固定,导出可重复。"""
    return sorted(items, key=lambda x: (order.index(x.id) if x.id in order else len(order), x.id))


def _quarter(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _pct(n: int, total: int) -> float:
    return round(n / total * 100, 1) if total else 0.0


def morphology(s: Session) -> dict:
    """政策形态画像:每条政策按「法律层级 × 强制力 × 政策工具类型 × 生命周期状态」刻画,
    再看各领域的形态差异与随时间的演变。全部从库里聚合,解读文字也由数据生成。"""
    # 全部显式排序:导出必须可重复(CI 会比对派生文件),不能依赖数据库返回顺序
    docs = s.scalars(select(Document).order_by(Document.uid)).all()
    total = len(docs)
    forms = {f.id: f for f in s.scalars(select(LegalForm).order_by(LegalForm.id)).all()}
    statuses = _ordered(s.scalars(select(Status)).all(), STATUS_ORDER)
    domains = {d.id: d for d in s.scalars(select(Domain).order_by(Domain.id)).all()}
    instruments = {i.id: i for i in s.scalars(select(Instrument).order_by(Instrument.id)).all()}
    classes = {c.id: c for c in _ordered(s.scalars(select(InstrumentClass)).all(), CLASS_ORDER)}
    top = lambda counts: max(sorted(counts), key=lambda k: counts[k]) if counts else None  # noqa: E731

    def primary_domain(doc: Document) -> str | None:
        return min(doc.domains, key=lambda x: x.seq).domain_id if doc.domains else None

    form_n: dict[str, int] = defaultdict(int)
    status_n: dict[str, int] = defaultdict(int)
    class_n: dict[str, int] = defaultdict(int)
    instr_n: dict[str, int] = defaultdict(int)
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    prof: dict[str, dict] = defaultdict(lambda: {"n": 0, "stab": 0, "binding": 0, "forms": defaultdict(int),
                                                 "classes": defaultdict(int), "tight": 0, "loose": 0})
    evo: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    binding = in_force = high_tier = stab_sum = tight = loose = 0

    for d in docs:
        f = forms.get(d.legal_form_id)
        stab = f.stability if f else 1
        form_n[d.legal_form_id] += 1
        status_n[d.status_id] += 1
        stab_sum += stab
        binding += bool(f and f.justiciable)
        in_force += bool(d.status and d.status.in_force)
        high_tier += stab >= 4
        tight += d.direction == "tight"
        loose += d.direction == "loose"
        cls_here = {instruments[x.instrument_id].class_id for x in d.instruments if x.instrument_id in instruments}
        for c in cls_here:
            class_n[c] += 1
        for x in d.instruments:
            instr_n[x.instrument_id] += 1
        dom = primary_domain(d)
        if dom:
            matrix[dom][d.legal_form_id] += 1
            p = prof[dom]
            p["n"] += 1
            p["stab"] += stab
            p["binding"] += bool(f and f.justiciable)
            p["forms"][d.legal_form_id] += 1
            for c in cls_here:
                p["classes"][c] += 1
            p["tight"] += d.direction == "tight"
            p["loose"] += d.direction == "loose"
        if d.display_date:
            evo[_quarter(d.display_date)][stab] += 1

    form_rows = [{"id": fid, "zh": f.zh, "stability": f.stability, "justiciable": f.justiciable,
                  "n": form_n.get(fid, 0), "pct": _pct(form_n.get(fid, 0), total)}
                 for fid, f in sorted(forms.items(), key=lambda kv: (-kv[1].stability, kv[0]))]
    tiers = [{"stability": t, "label": TIER_LABEL[t],
              "n": sum(r["n"] for r in form_rows if r["stability"] == t),
              "pct": _pct(sum(r["n"] for r in form_rows if r["stability"] == t), total)}
             for t in sorted(TIER_LABEL, reverse=True)]
    used_forms = [r for r in form_rows if r["n"]]
    dom_order = sorted(matrix, key=lambda k: (-sum(matrix[k].values()), k))

    profiles = []
    for did in dom_order:
        p = prof[did]
        top_form = top(p["forms"])
        top_cls = top(p["classes"])
        profiles.append({
            "id": did, "zh": domains[did].zh if did in domains else did, "n": p["n"],
            "avg_stability": round(p["stab"] / p["n"], 2),
            "binding_pct": _pct(p["binding"], p["n"]),
            "dominant_form": forms[top_form].zh if top_form in forms else top_form,
            "dominant_form_pct": _pct(p["forms"][top_form], p["n"]),
            "dominant_class": classes[top_cls].zh if top_cls in classes else None,
            "tight": p["tight"], "loose": p["loose"]})

    # 连续的最近 8 个季度(以数据截止季度为终点),没有政策的季度记 0,图上不会把空档悄悄跳过
    quarters: list[str] = []
    if evo:
        y, q = (int(x) for x in max(evo).split("Q"))
        for _ in range(8):
            quarters.append(f"{y}Q{q}")
            y, q = (y, q - 1) if q > 1 else (y - 1, 4)
        quarters.reverse()
    evolution = []
    for q in quarters:
        n = sum(evo[q].values()) if q in evo else 0
        evolution.append({"quarter": q, "n": n,
                          "avg_stability": round(sum(t * c for t, c in evo[q].items()) / n, 2) if n else None,
                          "tiers": {TIER_LABEL[t]: evo[q].get(t, 0) if q in evo else 0
                                    for t in sorted(TIER_LABEL, reverse=True)}})

    k = {"total": total, "avg_stability": round(stab_sum / total, 2) if total else 0,
         "binding_pct": _pct(binding, total), "in_force_pct": _pct(in_force, total),
         "high_tier_pct": _pct(high_tier, total), "tight": tight, "loose": loose}
    return {
        "n": total,
        "kpis": k,
        "insights": morphology_insights(k, tiers, profiles, evolution),
        "legal_forms": form_rows,
        "tiers": tiers,
        "instrument_classes": [{"id": cid, "zh": c.zh, "desc": c.desc, "n": class_n.get(cid, 0),
                                "pct": _pct(class_n.get(cid, 0), total)} for cid, c in classes.items()],
        "top_instruments": [{"zh": instruments[iid].zh, "class": classes[instruments[iid].class_id].zh, "n": n}
                            for iid, n in sorted(instr_n.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
                            if iid in instruments],
        "statuses": [{"id": x.id, "zh": x.zh, "n": status_n.get(x.id, 0), "pct": _pct(status_n.get(x.id, 0), total)}
                     for x in statuses],
        "matrix": {"rows": [{"id": d, "zh": domains[d].zh if d in domains else d} for d in dom_order],
                   "cols": [{"id": r["id"], "zh": r["zh"]} for r in used_forms],
                   "cells": [[matrix[d].get(r["id"], 0) for r in used_forms] for d in dom_order]},
        "domain_profiles": profiles,
        "evolution": evolution,
    }


def morphology_insights(k: dict, tiers: list[dict], profiles: list[dict], evolution: list[dict]) -> list[str]:
    """由数据生成的几句解读 —— 数字变了,结论跟着变,不写死任何判断。"""
    out: list[str] = []
    if not k["total"]:
        return out
    top = max(tiers, key=lambda t: t["n"])
    out.append(f"库内 {k['total']} 条政策中,{top['label']}层级最多(占 {top['pct']}%);"
               f"可诉、强制力较强的占 {k['binding_pct']}%,现行有效的占 {k['in_force_pct']}%。")
    low = [p for p in profiles if p["n"] >= 2]
    if len(low) >= 2:
        strong = max(low, key=lambda p: p["avg_stability"])
        weak = min(low, key=lambda p: p["avg_stability"])
        if strong["id"] != weak["id"]:
            out.append(f"「{strong['zh']}」的政策层级最高(平均稳定性 {strong['avg_stability']}),"
                       f"多以{strong['dominant_form']}出台;「{weak['zh']}」最低(平均 {weak['avg_stability']}),"
                       f"以{weak['dominant_form']}为主,规则更容易调整。")
    if k["tight"] or k["loose"]:
        lean = "收紧" if k["tight"] > k["loose"] else ("放宽" if k["loose"] > k["tight"] else "持平")
        out.append(f"方向上,收紧 {k['tight']} 条、放宽 {k['loose']} 条,整体偏{lean}。")
    # 前后两半各至少 10 条才比较 —— 单季一两条的差异只是噪声
    half = len(evolution) // 2
    early, late = evolution[:half], evolution[half:]
    ne, nl = sum(e["n"] for e in early), sum(e["n"] for e in late)
    if ne >= 10 and nl >= 10:
        ae = sum((e["avg_stability"] or 0) * e["n"] for e in early) / ne
        al = sum((e["avg_stability"] or 0) * e["n"] for e in late) / nl
        diff = round(al - ae, 2)
        if abs(diff) >= 0.2:
            out.append(f"与 {early[0]['quarter']}–{early[-1]['quarter']} 相比,{late[0]['quarter']}–{late[-1]['quarter']} "
                       f"新出台政策的平均层级{'上升' if diff > 0 else '下降'}了 {abs(diff)}(稳定性 1–5),"
                       f"{'规则更趋向以高层级立法固定' if diff > 0 else '更多以公告、指引等灵活形式出台'}。")
    return out
