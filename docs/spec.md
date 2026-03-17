# Ontology Editor — Specification

## Overview

個人用、單機跑的 ontology graph editor，整合 LLM 讓使用者透過自然語言建立、查詢、編輯 knowledge graph。支援多個獨立的 project，每個 project 有自己的 schema 與資料。

---

## Core Concepts

- **Project** — 最上層的隔離單位，每個 project 有獨立的 graph store 與 schema
- **Node (Entity)** — graph 中的節點，有 label（類型）與 properties
- **Edge (Relation)** — 節點之間的有向關係，有 relation type 與 properties
- **Schema** — 定義合法的 node labels、edge types 與其 properties，由 LLM 迭代產生並趨於穩定
- **Diff** — LLM 產生的變更集合（add/modify/delete），需使用者 review 後才套用

---

## Features

### 1. Project 管理
- 建立、刪除、切換 project
- 每個 project 獨立儲存（pyoxigraph store，一個 project 一個資料夾）
- Project 列表顯示於側邊欄

### 2. Graph View
- 視覺化呈現目前 project 的 graph
- 節點依 label 分色
- 支援 zoom / pan
- 點擊節點或邊 → 顯示 detail panel（properties 等）
- Layout 可切換（hierarchical / force-directed）

### 3. UI 直接編輯
- 拖拉新增節點（指定 label 與 properties）
- 拖拉連線建立 edge（選擇 relation type）
- 點擊節點/邊 → inline 編輯 properties
- 刪除節點/邊
- 所有操作即時寫入 DB，graph view 同步更新

### 4. 自然語言編輯（LLM）
- 使用者貼入文字或輸入自然語言指令
- LLM 讀取現有 schema，產生 JSON diff
- Frontend 顯示 diff preview（新增/修改/刪除 各自列出）
- 使用者逐條 accept / reject 或全部套用
- 確認後寫入 DB，graph view 更新

### 5. 自然語言查詢（LLM）
- 使用者輸入自然語言問題
- LLM 讀取現有 schema，產生 SPARQL
- 執行查詢，結果以 graph 或 table 呈現
- 同時顯示生成的 SPARQL（透明、可學習）

### 6. Schema 管理
- 自動從 LLM 編輯中抽取/更新 schema
- 顯示目前 schema（node labels、edge types、properties）
- Schema 版本歷史記錄
- 趨於穩定後，LLM 僅建議小幅修改

---

## Architecture

```
Browser (Static HTML/JS via CDN)
├── Graph View (Cytoscape.js)
├── Diff Preview Panel
├── Natural Language Input
├── Query Panel
└── Project Sidebar

FastAPI (127.0.0.1 only)
├── GET/POST /projects
├── GET/POST/DELETE /projects/{id}/nodes
├── GET/POST/DELETE /projects/{id}/edges
├── POST /projects/{id}/query          ← NL → SPARQL → 結果
├── POST /projects/{id}/llm/suggest    ← NL/內容 → JSON diff（不寫入）
└── POST /projects/{id}/llm/apply      ← 套用 confirmed diff

pyoxigraph (embedded, file-based)
└── projects/{id}/              ← 每個 project 獨立 store
```

---

## LLM Diff Format

LLM 輸出 structured JSON，backend 驗證後轉成 DB 操作：

```json
{
  "add_nodes": [
    { "id": "product_1", "label": "Product", "properties": { "name": "Widget" } }
  ],
  "add_edges": [
    { "source": "product_1", "target": "vendor_1", "relation": "suppliedBy" }
  ],
  "modify_nodes": [
    { "id": "product_1", "properties": { "price": 99 } }
  ],
  "delete_nodes": [],
  "delete_edges": []
}
```

---

## Tech Stack

| 層 | 技術 |
|---|---|
| Backend | Python, FastAPI, uvicorn（bind 127.0.0.1） |
| Graph DB | pyoxigraph（embedded，SPARQL） |
| LLM | Anthropic SDK（claude-sonnet-4-6） |
| Frontend | 靜態 HTML/JS，Cytoscape.js + Monaco Editor（CDN） |
| 環境 | `.venv`，`.env` 存 API key |
| 套件管理 | pip，`requirements.txt` |

---

## File Structure

```
ontology/
├── main.py              # FastAPI app entry point
├── db.py                # pyoxigraph 操作
├── llm.py               # Anthropic 整合（query & edit）
├── requirements.txt
├── .env                 # ANTHROPIC_API_KEY（不進 git）
├── .gitignore
├── projects/            # 每個 project 的 graph store
│   └── {project_id}/
├── docs/
│   └── spec.md
└── static/
    └── index.html       # 整個前端
```

---

## Out of Scope（目前不做）

- 多人協作
- Cloud 部署
- OWL reasoning / inference
- 完整 SPARQL editor（使用者自己寫 SPARQL）
- 匯出 RDF/OWL 標準格式
