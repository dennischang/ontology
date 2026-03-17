import pyoxigraph as ox
from pathlib import Path
from urllib.parse import quote, unquote

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
    """Percent-encode characters that are invalid in IRIs."""
    return quote(s, safe="-._~")


def _node(project_id: str, node_id: str) -> ox.NamedNode:
    return ox.NamedNode(f"{_ns(project_id)}n/{_iri_safe(node_id)}")


def _class(project_id: str, label: str) -> ox.NamedNode:
    return ox.NamedNode(f"{_ns(project_id)}c/{_iri_safe(label)}")


def _prop(project_id: str, key: str) -> ox.NamedNode:
    return ox.NamedNode(f"{_ns(project_id)}p/{_iri_safe(key)}")


def _rel(project_id: str, relation: str) -> ox.NamedNode:
    return ox.NamedNode(f"{_ns(project_id)}r/{_iri_safe(relation)}")


_stores: dict[str, ox.Store] = {}


def _store(project_id: str) -> ox.Store:
    if project_id not in _stores:
        _stores[project_id] = ox.Store(_store_path(project_id))
    return _stores[project_id]


# --- Projects ---

def list_projects() -> list[str]:
    if not PROJECTS_DIR.exists():
        return []
    return [d.name for d in sorted(PROJECTS_DIR.iterdir()) if d.is_dir()]


def create_project(project_id: str):
    _store(project_id)


def delete_project(project_id: str):
    import shutil
    _stores.pop(project_id, None)
    path = PROJECTS_DIR / project_id
    if path.exists():
        shutil.rmtree(path)


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


def modify_node(project_id: str, node_id: str, properties: dict):
    store = _store(project_id)
    n = _node(project_id, node_id)
    for k, v in properties.items():
        p = _prop(project_id, k)
        for q in list(store.quads_for_pattern(n, p, None, DG)):
            store.remove(q)
        store.add(ox.Quad(n, p, ox.Literal(str(v)), DG))


def delete_node(project_id: str, node_id: str):
    store = _store(project_id)
    n = _node(project_id, node_id)
    for q in list(store.quads_for_pattern(n, None, None, DG)):
        store.remove(q)
    for q in list(store.quads_for_pattern(None, None, n, DG)):
        store.remove(q)


# --- Edges ---

def add_edge(project_id: str, source: str, target: str, relation: str):
    store = _store(project_id)
    store.add(ox.Quad(_node(project_id, source), _rel(project_id, relation), _node(project_id, target), DG))


def delete_edge(project_id: str, source: str, target: str, relation: str):
    store = _store(project_id)
    for q in list(store.quads_for_pattern(
        _node(project_id, source), _rel(project_id, relation), _node(project_id, target), DG
    )):
        store.remove(q)


# --- Read ---

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
            node_id = unquote(s[len(node_prefix):])
            label = unquote(o[len(class_prefix):])
            nodes[node_id] = {"id": node_id, "label": label, "properties": {}}

    for node_id in nodes:
        n = _node(project_id, node_id)
        for q in store.quads_for_pattern(n, None, None, DG):
            p = _val(q.predicate)
            if p.startswith(prop_prefix):
                nodes[node_id]["properties"][unquote(p[len(prop_prefix):])] = _val(q.object)

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
                "source": unquote(s[len(node_prefix):]),
                "relation": unquote(p[len(rel_prefix):]),
                "target": unquote(o[len(node_prefix):]),
            })
    return edges


def get_schema(project_id: str) -> dict:
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
            label = unquote(o[len(class_prefix):])
            labels.add(label)
            props_by_label.setdefault(label, set())

    for q in store.quads_for_pattern(None, None, None, DG):
        s, p, o = _val(q.subject), _val(q.predicate), _val(q.object)
        if p.startswith(rel_prefix):
            relations.add(unquote(p[len(rel_prefix):]))
        if s.startswith(node_prefix) and p.startswith(prop_prefix):
            n = q.subject
            for q2 in store.quads_for_pattern(n, RDF_TYPE, None, DG):
                cls = _val(q2.object)
                if cls.startswith(class_prefix):
                    label = unquote(cls[len(class_prefix):])
                    props_by_label.setdefault(label, set()).add(unquote(p[len(prop_prefix):]))

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
                term = solution.get(var)
                row[var] = term.value if term is not None else None
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
