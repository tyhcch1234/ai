#!/usr/bin/env python3
"""每日抓「最新 AI 應用例子」，追加到 data/apps.json。

資料來源（全部公開、免金鑰）：
  1. Hacker News（Algolia API）— Show HN 自製 AI 工具 + 熱門 AI 討論
  2. Hugging Face Spaces — 可以直接開嚟試嘅 AI 應用（gradio / streamlit / docker）
  3. Product Hunt — 每日新上架產品之中同 AI 有關嘅
  4. Google 新聞（RSS，香港繁中）— AI 落地應用新聞

設計原則：
  - 只追加，永不覆蓋舊日子；同一日唔會重複抓
  - 任何一個來源失敗都只係少幾條，唔會令 workflow 變紅
  - 每條都保留原始連結同來源，唔會自行創作內容

用法：
    python3 scripts/fetch_apps.py              # 正式寫入
    python3 scripts/fetch_apps.py --dry-run    # 只印出抓到咩
    python3 scripts/fetch_apps.py --date 2026-10-30 --force
"""
import argparse
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "apps.json"
ARCHIVE = ROOT / "archive"
HKT = dt.timezone(dt.timedelta(hours=8))
UA = "Mozilla/5.0 (compatible; ai-daily/1.0; +https://github.com/tyhcch1234/ai)"

# ── 判斷係咪 AI 相關 ────────────────────────────────────────────────
AI_RE = re.compile(
    r"(?<![\w.])("
    r"a\.?i\.?|ai-|llm|llms|gpt[\w.-]*|chatgpt|claude|gemini|openai|anthropic|deepmind"
    r"|mistral|llama|qwen|deepseek|grok|perplexity|agent|agents|agentic|rag|mcp"
    r"|copilot|cursor|windsurf|diffusion|sora|veo|whisper|transformer|neural"
    r"|machine learning|inference|embedding|vector|prompt|genai|generative"
    r"|multimodal|fine-?tun\w*|hugging ?face|midjourney|runway|kling|vibe coding"
    r"|text-to-\w+|speech-to-\w+|人工智能|生成式|大模型|智能體"
    r")(?![\w])",
    re.I,
)

# ── 唔收錄：成人／換面／侵權類，公開網站唔適合展示 ─────────────────
BLOCK_RE = re.compile(
    r"(uncensor|nsfw|\bnude|porn|hentai|\b18\+|deepfake|face ?swap|nudify|undress"
    r"|jailbreak|\bonlyfans)",
    re.I,
)

# ── 領域分類（順序有意義：越specific越前）────────────────────────────
CATS = [
    ("影片", r"\bvideo|\bfilm|animation|sora|veo|runway|kling|wan ?2|lip.?sync|avatar|字幕|影片"),
    ("圖像設計", r"\bimage|\bphoto|design|poster|midjourney|flux|diffusion|\b3d\b|render|logo|icon|background|設計|圖片"),
    ("聲音", r"\baudio|\bvoice|speech|\btts\b|music|whisper|suno|podcast|transcri|語音|音樂"),
    ("編程開發", r"\bcode|coding|developer|\bide\b|github|\bsdk\b|compiler|debug|refactor|\bcli\b|terminal|程式"),
    ("代理自動化", r"agent|automat|workflow|\brpa\b|browser use|orchestrat|自動化|代理"),
    ("文書辦公", r"\bdocs?\b|document|\bpdf\b|\bnotes?\b|meeting|email|excel|spreadsheet|slide|presentation|resume|簡報|文件"),
    ("營銷客服", r"\bcrm\b|support|\bsales\b|marketing|\bseo\b|\bads?\b|outreach|lead|客服|營銷"),
    ("教育", r"\blearn|tutor|study|course|educat|exam|flashcard|教學|學習"),
    ("醫療健康", r"health|medical|clinic|therap|calorie|fitness|workout|\bdiet\b|sleep|醫療|健康"),
    ("金融", r"financ|trading|invest|bank|accounting|invoice|payment|\btax\b|金融|投資"),
    ("法律合規", r"legal|\blaw\b|contract|compliance|\bgdpr\b|privacy|法律|合規"),
    ("電商零售", r"shop|e-?commerce|\bstore\b|checkout|pricing|listing|電商|零售"),
    ("遊戲", r"\bgame|gaming|unity|roblox|pixel|遊戲"),
    ("數據分析", r"\bdata\b|analytic|\bsql\b|dashboard|\brag\b|search|scrap|monitor|數據|分析"),
    ("模型研究", r"\bmodel|benchmark|\bpaper\b|release|open.?source|training|inference|dataset|模型|研究"),
]


def http_get(url, timeout=30, lang="en"):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept-Language": f"{lang},en;q=0.8"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def classify(text):
    low = text.lower()
    for label, pat in CATS:
        if re.search(pat, low):
            return label
    return "其他"


def clean(s, limit=180):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = (s.replace("&#x27;", "'").replace("&#39;", "'").replace("&quot;", '"')
          .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&nbsp;", " "))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit].rstrip() + ("…" if len(s) > limit else "")


def norm_url(u):
    if not u:
        return ""
    u = u.split("#")[0].rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u, flags=re.I)
    u = re.sub(r"[?&](utm_[^&]+|ref=[^&]+)", "", u)
    return u.lower()


def is_ai(text):
    return bool(AI_RE.search(text or ""))


# ── 1. Hacker News ──────────────────────────────────────────────────
def source_hn(limit_show=4, limit_story=2):
    out = []

    def grab(url, kind, limit):
        try:
            raw = http_get(url)
            hits = json.loads(raw).get("hits", [])
        except Exception as e:
            print(f"[warn] HN {kind} 抓取失敗：{e}", file=sys.stderr)
            return
        n = 0
        for h in hits:
            title = clean(h.get("title") or "", 160)
            if not title or not is_ai(title + " " + clean(h.get("story_text") or "", 400)):
                continue
            link = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            points = h.get("points") or 0
            cmts = h.get("num_comments") or 0
            body = clean(h.get("story_text") or "", 170)
            note = body or ("開發者自建並公開分享嘅 AI 專案。" if kind == "應用" else
                            "Hacker News 上熱門嘅 AI 討論。")
            out.append({
                "source": "Hacker News",
                "kind": kind,
                "category": classify(title + " " + body),
                "title": re.sub(r"^Show HN:\s*", "", title),
                "note": note,
                "metric": f"{points} 分 · {cmts} 則討論",
                "url": link,
                "hn": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            })
            n += 1
            if n >= limit:
                break

    since = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=4)).timestamp())
    grab("https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&query=AI"
         f"&hitsPerPage=80&numericFilters=points>=2,created_at_i>{since}", "應用", limit_show)
    grab("https://hn.algolia.com/api/v1/search?tags=story&query=AI"
         f"&hitsPerPage=60&numericFilters=points>=80,created_at_i>{since}", "討論", limit_story)
    return out


# ── 2. Hugging Face Spaces ──────────────────────────────────────────
def source_hf(limit=4):
    out = []
    try:
        raw = http_get("https://huggingface.co/api/spaces?sort=trendingScore&direction=-1&limit=40&full=true")
        spaces = json.loads(raw)
    except Exception as e:
        print(f"[warn] HF 抓取失敗：{e}", file=sys.stderr)
        return out

    fresh_cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45)).strftime("%Y-%m-%d")
    pool = [s for s in spaces if (s.get("lastModified") or "")[:10] >= fresh_cut]
    cat_count = {}
    for s in pool:
        card = s.get("cardData") or {}
        title = clean(card.get("title") or s.get("id", "").split("/")[-1], 90)
        desc = clean(card.get("short_description") or "", 170)
        if not title:
            continue
        cat = classify(f"{title} {desc} {' '.join((card.get('tags') or [])[:6])}")
        if cat_count.get(cat, 0) >= 2:
            continue
        cat_count[cat] = cat_count.get(cat, 0) + 1
        out.append({
            "source": "Hugging Face",
            "kind": "應用",
            "category": cat,
            "title": title,
            "note": desc or "Hugging Face 上可以直接開嚟玩嘅 AI 應用。",
            "metric": f"{s.get('likes', 0)} 讚 · 熱度 {int(s.get('trendingScore') or 0)}",
            "url": f"https://huggingface.co/spaces/{s['id']}",
        })
        if len(out) >= limit:
            break
    return out


# ── 3. Product Hunt ─────────────────────────────────────────────────
def source_ph(limit=4):
    out = []
    try:
        raw = http_get("https://www.producthunt.com/feed")
        feed = ET.fromstring(raw)
    except Exception as e:
        print(f"[warn] Product Hunt 抓取失敗：{e}", file=sys.stderr)
        return out

    NS = "{http://www.w3.org/2005/Atom}"
    for e in feed.findall(f"{NS}entry"):
        title = clean(e.findtext(f"{NS}title") or "", 90)
        tagline = clean(e.findtext(f"{NS}content") or "", 170)
        if not title or not is_ai(f"{title} {tagline}"):
            continue
        link = ""
        for ln in e.findall(f"{NS}link"):
            if ln.get("rel") == "alternate":
                link = ln.get("href") or ""
        if not link:
            continue
        out.append({
            "source": "Product Hunt",
            "kind": "產品",
            "category": classify(f"{title} {tagline}"),
            "title": title,
            "note": tagline or "今日新上架嘅 AI 產品。",
            "metric": "今日上架",
            "url": link,
        })
        if len(out) >= limit:
            break
    return out


# ── 4. Google 新聞（香港繁中）───────────────────────────────────────
def source_news(limit=3):
    out = []
    q = urllib.parse.quote('AI 應用 OR 人工智能 應用')
    url = (f"https://news.google.com/rss/search?q={q}"
           "&hl=zh-HK&gl=HK&ceid=HK:zh-Hant")
    try:
        raw = http_get(url, lang="zh-HK")
        feed = ET.fromstring(raw)
    except Exception as e:
        print(f"[warn] Google 新聞抓取失敗：{e}", file=sys.stderr)
        return out

    for it in feed.iter("item"):
        title = clean(it.findtext("title") or "", 140)
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        src = it.findtext("source") or ""
        if src:
            title = re.sub(r"\s*[-–|]\s*" + re.escape(src) + r"\s*$", "", title)
        title = re.sub(r"\s*(作者|來源|編輯|責任編輯)\s*[：:]?\s*\S+\s*$", "", title).strip()
        out.append({
            "source": "新聞",
            "kind": "新聞",
            "category": classify(title),
            "title": title,
            "note": clean(it.findtext("description") or "", 150) or "AI 落地應用相關報道。",
            "metric": clean(src, 24) or "Google 新聞",
            "url": link,
        })
        if len(out) >= limit:
            break
    return out


def tokens(s):
    return {w for w in re.split(r"\W+", (s or "").lower()) if len(w) > 1}


def merge(items):
    """網址相同、標題幾乎相同、或者含封鎖字嘅都剔除。"""
    seen_u, kept_tok, out = set(), [], []
    for it in items:
        title = it.get("title") or ""
        if BLOCK_RE.search(title + " " + (it.get("note") or "")):
            continue
        u = norm_url(it.get("url"))
        if not u or u in seen_u:
            continue
        tk = tokens(title)
        if tk and any(len(tk & k) / max(1, len(tk | k)) > 0.7 for k in kept_tok):
            continue
        seen_u.add(u)
        kept_tok.append(tk)
        out.append(it)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="今日已有資料都照加")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（預設今日，香港時間）")
    args = ap.parse_args()

    today = args.date or dt.datetime.now(HKT).strftime("%Y-%m-%d")

    batch = merge(
        source_hn() + source_hf() + source_ph() + source_news()
    )
    if not batch:
        print("[skip] 今日四個來源都冇抓到內容")
        return 0

    for i, it in enumerate(batch, 1):
        it["date"] = today
        it["rank"] = i

    print(f"[ok] 抓 {len(batch)} 條（{today}）")
    for i in batch:
        print(f"  {i['rank']:>2}. [{i['source']}/{i['category']}] {i['title']}")

    if args.dry_run:
        return 0

    data = {"updated": today, "items": []}
    if DATA.exists():
        try:
            data = json.loads(DATA.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[warn] 舊 data 讀取失敗，改用空檔：{e}", file=sys.stderr)
    data.setdefault("items", [])

    if not args.force and any(x.get("date") == today for x in data["items"]):
        print(f"[skip] {today} 已經有資料，唔重複加（要覆寫請用 --force）")
        return 0

    before = len(data["items"])
    data["items"] = batch + [x for x in data["items"] if x.get("date") != today] if args.force \
        else batch + data["items"]
    data["items"].sort(key=lambda x: (x.get("date", ""), -int(x.get("rank") or 0)), reverse=True)
    data["updated"] = max([today, data.get("updated") or today])
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[done] 新增 {len(data['items']) - before} 條，總數 {len(data['items'])}")

    # 每日 markdown 存檔（方便日後回顧／給搜索器讀）
    ARCHIVE.mkdir(exist_ok=True)
    md = [f"# {today} AI 應用日誌", "",
          f"共 {len(batch)} 條，自動抓取自公開來源。", ""]
    for i in batch:
        md.append(f"## {i['rank']}. {i['title']}")
        md.append(f"- 來源：{i['source']}（{i['kind']}／{i['category']}）")
        md.append(f"- {i['note']}")
        md.append(f"- {i['metric']}")
        md.append(f"- 連結：{i['url']}")
        md.append("")
    (ARCHIVE / f"{today}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[done] 已寫 archive/{today}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
