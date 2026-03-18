# Ontology Editor — Specification

## Overview

個人用、單機跑的 ontology graph editor，整合 LLM 讓使用者透過自然語言建立、查詢、編輯 knowledge graph。支援多個獨立的 project，每個 project 有自己的 schema 與資料。結合 DuckDB data lake 做互動式資料分析。

---

## Core Concepts

- **Project** — 最上層的隔離單位，每個 project 有獨立的 graph store、data lake 與 schema
- **Node (Entity)** — graph 中的節點，有 label（類型）與 properties
- **Edge (Relation)** — 節點之間的有向關係，有 relation type
- **Graph Schema** — 由 graph 資料動態推導（node labels、edge types、properties），由 LLM 迭代產生並趨於穩定
- **Project Schema (schema.json)** — 顯式定義 class/relation 的 table mapping（optional per class）
- **Diff** — LLM 產生的變更集合（add/modify/delete），需使用者 review 後才套用
- **Table** — DuckDB 中的資料表，可從 CSV/Parquet 上傳，支援 SQL 查詢

---

## Features

### 1. Project 管理 ✅
- 建立、刪除、切換 project
- 每個 project 獨立儲存（pyoxigraph store + DuckDB + schema.json，`projects/{id}/`）
- Project 列表顯示於左側欄，hover 顯示刪除按鈕

### 2. Graph View ✅
- Cytoscape.js 視覺化呈現目前 project 的 graph
- 節點依 label 分色，圓角矩形，大小自動配合文字
- 支援 zoom / pan
- 點擊節點 → 高亮第一層鄰居（neighbor highlight），其餘 dim
- 點擊空白處 → 取消高亮
- Layout 切換：Hierarchical L→R / T→B（dagre）、Force-directed（cose）

### 3. UI 直接編輯 ✅
- 透過工具列按鈕新增節點（指定 ID、label、properties JSON）
- 透過工具列按鈕新增邊（指定 source、target、relation）
- 點擊節點 → Details tab 編輯 properties、刪除節點
- 點擊邊 → Details tab 查看、刪除邊
- 所有操作即時寫入 DB，graph view 同步更新

### 4. 自然語言編輯（LLM）✅
- 使用者在 LLM Edit tab 貼入文字或輸入指令
- LLM 讀取現有 schema + 既有 node IDs，產生 JSON diff
- Frontend 顯示 diff preview（綠色新增 / 黃色修改 / 紅色刪除），各有 checkbox
- 使用者逐條 accept / reject 或全部套用
- 確認後寫入 DB，graph view 更新

### 5. 自然語言查詢（LLM）✅
- 使用者在 Query tab 輸入自然語言問題
- LLM 讀取現有 schema + nodes/edges 摘要，產生 SPARQL
- 執行查詢，結果以 table 呈現
- 同時顯示生成的 SPARQL（透明、可學習）
- 另有 Raw SPARQL 區塊供進階使用者直接下 SPARQL

### 6. Schema 管理 ✅
- Schema tab 顯示目前 schema（node labels、relation types、properties by label）
- Graph schema 從 graph 資料動態推導
- Project schema（schema.json）定義 class/relation 的 table mapping

### 7. Data Lake（DuckDB）✅
- 每個 project 有獨立的 DuckDB（`warehouse.duckdb`）
- 上傳 CSV/Parquet → 自動建表
- Tables tab 顯示所有表格、column schema
- SQL runner 可直接下 SQL 查詢
- Class/Relation mapping 透過 schema.json 設定（optional）
- Tables tab 可設定 class/relation mapping（指定 source table、id_column、column_mapping 等）

### 8. Graph ↔ DuckDB Sync ✅
- **Graph → DuckDB**：新增/修改/刪除 node 或 edge 時，若其 class/relation 有 mapping，自動同步到 DuckDB table
  - `add_node` → INSERT row
  - `modify_node` → UPDATE row
  - `delete_node` → DELETE row
  - `add_edge` → INSERT row（如果 relation 有 mapping）
  - `delete_edge` → DELETE row（如果 relation 有 mapping）
  - Sync 失敗只 log.error，不阻擋 graph 操作
- **DuckDB → Graph**：透過「Sync to Graph」按鈕手動觸發
  - 自動偵測所有有 mapping 的 class 和 relation
  - 先 import class nodes，再 import relation edges
  - Import 使用 `_add_node_no_sync` / `_add_edge_no_sync` 避免寫回迴圈
  - 已存在的 node/edge 會被跳過（不重複新增）
- **反向自動同步**（DuckDB 外部修改 → 自動更新 graph）目前不支援

### 9. 安全性 ✅
- Backend bind 127.0.0.1（localhost only）
- 每次啟動產生 random auth key，URL 帶 `?key=xxx`
- 首次存取後設 httponly cookie，後續 request 自動驗證

---

## Architecture

```
Browser (Static HTML/JS via CDN)
├── Graph View (Cytoscape.js + dagre layout)
├── Diff Preview Panel
├── Natural Language Input
├── Query Panel (NL + Raw SPARQL)
├── Tables Panel (Upload, List, Mapping Config, Sync to Graph, SQL Runner)
├── Schema Panel (Graph Schema + Table Mappings)
├── Details Panel (node/edge editing)
└── Project Sidebar

FastAPI (127.0.0.1 only, auth key middleware)
├── GET  /                              ← serve index.html
├── GET  /projects                      ← list projects
├── POST /projects                      ← create project
├── DEL  /projects/{id}                 ← delete project
├── GET  /projects/{id}/graph           ← all nodes + edges
├── GET  /projects/{id}/schema          ← derived graph schema
├── POST /projects/{id}/nodes           ← add node
├── PATCH /projects/{id}/nodes/{nid}    ← modify node props
├── DEL  /projects/{id}/nodes/{nid}     ← delete node
├── POST /projects/{id}/edges           ← add edge
├── DEL  /projects/{id}/edges?s=&t=&r=  ← delete edge
├── POST /projects/{id}/llm/suggest     ← NL → JSON diff（不寫入）
├── POST /projects/{id}/llm/apply       ← 套用 confirmed diff
├── POST /projects/{id}/query           ← NL → SPARQL → 結果
├── POST /projects/{id}/sparql          ← raw SPARQL
├── GET  /projects/{id}/tables          ← list DuckDB tables
├── GET  /projects/{id}/tables/{name}   ← table column schema
├── POST /projects/{id}/tables/upload   ← upload CSV/Parquet
├── POST /projects/{id}/sql             ← run SQL query
├── GET  /projects/{id}/project-schema  ← read schema.json
├── PUT  /projects/{id}/project-schema  ← write schema.json
├── PATCH /projects/{id}/project-schema/classes/{name}    ← update class mapping
├── PATCH /projects/{id}/project-schema/relations/{name}  ← update relation mapping
├── POST /projects/{id}/import/class                      ← DuckDB → graph nodes（by class mapping）
└── POST /projects/{id}/import/relation                   ← DuckDB → graph edges（by relation mapping）

Storage (per project)
├── pyoxigraph (embedded, file-based, singleton Store)
├── DuckDB (warehouse.duckdb, singleton connection)
└── schema.json (class/relation → table mapping)
```

---

## RDF URI Schema

每個 project 的 namespace: `http://ontology.local/p/{project_id}/`

| 類型 | URI pattern | 範例 |
|---|---|---|
| Node | `{ns}n/{node_id}` | `http://ontology.local/p/test/n/product_1` |
| Class | `{ns}c/{Label}` | `http://ontology.local/p/test/c/Product` |
| Property | `{ns}p/{key}` | `http://ontology.local/p/test/p/name` |
| Relation | `{ns}r/{relation}` | `http://ontology.local/p/test/r/suppliedBy` |

ID 中的非安全字元（空白等）會被 `_iri_safe` 替換為底線。

---

## Project Schema (schema.json)

定義 graph class/relation 與 DuckDB table 之間的 optional mapping：

```json
{
  "classes": {
    "Part": {
      "source": "bom",
      "id_column": "part_id",
      "column_mapping": { "name": "part_name", "cost": "unit_cost" }
    },
    "Team": {}
  },
  "relations": {
    "contains": {
      "source": "bom",
      "source_column": "parent_id",
      "target_column": "part_id"
    }
  }
}
```

- `source` 可以是 table 或 view
- 沒有 `source` 的 class/relation 只存在於 graph
- Mapping 在 Class level，所有該 label 的 nodes 都適用

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
    { "id": "product_1", "properties": { "price": "99" } }
  ],
  "delete_nodes": ["old_node"],
  "delete_edges": [
    { "source": "a", "target": "b", "relation": "rel" }
  ]
}
```

---

## Tech Stack

| 層 | 技術 |
|---|---|
| Backend | Python 3.13, FastAPI 0.135.1, uvicorn 0.42.0 |
| Graph DB | pyoxigraph 0.5.6（embedded RDF store，SPARQL） |
| Data Lake | DuckDB 1.2.1（embedded，SQL，CSV/Parquet） |
| LLM | anthropic 0.85.0（claude-sonnet-4-6） |
| Frontend | 靜態 HTML/JS，Cytoscape.js 3.28.1 + cytoscape-dagre 2.5.0（CDN） |
| 環境 | `.venv`，`.env` 存 API key，python-dotenv 1.2.2 |

---

## File Structure

```
ontology/
├── main.py              # FastAPI app + auth middleware + logging
├── db.py                # pyoxigraph + DuckDB 操作（singleton per project）
├── llm.py               # Anthropic 整合（suggest edits + NL query）
├── requirements.txt     # pinned direct dependencies
├── .env                 # ANTHROPIC_API_KEY（不進 git）
├── .env.example
├── .gitignore
├── CLAUDE.md            # Claude 記憶（決策、偏好、踩坑）
├── README.md            # 使用說明
├── projects/            # 每個 project 的資料（不進 git）
│   └── {project_id}/
│       ├── (pyoxigraph files)
│       ├── warehouse.duckdb
│       └── schema.json
├── docs/
│   └── spec.md          # 本文件
└── static/
    └── index.html       # 整個前端 UI
```

---

## Out of Scope（目前不做）

- 多人協作
- Cloud 部署
- OWL reasoning / inference
- 匯出 RDF/OWL 標準格式
- Schema 版本歷史
- Edge properties（目前 edge 只有 relation type，無額外 properties）
- DuckDB 外部修改後 sync 回 graph（反向同步）
