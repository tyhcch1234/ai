# AI · 每日應用庫

每日自動收錄最新嘅 **AI 應用例子**，一日一頁累積落去。

🔗 https://tyhcch1234.github.io/ai/

## 收錄咩

| 來源 | 收錄內容 | 判斷方式 |
|---|---|---|
| Hacker News（Algolia API） | 開發者自製並公開嘅 AI 工具（Show HN）、熱門 AI 討論 | 標題含 AI 關鍵字、4 日內、分數門檻 |
| Hugging Face Spaces | 可以直接開嚟試嘅 AI 應用（gradio / streamlit / docker） | trendingScore 排名、45 日內有更新 |
| Product Hunt | 每日新上架而同 AI 有關嘅產品 | Atom feed + AI 關鍵字比對 |
| Google 新聞（香港繁中） | AI 落地應用嘅新聞報道 | RSS 搜尋「AI 應用 / 人工智能應用」 |

每日大約 12–16 條。所有標題、簡介、數字都係**來源原文節錄**，本站只做分類、去重同排版，唔會代寫評價或者補內容。

唔收錄：成人／換面／deepfake 類工具（`BLOCK_RE` 過濾）。

## 每日自動更新

`.github/workflows/daily.yml` 每日 **香港時間 07:00** 執行：

1. `scripts/fetch_apps.py` 抓四個來源 → 寫入 `data/apps.json`（只追加，唔改舊日子）＋ `archive/YYYY-MM-DD.md`
2. `scripts/validate.py` 驗結構（缺欄位、日期格式、網址重複、條數上限）→ 唔合格就唔推
3. 有變更才 commit & push（避免無謂 commit）

想即時手動跑：Actions → **Daily AI apps update** → Run workflow（可勾 `force` 覆寫當日）。

## 本地執行

```bash
python3 scripts/fetch_apps.py --dry-run     # 只印出抓到咩，唔寫檔
python3 scripts/fetch_apps.py               # 正式寫入（今日已有資料會跳過）
python3 scripts/fetch_apps.py --force       # 覆寫當日
python3 scripts/validate.py                 # 檢查資料
python3 -m http.server 8000                 # 開 http://localhost:8000 睇網頁
```

## 結構

```
index.html              首頁（純靜態，無外部依賴）
archive/index.html      歷史紀錄頁
data/apps.json          全部資料（items 按日期新→舊）
archive/YYYY-MM-DD.md   每日 markdown 存檔
scripts/fetch_apps.py   抓取 + 分類 + 去重
scripts/validate.py     資料驗證
.github/workflows/daily.yml
```

## 資料欄位

```json
{
  "date": "2026-10-30",
  "source": "Hacker News | Hugging Face | Product Hunt | 新聞",
  "kind": "應用 | 產品 | 討論 | 新聞",
  "category": "代理自動化 / 編程開發 / 影片 …",
  "title": "產品或專案名",
  "note": "來源原文節錄",
  "metric": "分數 · 留言 / 讚 · 熱度 / 上架狀態",
  "url": "原始連結",
  "hn": "（選填）HN 討論串",
  "rank": 1
}
```
