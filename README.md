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
