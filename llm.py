import re
import json
import anthropic
from dotenv import load_dotenv
from db import get_schema, sparql_query, get_all_nodes

load_dotenv()
client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-6"


def _extract_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _schema_text(schema: dict) -> str:
    lines = ["Current ontology schema:"]
    lines.append(f"  Node labels: {', '.join(schema['node_labels']) or '(none)'}")
    lines.append(f"  Relation types: {', '.join(schema['relation_types']) or '(none)'}")
    if schema["properties_by_label"]:
        lines.append("  Properties by label:")
        for label, props in schema["properties_by_label"].items():
            lines.append(f"    {label}: {', '.join(props)}")
    return "\n".join(lines)


def suggest_edits(project_id: str, content: str) -> dict:
    schema = get_schema(project_id)
    existing_ids = [n["id"] for n in get_all_nodes(project_id)]

    prompt = f"""{_schema_text(schema)}

Existing node IDs: {existing_ids or '(none)'}

User input / content to extract knowledge from:
{content}

Generate a JSON diff to add/modify/delete nodes and edges in the ontology graph.
Return ONLY valid JSON with this exact structure:
{{
  "add_nodes": [{{"id": "snake_case_id", "label": "ClassName", "properties": {{"key": "value"}}}}],
  "add_edges": [{{"source": "node_id", "target": "node_id", "relation": "relationName"}}],
  "modify_nodes": [{{"id": "existing_id", "properties": {{"key": "value"}}}}],
  "delete_nodes": ["node_id"],
  "delete_edges": [{{"source": "node_id", "target": "node_id", "relation": "relationName"}}]
}}

Rules:
- Reuse existing labels and relation types from the schema when semantically appropriate
- Node IDs must be unique snake_case (no spaces, use underscores), not duplicating existing IDs
- Label names and relation names must also use no spaces (PascalCase or camelCase)
- Only include operations that are needed
- Return ONLY the JSON, no explanation"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(_extract_json(response.content[0].text))


def nl_query(project_id: str, question: str) -> dict:
    schema = get_schema(project_id)
    ns = f"http://ontology.local/p/{project_id}/"

    prompt = f"""{_schema_text(schema)}

Graph URI patterns:
  Nodes:      {ns}n/{{id}}
  Classes:    {ns}c/{{Label}}
  Properties: {ns}p/{{key}}
  Relations:  {ns}r/{{relation}}

Prefixes available:
  PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

Question: {question}

Generate a SPARQL SELECT query to answer this question.
Return ONLY valid JSON: {{"sparql": "SELECT ... WHERE {{ ... }}"}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    result = json.loads(_extract_json(response.content[0].text))
    sparql = result["sparql"]

    try:
        query_result = sparql_query(project_id, sparql)
        return {"sparql": sparql, "result": query_result, "error": None}
    except Exception as e:
        return {"sparql": sparql, "result": None, "error": str(e)}
