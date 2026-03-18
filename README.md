# Ontology Editor

LLM-powered ontology graph editor. Local, single-machine tool for building and querying knowledge graphs via natural language.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Configuration

Copy the example and fill in your API key:

```bash
cp .env.example .env
```

Edit `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
.venv/bin/python main.py
```

Terminal will print a URL with an auth key. Open that URL in a browser:

```
🔗 Open: http://127.0.0.1:8000?key=<random-key>
```

The key is regenerated on every restart. Only requests with this key (or the resulting cookie) are accepted.

## Features

- **Multi-project** — each project has its own isolated graph and schema
- **LLM Edit** — paste text or give instructions, AI suggests graph changes with diff preview
- **Natural Language Query** — ask questions, AI generates SPARQL, shows results + generated query
- **UI Editing** — add/edit/delete nodes and edges directly in the graph view
- **SPARQL** — raw SPARQL access for advanced queries
- **Data Lake (DuckDB)** — each project has an embedded DuckDB for tabular data and SQL queries
- **Graph ↔ Table Sync** — optional mapping between graph classes and DuckDB tables, with bidirectional sync

## Data Lake Usage

Each project includes a DuckDB data lake. Switch to the **Tables** tab to use it.

### Upload Tables

1. In the Tables tab, enter a **table name** (e.g. `bom`)
2. Choose a **CSV or Parquet** file
3. Click **Upload** — the file is loaded into DuckDB as a table

Example CSVs are provided in the `examples/` directory:
- `bom.csv` — Bill of Materials with parent-child relationships
- `suppliers.csv` — Supplier master data
- `supply_relations.csv` — Part-supplier relationships

### SQL Query

Use the SQL runner at the bottom of the Tables tab to query uploaded tables directly:

```sql
SELECT * FROM bom WHERE parent_id = 'frame_a';
```

### Class/Relation Mapping (Optional)

You can map graph classes and relations to DuckDB tables via `schema.json`:

1. Click a table in the list to see its columns
2. Click **Map as Class** to create a mapping from a graph node label to this table (specify `id_column` and optional `column_mapping`)
3. Click **Map as Relation** to map a graph edge type to this table (specify `source_column` and `target_column`)

Once mapped:
- Adding/modifying/deleting graph nodes will auto-sync to the DuckDB table
- Click **Sync to Graph** to import table rows as graph nodes and edges (DuckDB → Graph)
