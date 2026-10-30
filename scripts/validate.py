#!/usr/bin/env python3
"""檢查 data/apps.json 結構同內容，唔合格就 exit 1（令 workflow 停手，唔會推壞資料）。"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

DATA = Path(__file__).resolve().parent.parent / "data" / "apps.json"
REQUIRED = ("date", "source", "kind", "category", "title", "note", "metric", "url")
ALLOWED_SRC = {"Hacker News", "Hugging Face", "Product Hunt", "新聞"}
MAX_ITEMS = 6000


def fail(msg, errs):
    errs.append(msg)


def main():
    if not DATA.exists():
        print(f"[fail] 搵唔到 {DATA}", file=sys.stderr)
        return 1
    try:
        d = json.loads(DATA.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[fail] JSON 解析失敗：{e}", file=sys.stderr)
        return 1

    errs = []
    if not isinstance(d, dict):
        print("[fail] 根層唔係 object", file=sys.stderr)
        return 1

    items = d.get("items")
    if not isinstance(items, list) or not items:
        print("[fail] items 係空或者唔係 array", file=sys.stderr)
        return 1
    if len(items) > MAX_ITEMS:
        fail(f"條目過多（{len(items)} > {MAX_ITEMS}）", errs)

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d.get("updated", ""))):
        fail("updated 格式錯", errs)

    seen_urls, seen_ids = set(), set()
    per_day = {}
    for i, x in enumerate(items):
        tag = f"#{i}"
        if not isinstance(x, dict):
            fail(f"{tag} 唔係 object", errs)
            continue
        for k in REQUIRED:
            if not str(x.get(k) or "").strip():
                fail(f"{tag} 缺 {k}", errs)
        date = str(x.get("date", ""))
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            fail(f"{tag} date 唔合法：{date}", errs)
        if x.get("source") not in ALLOWED_SRC:
            fail(f"{tag} source 唔認識：{x.get('source')}", errs)
        u = str(x.get("url", ""))
        p = urlparse(u)
        if p.scheme not in ("http", "https") or not p.netloc:
            fail(f"{tag} url 唔合法：{u}", errs)
        key = u.split("#")[0].rstrip("/").lower()
        if key in seen_urls:
            fail(f"{tag} url 重複：{u}", errs)
        seen_urls.add(key)
        per_day[date] = per_day.get(date, 0) + 1
        if len(str(x.get("title"))) > 200:
            fail(f"{tag} title 過長", errs)
        if len(str(x.get("note"))) > 400:
            fail(f"{tag} note 過長", errs)

    if errs:
        print(f"[fail] 發現 {len(errs)} 個問題：", file=sys.stderr)
        for e in errs[:20]:
            print("  -", e, file=sys.stderr)
        return 1

    days = sorted(per_day)
    print(f"[ok] {len(items)} 條 / {len(days)} 日 · {days[0]} → {days[-1]}")
    print("[ok] 最新一日：" + "、".join(f"{k}×{v}" for k, v in
          sorted(per_day.items(), reverse=True)[:1]) if days else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
