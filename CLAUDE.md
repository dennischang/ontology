# Ontology Tool — Project Memory

## 目標
個人用、單機跑的 ontology graph editor，整合 LLM 來自動調整/編輯 graph。

## 核心設計決策

- **單機本地** — 不需要 cloud DB，所有東西在本機跑
- **多 Project 隔離** — 每個 project 有自己獨立的 schema 和 graph data
- **Schema 由 LLM 驅動** — 透過 prompt 迭代調整 schema，幾輪後趨於穩定，之後只做小幅修改
- **Web UI 為主** — 可以下 graph 查詢語言

## Tech Stack

| 層 | 選擇 |
|---|---|
| Backend | FastAPI + uvicorn，bind 127.0.0.1（localhost only，安全性考量） |
| Graph DB | pyoxigraph（Rust 核心，pip 裝，embedded，支援 SPARQL） |
| LLM | Anthropic SDK，API key 放 .env（加入 .gitignore） |
| Frontend | 靜態 HTML/JS（FastAPI serve），Cytoscape.js 或 vis.js 與 Monaco Editor 透過 CDN，不用 npm |
| 查詢語言 | SPARQL |
| Virtualenv | `.venv` — **所有 python/pip 操作必須用 `.venv/bin/python` 或 `.venv/bin/pip`，絕不用系統的** |

## LLM 整合模式

### Graph 編輯（寫入）— 兩種入口，互相連動
- **自然語言** — 使用者輸入指令或貼入內容，LLM 生成 JSON diff → preview → 確認後寫入
- **UI 直接編輯** — 拖拉節點、新增邊、修改 property，直接寫入 DB
- 兩者都會即時反映在 graph view（單一 source of truth = DB）

### Graph 查詢（讀取）
1. 使用者輸入自然語言
2. LLM 讀取現有 schema，生成對應的 SPARQL
3. 顯示查詢結果（graph 或 table）
4. 同時顯示生成的 SPARQL（透明、可學習）

**使用者不需要自己寫 SPARQL**，但可以看到 LLM 產生的語句。

## Project Isolation

每個 project 對應一個獨立的 pyoxigraph store（獨立資料夾），schema history 也各自存放。

## 專案結構（規劃中）

```
ontology/
├── main.py
├── db.py
├── llm.py
├── projects/        # 每個 project 一個子資料夾
└── static/
    └── index.html
```
