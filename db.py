import re
import json
import logging
import tempfile
import duckdb
import pyoxigraph as ox
from pathlib import Path

log = logging.getLogger("ontology")

PROJECTS_DIR = Path("projects")
BASE = "http://ontology.local/"
RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
RDFS_CLASS = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#Class")
RDFS_LABEL = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#label")
DG = ox.DefaultGraph()


def _val(term) -> str:
    """Get raw string value from any pyoxigraph term (no angle brackets or quotes)."""
    return term.value


def _store_path(project_id: str) -> str:
    path = PROJECTS_DIR / project_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _ns(project_id: str) -> str:
    return f"{BASE}p/{_iri_safe(project_id)}/"


def _iri_safe(s: str) -> str:
    """Replace non-IRI-safe characters with underscores."""
    return re.sub(r'[^a-zA-Z0-9._~-]', '_', s)


def _node(project_id: str, node_id: str) -> ox.NamedNode:
    return ox.NamedNode(f"{_ns(project_id)}n/{_iri_safe(node_id)}")


def _class(project_id: str, label: str) -> ox.NamedNode:
    return ox.NamedNode(f"{_ns(project_id)}c/{_iri_safe(label)}")


def _prop(project_id: str, key: str) -> ox.NamedNode:
    return ox.NamedNode(f"{_ns(project_id)}p/{_iri_safe(key)}")


def _rel(project_id: str, relation: str) -> ox.NamedNode:
    return ox.NamedNode(f"{_ns(project_id)}r/{_iri_safe(relation)}")


# --- Singletons ---

_stores: dict[str, ox.Store] = {}


def _store(project_id: str) -> ox.Store:
    if project_id not in _stores:
        _stores[project_id] = ox.Store(_store_path(project_id))
    return _stores[project_id]


_duckdbs: dict[str, duckdb.DuckDBPyConnection] = {}


def _duckdb(project_id: str) -> duckdb.DuckDBPyConnection:
    if project_id not in _duckdbs:
        path = PROJECTS_DIR / project_id / "warehouse.duckdb"
        path.parent.mkdir(parents=True, exist_ok=True)
        _duckdbs[project_id] = duckdb.connect(str(path))
    return _duckdbs[project_id]


def _schema_path(project_id: str) -> Path:
    return PROJECTS_DIR / project_id / "schema.json"


# --- Projects ---

def list_projects() -> list[str]:
    if not PROJECTS_DIR.exists():
        return []
    return [d.name for d in sorted(PROJECTS_DIR.iterdir()) if d.is_dir()]


def create_project(project_id: str):
    _store(project_id)
    _duckdb(project_id)
    sp = _schema_path(project_id)
    if not sp.exists():
        sp.write_text(json.dumps({"classes": {}, "relations": {}}, indent=2))


def delete_project(project_id: str):
    import shutil
    _stores.pop(project_id, None)
    conn = _duckdbs.pop(project_id, None)
    if conn:
        conn.close()
    path = PROJECTS_DIR / project_id
    if path.exists():
        shutil.rmtree(path)


# --- Schema.json CRUD ---

def get_project_schema(project_id: str) -> dict:
    sp = _schema_path(project_id)
    if sp.exists():
        return json.loads(sp.read_text())
    return {"classes": {}, "relations": {}}


def save_project_schema(project_id: str, schema: dict):
    sp = _schema_path(project_id)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(schema, indent=2, ensure_ascii=False))


def update_class_mapping(project_id: str, class_name: str, mapping: dict):
    schema = get_project_schema(project_id)
    schema.setdefault("classes", {})[class_name] = mapping
    save_project_schema(project_id, schema)


def update_relation_mapping(project_id: str, relation_name: str, mapping: dict):
    schema = get_project_schema(project_id)
    schema.setdefault("relations", {})[relation_name] = mapping
    save_project_schema(project_id, schema)


# --- Sync Helpers (Graph → DuckDB) ---

def _get_class_mapping(project_id: str, label: str) -> dict | None:
    schema = get_project_schema(project_id)
    mapping = schema.get("classes", {}).get(label, {})
    return mapping if mapping.get("source") else None


def _get_relation_mapping(project_id: str, relation: str) -> dict | None:
    schema = get_project_schema(project_id)
    mapping = schema.get("relations", {}).get(relation, {})
    return mapping if mapping.get("source") else None


def _get_node_label(project_id: str, node_id: str) -> str | None:
    """Look up a node's label from the graph store."""
    store = _store(project_id)
    ns = _ns(project_id)
    class_prefix = f"{ns}c/"
    n = _node(project_id, node_id)
    for q in store.quads_for_pattern(n, RDF_TYPE, None, DG):
        cls = _val(q.object)
        if cls.startswith(class_prefix):
            return cls[len(class_prefix):]
    return None


def _sync_node_to_duckdb(project_id: str, node_id: str, label: str, properties: dict, op: str):
    """Sync a node operation to DuckDB. op: 'insert', 'update', 'delete'. Failures are logged only."""
    try:
        mapping = _get_class_mapping(project_id, label)
        if not mapping:
            return
        conn = _duckdb(project_id)
        source = mapping["source"]
        id_col = mapping.get("id_column", "id")
        col_map = mapping.get("column_mapping", {})
        safe_source = source.replace('"', '""')

        if op == "insert":
            cols = {id_col: node_id}
            for prop_key, col_name in col_map.items():
                if prop_key in properties:
                    cols[col_name] = properties[prop_key]
            col_names = ", ".join(f'"{c}"' for c in cols)
            placeholders = ", ".join("?" for _ in cols)
            conn.execute(
                f'INSERT INTO "{safe_source}" ({col_names}) VALUES ({placeholders})',
                list(cols.values()),
            )
            log.info(f"[{project_id}] Synced INSERT node '{node_id}' → {source}")

        elif op == "update":
            sets = {}
            for prop_key, col_name in col_map.items():
                if prop_key in properties:
                    sets[col_name] = properties[prop_key]
            if not sets:
                return
            set_clause = ", ".join(f'"{c}" = ?' for c in sets)
            conn.execute(
                f'UPDATE "{safe_source}" SET {set_clause} WHERE "{id_col}" = ?',
                list(sets.values()) + [node_id],
            )
            log.info(f"[{project_id}] Synced UPDATE node '{node_id}' → {source}")

        elif op == "delete":
            conn.execute(
                f'DELETE FROM "{safe_source}" WHERE "{id_col}" = ?',
                [node_id],
            )
            log.info(f"[{project_id}] Synced DELETE node '{node_id}' → {source}")

    except Exception as e:
        log.error(f"[{project_id}] Sync node '{node_id}' ({op}) failed: {e}")


def _sync_edge_to_duckdb(project_id: str, source_id: str, target_id: str, relation: str, op: str):
    """Sync an edge operation to DuckDB. op: 'insert', 'delete'. Failures are logged only."""
    try:
        mapping = _get_relation_mapping(project_id, relation)
        if not mapping:
            return
        conn = _duckdb(project_id)
        table = mapping["source"]
        src_col = mapping.get("source_column")
        tgt_col = mapping.get("target_column")
        if not src_col or not tgt_col:
            return
        safe_table = table.replace('"', '""')

        if op == "insert":
            conn.execute(
                f'INSERT INTO "{safe_table}" ("{src_col}", "{tgt_col}") VALUES (?, ?)',
                [source_id, target_id],
            )
            log.info(f"[{project_id}] Synced INSERT edge '{source_id}→{relation}→{target_id}' → {table}")

        elif op == "delete":
            conn.execute(
                f'DELETE FROM "{safe_table}" WHERE "{src_col}" = ? AND "{tgt_col}" = ?',
                [source_id, target_id],
            )
            log.info(f"[{project_id}] Synced DELETE edge '{source_id}→{relation}→{target_id}' → {table}")

    except Exception as e:
        log.error(f"[{project_id}] Sync edge '{source_id}→{relation}→{target_id}' ({op}) failed: {e}")


# --- Nodes ---

def add_node(project_id: str, node_id: str, label: str, properties: dict):
    store = _store(project_id)
    n = _node(project_id, node_id)
    c = _class(project_id, label)
    quads = [
        ox.Quad(n, RDF_TYPE, c, DG),
        ox.Quad(c, RDF_TYPE, RDFS_CLASS, DG),
        ox.Quad(c, RDFS_LABEL, ox.Literal(label), DG),
    ]
    for k, v in properties.items():
        quads.append(ox.Quad(n, _prop(project_id, k), ox.Literal(str(v)), DG))
    store.extend(quads)
    _sync_node_to_duckdb(project_id, node_id, label, properties, "insert")


def modify_node(project_id: str, node_id: str, properties: dict):
    store = _store(project_id)
    n = _node(project_id, node_id)
    for k, v in properties.items():
        p = _prop(project_id, k)
        for q in list(store.quads_for_pattern(n, p, None, DG)):
            store.remove(q)
        store.add(ox.Quad(n, p, ox.Literal(str(v)), DG))
    label = _get_node_label(project_id, node_id)
    if label:
        _sync_node_to_duckdb(project_id, node_id, label, properties, "update")


def delete_node(project_id: str, node_id: str):
    store = _store(project_id)
    n = _node(project_id, node_id)
    label = _get_node_label(project_id, node_id)
    for q in list(store.quads_for_pattern(n, None, None, DG)):
        store.remove(q)
    for q in list(store.quads_for_pattern(None, None, n, DG)):
        store.remove(q)
    if label:
        _sync_node_to_duckdb(project_id, node_id, label, {}, "delete")


# --- Edges ---

def add_edge(project_id: str, source: str, target: str, relation: str):
    store = _store(project_id)
    store.add(ox.Quad(_node(project_id, source), _rel(project_id, relation), _node(project_id, target), DG))
    _sync_edge_to_duckdb(project_id, source, target, relation, "insert")


def delete_edge(project_id: str, source: str, target: str, relation: str):
    store = _store(project_id)
    for q in list(store.quads_for_pattern(
        _node(project_id, source), _rel(project_id, relation), _node(project_id, target), DG
    )):
        store.remove(q)
    _sync_edge_to_duckdb(project_id, source, target, relation, "delete")


# --- Read (Graph) ---

def get_all_nodes(project_id: str) -> list[dict]:
    store = _store(project_id)
    ns = _ns(project_id)
    node_prefix = f"{ns}n/"
    class_prefix = f"{ns}c/"
    prop_prefix = f"{ns}p/"

    nodes: dict[str, dict] = {}
    for q in store.quads_for_pattern(None, RDF_TYPE, None, DG):
        s, o = _val(q.subject), _val(q.object)
        if s.startswith(node_prefix) and o.startswith(class_prefix):
            node_id = s[len(node_prefix):]
            label = o[len(class_prefix):]
            nodes[node_id] = {"id": node_id, "label": label, "properties": {}}

    for node_id in nodes:
        n = _node(project_id, node_id)
        for q in store.quads_for_pattern(n, None, None, DG):
            p = _val(q.predicate)
            if p.startswith(prop_prefix):
                nodes[node_id]["properties"][p[len(prop_prefix):]] = _val(q.object)

    return list(nodes.values())


def get_all_edges(project_id: str) -> list[dict]:
    store = _store(project_id)
    ns = _ns(project_id)
    node_prefix = f"{ns}n/"
    rel_prefix = f"{ns}r/"

    edges = []
    for q in store.quads_for_pattern(None, None, None, DG):
        s, p, o = _val(q.subject), _val(q.predicate), _val(q.object)
        if s.startswith(node_prefix) and p.startswith(rel_prefix) and o.startswith(node_prefix):
            edges.append({
                "source": s[len(node_prefix):],
                "relation": p[len(rel_prefix):],
                "target": o[len(node_prefix):],
            })
    return edges


def get_graph_schema(project_id: str) -> dict:
    store = _store(project_id)
    ns = _ns(project_id)
    node_prefix = f"{ns}n/"
    class_prefix = f"{ns}c/"
    rel_prefix = f"{ns}r/"
    prop_prefix = f"{ns}p/"

    labels: set[str] = set()
    relations: set[str] = set()
    props_by_label: dict[str, set] = {}

    for q in store.quads_for_pattern(None, RDF_TYPE, None, DG):
        s, o = _val(q.subject), _val(q.object)
        if s.startswith(node_prefix) and o.startswith(class_prefix):
            label = o[len(class_prefix):]
            labels.add(label)
            props_by_label.setdefault(label, set())

    for q in store.quads_for_pattern(None, None, None, DG):
        s, p, o = _val(q.subject), _val(q.predicate), _val(q.object)
        if p.startswith(rel_prefix):
            relations.add(p[len(rel_prefix):])
        if s.startswith(node_prefix) and p.startswith(prop_prefix):
            n = q.subject
            for q2 in store.quads_for_pattern(n, RDF_TYPE, None, DG):
                cls = _val(q2.object)
                if cls.startswith(class_prefix):
                    label = cls[len(class_prefix):]
                    props_by_label.setdefault(label, set()).add(p[len(prop_prefix):])

    return {
        "node_labels": sorted(labels),
        "relation_types": sorted(relations),
        "properties_by_label": {k: sorted(v) for k, v in props_by_label.items()},
    }


def sparql_query(project_id: str, sparql: str) -> dict:
    store = _store(project_id)
    result = store.query(sparql)

    if isinstance(result, ox.QuerySolutions):
        variables = [v.value for v in result.variables]
        rows = []
        for solution in result:
            row = {}
            for var in variables:
                try:
                    term = solution[var]
                    row[var] = term.value if term is not None else None
                except KeyError:
                    row[var] = None
            rows.append(row)
        return {"type": "select", "variables": variables, "rows": rows}
    elif isinstance(result, ox.QueryBoolean):
        return {"type": "ask", "result": bool(result)}
    else:
        return {"type": "construct", "triples": [
            {"s": _val(t.subject), "p": _val(t.predicate), "o": _val(t.object)} for t in result
        ]}


def apply_diff(project_id: str, diff: dict):
    for node in diff.get("add_nodes", []):
        add_node(project_id, node["id"], node["label"], node.get("properties", {}))
    for edge in diff.get("add_edges", []):
        add_edge(project_id, edge["source"], edge["target"], edge["relation"])
    for node in diff.get("modify_nodes", []):
        modify_node(project_id, node["id"], node.get("properties", {}))
    for edge in diff.get("delete_edges", []):
        delete_edge(project_id, edge["source"], edge["target"], edge["relation"])
    for node_id in diff.get("delete_nodes", []):
        delete_node(project_id, node_id)


# --- Import (DuckDB → Graph, no sync back) ---

def _add_node_no_sync(project_id: str, node_id: str, label: str, properties: dict):
    """Add node to graph only, skip DuckDB sync (used when importing from DuckDB)."""
    store = _store(project_id)
    n = _node(project_id, node_id)
    c = _class(project_id, label)
    quads = [
        ox.Quad(n, RDF_TYPE, c, DG),
        ox.Quad(c, RDF_TYPE, RDFS_CLASS, DG),
        ox.Quad(c, RDFS_LABEL, ox.Literal(label), DG),
    ]
    for k, v in properties.items():
        quads.append(ox.Quad(n, _prop(project_id, k), ox.Literal(str(v)), DG))
    store.extend(quads)


def _add_edge_no_sync(project_id: str, source: str, target: str, relation: str):
    """Add edge to graph only, skip DuckDB sync."""
    store = _store(project_id)
    store.add(ox.Quad(_node(project_id, source), _rel(project_id, relation), _node(project_id, target), DG))


def import_class_to_graph(project_id: str, class_name: str) -> dict:
    """Import table rows as graph nodes based on class mapping. Returns counts."""
    mapping = _get_class_mapping(project_id, class_name)
    if not mapping:
        raise ValueError(f"No table mapping for class '{class_name}'")
    conn = _duckdb(project_id)
    source = mapping["source"]
    id_col = mapping.get("id_column", "id")
    col_map = mapping.get("column_mapping", {})
    reverse_map = {v: k for k, v in col_map.items()}

    safe_source = source.replace('"', '""')
    rows = conn.execute(f'SELECT * FROM "{safe_source}"').fetchall()
    columns = [desc[0] for desc in conn.execute(f'SELECT * FROM "{safe_source}" LIMIT 0').description]

    added = 0
    for row in rows:
        row_dict = dict(zip(columns, row))
        node_id = str(row_dict.get(id_col, ""))
        if not node_id:
            continue
        properties = {}
        for col_name, value in row_dict.items():
            if col_name == id_col:
                continue
            prop_key = reverse_map.get(col_name, col_name)
            if value is not None:
                properties[prop_key] = str(value)
        _add_node_no_sync(project_id, node_id, class_name, properties)
        added += 1

    log.info(f"[{project_id}] Imported {added} nodes as '{class_name}' from {source}")
    return {"added": added}


def import_relation_to_graph(project_id: str, relation_name: str) -> dict:
    """Import table rows as graph edges based on relation mapping. Returns counts."""
    mapping = _get_relation_mapping(project_id, relation_name)
    if not mapping:
        raise ValueError(f"No table mapping for relation '{relation_name}'")
    conn = _duckdb(project_id)
    source = mapping["source"]
    src_col = mapping.get("source_column")
    tgt_col = mapping.get("target_column")
    if not src_col or not tgt_col:
        raise ValueError(f"Relation mapping for '{relation_name}' missing source_column or target_column")

    safe_source = source.replace('"', '""')
    rows = conn.execute(f'SELECT "{src_col}", "{tgt_col}" FROM "{safe_source}" WHERE "{src_col}" IS NOT NULL AND "{tgt_col}" IS NOT NULL').fetchall()

    added = 0
    for src_id, tgt_id in rows:
        _add_edge_no_sync(project_id, str(src_id), str(tgt_id), relation_name)
        added += 1

    log.info(f"[{project_id}] Imported {added} edges as '{relation_name}' from {source}")
    return {"added": added}


# --- DuckDB Operations ---

def duckdb_list_tables(project_id: str) -> list[dict]:
    conn = _duckdb(project_id)
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    result = []
    for (name,) in tables:
        count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        result.append({"name": name, "row_count": count})
    return result


def duckdb_table_schema(project_id: str, table_name: str) -> list[dict]:
    conn = _duckdb(project_id)
    cols = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
        [table_name],
    ).fetchall()
    return [{"column": c, "type": t} for c, t in cols]


def duckdb_query(project_id: str, sql: str) -> dict:
    conn = _duckdb(project_id)
    result = conn.execute(sql)
    if result.description:
        columns = [desc[0] for desc in result.description]
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return {"columns": columns, "rows": rows}
    return {"columns": [], "rows": []}


def duckdb_upload_csv(project_id: str, table_name: str, file_path: str) -> int:
    conn = _duckdb(project_id)
    safe_name = table_name.replace('"', '""')
    conn.execute(
        f'CREATE OR REPLACE TABLE "{safe_name}" AS SELECT * FROM read_csv_auto(?)',
        [file_path],
    )
    count = conn.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
    return count
