# -*- coding: utf-8 -*-
"""简体 → 繁体(台湾字形)转换:/zh-hant/ 下的静态页由 app.seo.build 用它从简体页生成。

为什么用 OpenCC 的 s2tw(只换字形)而不是 s2twp(连词汇一起换成台湾用语):
s2twp 会把法律文本改坏 ——「发布公告→釋出公告」「申请文件→申請檔案」「行政程序→行政程式」「项目→專案」。
s2tw 也有一简对多繁的错(「干辣椒→幹辣椒」),由 config/hant.json 的覆盖表在 OpenCC 之后逐条改正。

只转换汉字:OpenCC 不动 ASCII 与泰文,所以 URL、uid、CSS 类名、泰文原文天然不受影响;
convert_html 另外逐字核对「非汉字部分转换前后完全一致」,万一词典或覆盖表误伤了它们,导出直接报错。
不能被转换的汉字(语言切换链接上的「简体中文」)用 keep() 包起来。

OpenCC 的版本钉死在 requirements.txt:词典随版本变,不钉死的话 CI 的派生产物比对会漂。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .config import REPO_ROOT

CONFIG = REPO_ROOT / "config" / "hant.json"
MODE = "s2tw"

# keep() 的边界标记:Unicode 私用区字符,正文里不会出现
_K0, _K1 = "\ue000", "\ue001"
_KEEP_RE = re.compile(f"{_K0}(.*?){_K1}", re.S)
# 汉字(含扩展区与兼容区);其余字符(ASCII、泰文、标点)转换前后必须一字不差
_HAN_RE = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]")


def keep(text: str) -> str:
    """包起来的文字原样保留,不做繁简转换。"""
    if _K0 in text or _K1 in text:
        raise ValueError("keep() 的文字里不能含 U+E000 / U+E001(保留标记)")
    return f"{_K0}{text}{_K1}"


@lru_cache(maxsize=1)
def _converter():
    import opencc            # 延迟导入:只有导出繁体页时才需要
    return opencc.OpenCC(MODE)


def load_rules(path: Path | None = None) -> list[tuple[str | re.Pattern, str]]:
    """覆盖表:[[OpenCC 的输出, 应改成, 说明], ...],按顺序替换;以 re: 开头的是正则。"""
    path = path or CONFIG
    if not path.exists():
        return []
    rules = json.loads(path.read_text(encoding="utf-8")).get("rules") or []
    return [(re.compile(r[0][3:]) if r[0].startswith("re:") else r[0], r[1])
            for r in rules if isinstance(r, list) and len(r) >= 2 and r[0]]


def load_suspicious(path: Path | None = None) -> list[tuple[re.Pattern, str]]:
    """可疑字形清单:[[正则, 说明], ...]。只用来检查成品,不改文字。"""
    path = path or CONFIG
    if not path.exists():
        return []
    items = json.loads(path.read_text(encoding="utf-8")).get("suspicious") or []
    return [(re.compile(x[0]), x[1] if len(x) > 1 else "") for x in items if isinstance(x, list) and x and x[0]]


def scan(root: Path, patterns: list[tuple[re.Pattern, str]] | None = None,
         context: int = 8) -> list[tuple[str, str, str]]:
    """扫描导出的繁体成品(root 下的 .html / .xml),返回 [(相对路径, 说明, 片段)],按路径排序。
    只看标签以外的文字与属性值里的汉字;同一页同一片段只报一次。"""
    patterns = load_suspicious() if patterns is None else patterns
    hits: list[tuple[str, str, str]] = []
    if not root.is_dir():
        return hits
    for f in sorted(list(root.rglob("*.html")) + list(root.rglob("*.xml"))):
        text = f.read_text(encoding="utf-8")
        seen = set()
        for rx, note in patterns:
            for m in rx.finditer(text):
                snip = text[max(0, m.start() - context):m.end() + context].replace("\n", " ")
                if (note, snip) not in seen:
                    seen.add((note, snip))
                    hits.append((str(f.relative_to(root)), note, snip))
    return hits


class Converter:
    """一次导出用一个实例(覆盖表只读一次)。"""

    def __init__(self, rules: list[tuple[str | re.Pattern, str]] | None = None):
        self.rules = load_rules() if rules is None else rules

    def text(self, s: str) -> str:
        """先 OpenCC、后覆盖表;keep() 包住的部分原样保留(并去掉标记)。
        输入里出现不成对的保留标记(U+E000 / U+E001)直接报错,不静默吞掉。"""
        stray = _KEEP_RE.sub("", s)
        if _K0 in stray or _K1 in stray:
            raise ValueError("输入里有不成对的保留标记 U+E000 / U+E001")
        out, pos = [], 0
        for m in _KEEP_RE.finditer(s):
            out.append(self._conv(s[pos:m.start()]))
            out.append(m.group(1))
            pos = m.end()
        out.append(self._conv(s[pos:]))
        return "".join(out)

    def _conv(self, s: str) -> str:
        if not s or not _HAN_RE.search(s):
            return s
        t = _converter().convert(s)
        for a, b in self.rules:
            t = a.sub(b, t) if isinstance(a, re.Pattern) else t.replace(a, b)
        return t

    def html(self, s: str) -> str:
        """整页转换(HTML / XML / 纯文本都可以),并核对非汉字部分一字未动。"""
        out = self.text(s)
        src = _KEEP_RE.sub(lambda m: m.group(1), s)
        if _HAN_RE.sub("", src) != _HAN_RE.sub("", out):
            raise ValueError("繁简转换改动了非汉字内容(URL、泰文、标记等),检查 OpenCC 版本与 config/hant.json")
        return out


def main(argv: list[str] | None = None) -> int:
    """python -m app.hant --check [目录]:扫描繁体成品里的可疑字形,有命中则列出并非零退出。"""
    import argparse
    ap = argparse.ArgumentParser(description="繁体版转换检查")
    ap.add_argument("--check", nargs="?", const=str(REPO_ROOT / "zh-hant"), metavar="DIR",
                    help="扫描导出的繁体页(默认仓库里的 zh-hant/)")
    args = ap.parse_args(argv)
    if not args.check:
        ap.print_help()
        return 2
    hits = scan(Path(args.check))
    for path, note, snip in hits:
        print(f"{path}\t{note}\t{snip}")
    print(f"可疑字形:{len(hits)} 处" + ("" if hits else "(零命中)"))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
