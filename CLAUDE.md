# Ontology Tool — Project Memory

## 目標
個人用、單機跑的 ontology graph editor，整合 LLM 來自動調整/編輯 graph。結合 data lake（DuckDB）做互動式資料分析，探索 Graph RAG 概念。

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
| Data Lake | DuckDB（embedded，pip 裝，每個 project 一個 `warehouse.duckdb`） |
| LLM | Anthropic SDK（claude-sonnet-4-6），API key 放 .env（加入 .gitignore） |
| Frontend | 靜態 HTML/JS（FastAPI serve），Cytoscape.js + dagre layout 透過 CDN，不用 npm |
| 查詢語言 | SPARQL（graph）+ SQL（DuckDB） |
| Virtualenv | `.venv` — **所有 python/pip 操作必須用 `.venv/bin/python` 或 `.venv/bin/pip`，絕不用系統的** |

## 安全性

- Backend 只 bind `127.0.0.1`
- 每次啟動產生 random auth key，首次用 `?key=xxx` 存取後設 cookie
- `.env` 存 API key，不進 git

## Graph + Data Lake 設計

### 雙層架構
- **Graph（pyoxigraph）**— 存結構、關係、metadata
- **Data Lake（DuckDB）**— 存實際資料表，是 mapped classes 的 source of truth
- 兩者都是一等公民，沒有先後順序

### Class Definition（schema.json）
- 每個 project 有獨立的 `schema.json`，定義 class/relation 的 table mapping
- Mapping 是 **optional** — 有 mapping 的 class 對應 table row，沒有的只存在 graph
- Mapping 在 **Class level** — 設一次，所有該 label 的 nodes 都適用
- Mapping 可指向 **table 或 view**（graph 不區分）

### 同步規則（已實作）
- **Graph → DuckDB**：有 mapping 的 class，改 graph node 自動同步到 DuckDB（INSERT/UPDATE/DELETE）
  - 接入點：`add_node`、`modify_node`、`delete_node`、`add_edge`、`delete_edge`
  - `apply_diff` 透過上述函式自動觸發 sync
  - Sync 失敗只 log.error，不擋 graph 操作
- **DuckDB → Graph**：透過 UI「Sync to Graph」按鈕手動觸發
  - `import_class_to_graph` — 讀 table rows 建 graph nodes
  - `import_relation_to_graph` — 讀 table 的 parent-child 關係建 graph edges
  - Import 用 `_add_node_no_sync` / `_add_edge_no_sync` 避免回寫 DuckDB
- 反向自動同步（DuckDB 被外部修改 → graph）暫不做

### schema.json 格式
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

## 實作進度

### Phase 1: DuckDB Foundation ✅
- DuckDB singleton per project（同 pyoxigraph pattern）
- CSV/Parquet 上傳、list tables、table schema、SQL query
- schema.json CRUD（get/save/update class/relation mapping）
- `get_schema()` → `get_graph_schema()` rename
- 前端 Tables tab（upload、table list、SQL runner）
- 前端 Schema tab 顯示 table mapping 資訊

### Phase 2: Graph ↔ DuckDB Sync ✅
- Sync helpers：`_sync_node_to_duckdb`、`_sync_edge_to_duckdb`
- 接入 CRUD：add/modify/delete node/edge 自動 sync
- Import：`import_class_to_graph`、`import_relation_to_graph`（DuckDB → Graph，不觸發回寫）
- 前端 Tables tab：Map as Class / Map as Relation 設定 UI
- 前端「Sync to Graph」一鍵同步 nodes + edges

### Phase 3: LLM Integration（待做）
- LLM context 加入 DuckDB table schema + mapping 資訊
- nl_query 支援 SQL（LLM 自動判斷 SPARQL or SQL）
- suggest_mapping（LLM 自動建議 table → class/relation mapping）
- 前端 Query 結果區分 SPARQL/SQL 顯示

## Project Isolation

每個 project 對應：
- 獨立的 pyoxigraph store（`projects/{id}/`）
- 獨立的 DuckDB（`projects/{id}/warehouse.duckdb`）
- 獨立的 class/relation 定義（`projects/{id}/schema.json`）

## 已知踩坑紀錄

- pyoxigraph 的 `str(NamedNode)` 會帶角括號，`str(Literal)` 帶引號 → 必須用 `.value`
- pyoxigraph Store 每次開新實例會讀不到前一個實例的寫入 → 必須用 singleton cache
- IRI 不能有空白、`%` 在 SPARQL 會出問題 → 用底線取代非安全字元（`_iri_safe`）
- QuerySolution 沒有 `.get()` → 用 `solution[var]` + try/except
- LLM 查詢要帶既有 nodes/edges 摘要，否則 LLM 會猜錯 node ID
- `load_dotenv()` 必須在 `anthropic.Anthropic()` 之前執行
- DuckDB connection 必須在 `shutil.rmtree` 前 close，否則檔案被鎖
- DuckDB CSV upload 用 `read_csv_auto()` 需要 file path → 用 tempfile
- DuckDB → Graph import 必須用 `_add_node_no_sync` 避免觸發回寫造成重複

## 專案結構

```
ontology/
├── main.py              # FastAPI app + auth middleware + logging
├── db.py                # pyoxigraph + DuckDB 操作（singleton per project）
├── llm.py               # Anthropic 整合（suggest edits + NL query）
├── requirements.txt     # pinned versions
├── .env                 # ANTHROPIC_API_KEY（不進 git）
├── .env.example
├── .gitignore
├── CLAUDE.md            # 本檔案（Claude 記憶）
├── README.md
├── examples/            # 範例 CSV（bom.csv, suppliers.csv, supply_relations.csv）
├── projects/            # 每個 project 的資料（不進 git）
│   └── {id}/
│       ├── (pyoxigraph files)
│       ├── warehouse.duckdb
│       └── schema.json
├── docs/
│   └── spec.md          # 正式規格文件
└── static/
    └── index.html       # 整個前端（Cytoscape.js + dagre）
```

## 重要函式索引

### db.py
- `_store(project_id)` / `_duckdb(project_id)` — singleton getters
- `get_graph_schema(project_id)` — 從 graph 動態推導 schema（原名 get_schema）
- `get_project_schema(project_id)` — 讀 schema.json
- `_sync_node_to_duckdb(...)` / `_sync_edge_to_duckdb(...)` — graph → DuckDB sync
- `_add_node_no_sync(...)` / `_add_edge_no_sync(...)` — graph only（import 用）
- `import_class_to_graph(...)` / `import_relation_to_graph(...)` — DuckDB → graph

### llm.py
- `suggest_edits(project_id, content)` — NL → JSON diff
- `nl_query(project_id, question)` — NL → SPARQL → 執行結果

### main.py
- Graph CRUD: `/nodes`, `/edges`, `/llm/suggest`, `/llm/apply`
- DuckDB: `/tables`, `/tables/upload`, `/sql`
- Schema: `/schema`（graph）, `/project-schema`（schema.json）
- Import: `/import/class`, `/import/relation`

## Git

- Repo: https://github.com/dennischang/ontology.git
- Branch: main
