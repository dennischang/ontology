# Ontology Tool — Project Memory

## 目標
個人用、單機跑的 ontology graph editor，整合 LLM 來自動調整/編輯 graph。

## 核心設計決策

- **單機本地** — 不需要 cloud DB，所有東西在本機跑
- **多 Project 隔離** — 每個 project 有自己獨立的 schema 和 graph data
- **Schema 由 LLM 驅動** — 透過 prompt 迭代調整 schema，幾輪後趨於穩定，之後只做小幅修改
- **Web UI 為主** — 可以下 graph 查詢語言
- **文件分工** — `CLAUDE.md` 是 Claude 的記憶（決策、偏好），`docs/spec.md` 是正式規格文件

## Tech Stack

| 層 | 選擇 |
|---|---|
| Backend | FastAPI + uvicorn，bind 127.0.0.1（localhost only，安全性考量） |
| Graph DB | pyoxigraph（Rust 核心，pip 裝，embedded，支援 SPARQL），資料存於 `projects/{id}/` |
| LLM | Anthropic SDK（claude-sonnet-4-6），API key 放 .env（加入 .gitignore） |
| Frontend | 靜態 HTML/JS（FastAPI serve），Cytoscape.js + dagre layout 透過 CDN，不用 npm |
| 查詢語言 | SPARQL |
| Virtualenv | `.venv` — **所有 python/pip 操作必須用 `.venv/bin/python` 或 `.venv/bin/pip`，絕不用系統的** |

## 安全性

- Backend 只 bind `127.0.0.1`
- 每次啟動產生 random auth key，首次用 `?key=xxx` 存取後設 cookie
- `.env` 存 API key，不進 git

## LLM 整合模式

### Graph 編輯（寫入）— 兩種入口，互相連動
- **自然語言** — 使用者輸入指令或貼入內容，LLM 生成 JSON diff → preview → 確認後寫入
- **UI 直接編輯** — 拖拉節點、新增邊、修改 property，直接寫入 DB
- 兩者都會即時反映在 graph view（單一 source of truth = DB）

### Graph 查詢（讀取）
1. 使用者輸入自然語言
2. LLM 讀取現有 schema + 既有 nodes/edges 摘要，生成對應的 SPARQL
3. 顯示查詢結果（graph 或 table）
4. 同時顯示生成的 SPARQL（透明、可學習）

**使用者不需要自己寫 SPARQL**，但可以看到 LLM 產生的語句。

## Project Isolation

每個 project 對應一個獨立的 pyoxigraph store（獨立資料夾），schema history 也各自存放。

## 已知踩坑紀錄

- pyoxigraph 的 `str(NamedNode)` 會帶角括號，`str(Literal)` 帶引號 → 必須用 `.value`
- pyoxigraph Store 每次開新實例會讀不到前一個實例的寫入 → 必須用 singleton cache
- IRI 不能有空白、`%` 在 SPARQL 會出問題 → 用底線取代非安全字元（`_iri_safe`）
- QuerySolution 沒有 `.get()` → 用 `solution[var]` + try/except
- LLM 查詢要帶既有 nodes/edges 摘要，否則 LLM 會猜錯 node ID
- `load_dotenv()` 必須在 `anthropic.Anthropic()` 之前執行

## 專案結構

```
ontology/
├── main.py              # FastAPI app + auth middleware + logging
├── db.py                # pyoxigraph 操作（singleton Store per project）
├── llm.py               # Anthropic 整合（suggest edits + NL query）
├── requirements.txt     # pinned versions
├── .env                 # ANTHROPIC_API_KEY（不進 git）
├── .env.example
├── .gitignore
├── CLAUDE.md            # 本檔案（Claude 記憶）
├── README.md
├── projects/            # 每個 project 的 graph store（不進 git）
├── docs/
│   └── spec.md          # 正式規格文件
└── static/
    └── index.html       # 整個前端（Cytoscape.js + dagre）
```

## Git

- Repo: https://github.com/dennischang/ontology.git
- Branch: main
