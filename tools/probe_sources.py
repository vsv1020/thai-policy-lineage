"""临时:统计公报数据集全部月份里与「变更土地用途」相关的条目。只打印,不写数据。"""
import re, sys
from collections import Counter, defaultdict
sys.path.insert(0, "backend")
import httpx
from app import collect as C

LAND = {
    "城市规划(ผังเมือง)": r"ผังเมือง",
    "土地利用(การใช้ประโยชน์ที่ดิน)": r"ใช้ประโยชน์(?:ใน)?ที่ดิน",
    "土地整理(จัดรูปที่ดิน)": r"จัดรูปที่ดิน",
    "农地改革(ส.ป.ก./ปฏิรูปที่ดิน)": r"ปฏิรูปที่ดิน|ส\.ป\.ก",
    "林地(ป่าสงวน/ป่าไม้)": r"ป่าสงวน|ป่าไม้ถาวร|ป่าชายเลน|อุทยานแห่งชาติ",
    "公地转用(ถอนสภาพ/สาธารณประโยชน์/ราชพัสดุ)": r"ถอนสภาพ|สาธารณประโยชน์|ราชพัสดุ|ที่ดินของรัฐ",
    "工业区(นิคมอุตสาหกรรม/เขตพัฒนา)": r"นิคมอุตสาหกรรม|เขตพัฒนาพิเศษ|เขตส่งเสริมเศรษฐกิจพิเศษ",
    "建筑管制(ควบคุมอาคาร/ห้ามก่อสร้าง)": r"ควบคุมอาคาร|ห้ามก่อสร้าง|ห้ามดัดแปลง",
    "土地征收(เวนคืน)": r"เวนคืน",
    "土地税(ภาษีที่ดิน)": r"ภาษีที่ดิน",
    "土地开发(พัฒนาที่ดิน/จัดที่ดิน)": r"พัฒนาที่ดิน|การจัดที่ดิน|นิคมสร้างตนเอง",
}
PAT = {k: re.compile(v) for k, v in LAND.items()}

th = C.Throttle(1.0)
with C.source_client({"User-Agent": C.UA, "Accept": "application/json"}) as client:
    client.timeout = httpx.Timeout(120)
    res = C.fetch_ckan("dataset_02_04", th, client)
    usable = [r for r in res if r.get("datastore_active") or (r.get("format") or "").lower() == "json"]
    usable.sort(key=C.resource_period)
    print("resources", len(res), "usable", len(usable), [C.resource_period(r) for r in usable])
    by_kind, samples, total = Counter(), defaultdict(list), 0
    for r in usable:
        per = C.resource_period(r)
        try:
            payload, via = C.download(r, th, client)
        except Exception as e:
            print("FAIL", per, str(e)[:120]); continue
        rows = C.iter_records(payload)
        kept = 0
        for rec in rows:
            norm, why = C.normalize_gazette(rec, "x")
            if not norm:
                continue
            t = norm["titles"]["th"]
            kinds = [k for k, p in PAT.items() if p.search(t)]
            if not kinds:
                continue
            kept += 1
            for k in kinds:
                by_kind[k] += 1
                if len(samples[k]) < 12:
                    samples[k].append(f"{norm['dates']['published_at']} {t[:130]}")
        total += kept
        print(f"  {per[0]}-{per[1]:02d}: 原始 {len(rows)} 条,土地相关(过红线后) {kept}", flush=True)
    print("\nTOTAL", total)
    for k, v in by_kind.most_common():
        print(f"\n## {k}: {v}")
        for s in samples[k]:
            print("   ", s)
