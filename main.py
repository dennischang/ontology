from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv
import logging
import traceback
import secrets
import db
import llm

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ontology")

AUTH_KEY = secrets.token_urlsafe(16)

app = FastAPI(title="Ontology Editor")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    key = request.query_params.get("key") or request.cookies.get("ontology_key")
    if key != AUTH_KEY:
        return Response("Unauthorized", status_code=401)
    response = await call_next(request)
    if request.query_params.get("key") == AUTH_KEY:
        response.set_cookie("ontology_key", AUTH_KEY, httponly=True, samesite="strict")
    return response


@app.get("/", response_class=HTMLResponse)
def root():
    return open("static/index.html").read()


# --- Projects ---

@app.get("/projects")
def list_projects():
    return db.list_projects()


class ProjectCreate(BaseModel):
    id: str


@app.post("/projects")
def create_project(body: ProjectCreate):
    db.create_project(body.id)
    return {"id": body.id}


@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    db.delete_project(project_id)
    return {"ok": True}


# --- Graph ---

@app.get("/projects/{project_id}/graph")
def get_graph(project_id: str):
    return {"nodes": db.get_all_nodes(project_id), "edges": db.get_all_edges(project_id)}


@app.get("/projects/{project_id}/schema")
def get_schema(project_id: str):
    return db.get_schema(project_id)


# --- Nodes ---

class NodeBody(BaseModel):
    id: str
    label: str
    properties: dict = {}


@app.post("/projects/{project_id}/nodes")
def add_node(project_id: str, body: NodeBody):
    db.add_node(project_id, body.id, body.label, body.properties)
    return {"ok": True}


class NodePatch(BaseModel):
    properties: dict


@app.patch("/projects/{project_id}/nodes/{node_id}")
def modify_node(project_id: str, node_id: str, body: NodePatch):
    db.modify_node(project_id, node_id, body.properties)
    return {"ok": True}


@app.delete("/projects/{project_id}/nodes/{node_id}")
def delete_node(project_id: str, node_id: str):
    db.delete_node(project_id, node_id)
    return {"ok": True}


# --- Edges ---

class EdgeBody(BaseModel):
    source: str
    target: str
    relation: str


@app.post("/projects/{project_id}/edges")
def add_edge(project_id: str, body: EdgeBody):
    db.add_edge(project_id, body.source, body.target, body.relation)
    return {"ok": True}


@app.delete("/projects/{project_id}/edges")
def delete_edge(project_id: str, source: str, target: str, relation: str):
    db.delete_edge(project_id, source, target, relation)
    return {"ok": True}


# --- LLM ---

class SuggestBody(BaseModel):
    content: str


@app.post("/projects/{project_id}/llm/suggest")
def llm_suggest(project_id: str, body: SuggestBody):
    try:
        log.info(f"[{project_id}] LLM suggest, content length={len(body.content)}")
        result = llm.suggest_edits(project_id, body.content)
        log.info(f"[{project_id}] LLM suggest OK: {list(result.keys())}")
        return result
    except Exception as e:
        log.error(f"[{project_id}] LLM suggest error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.post("/projects/{project_id}/llm/apply")
def llm_apply(project_id: str, diff: dict):
    db.apply_diff(project_id, diff)
    return {"ok": True}


# --- Query ---

class NLQueryBody(BaseModel):
    question: str


@app.post("/projects/{project_id}/query")
def nl_query(project_id: str, body: NLQueryBody):
    try:
        log.info(f"[{project_id}] NL query: {body.question!r}")
        result = llm.nl_query(project_id, body.question)
        log.info(f"[{project_id}] NL query OK, sparql={result.get('sparql','')[:80]}")
        return result
    except Exception as e:
        log.error(f"[{project_id}] NL query error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


class SparqlBody(BaseModel):
    sparql: str


@app.post("/projects/{project_id}/sparql")
def run_sparql(project_id: str, body: SparqlBody):
    try:
        log.info(f"[{project_id}] Raw SPARQL: {body.sparql}")
        result = db.sparql_query(project_id, body.sparql)
        log.info(f"[{project_id}] Raw SPARQL result: {result}")
        return result
    except Exception as e:
        log.error(f"[{project_id}] Raw SPARQL error: {e}")
        raise HTTPException(400, str(e))


if __name__ == "__main__":
    import uvicorn
    url = f"http://127.0.0.1:8000?key={AUTH_KEY}"
    log.info(f"Ontology Editor: {url}")
    print(f"\n  🔗 Open: {url}\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
