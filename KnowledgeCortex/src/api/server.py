"""FastAPI server for KnowledgeCortex."""

from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import settings
from src.graph.neo4j_client import get_client
from src.graph.builder import GraphBuilder
from src.ingestion.clone import clone_repo
from src.enrichment.summarizer import Summarizer
from src.embeddings.embedder import Embedder
from src.query.engine import QueryEngine

# Initialize app
app = FastAPI(
    title="KnowledgeCortex API",
    description="API for ingesting, indexing, and querying code repositories",
    version="0.1.0",
)

# Global clients (initialized on startup)
neo4j_client = None
embedder = None
query_engine = None


@app.on_event("startup")
async def startup():
    global neo4j_client, embedder, query_engine
    neo4j_client = get_client()
    embedder = Embedder(neo4j_client)
    query_engine = QueryEngine(neo4j_client, embedder)


@app.on_event("shutdown")
async def shutdown():
    if neo4j_client:
        neo4j_client.close()


# ============================================================================
# Request/Response Models
# ============================================================================

class IngestRequest(BaseModel):
    repo_url: str  # Git URL or local path
    repo_name: str | None = None  # Optional custom name


class IngestResponse(BaseModel):
    status: str
    repo_name: str
    files_processed: int
    functions_created: int
    classes_created: int


class QueryRequest(BaseModel):
    question: str
    repo_name: str
    n_context: int = 5


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    tool_calls_made: int
    tokens_used: int


class SearchRequest(BaseModel):
    query: str
    repo_name: str
    n_results: int = 5


class SearchResponse(BaseModel):
    results: list[dict]


class CodeRequest(BaseModel):
    repo_name: str


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "KnowledgeCortex"}


@app.get("/repos")
async def list_repos():
    """List all indexed repositories."""
    repos = neo4j_client.run_query("""
        MATCH (r:Repository)
        RETURN r.name as name, r.primary_language as language,
               r.file_count as file_count, r.summary as summary
    """)
    return {"repositories": repos}


@app.post("/repos/ingest", response_model=IngestResponse)
async def ingest_repo(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Ingest a repository into the knowledge base.

    This clones the repo, parses all files, builds the graph,
    generates summaries, and creates embeddings.
    """
    # Clone or use local path
    if request.repo_url.startswith(("http://", "https://", "git@")):
        repo_path = clone_repo(request.repo_url)
    else:
        repo_path = Path(request.repo_url)
        if not repo_path.exists():
            raise HTTPException(status_code=400, detail=f"Path not found: {request.repo_url}")

    repo_name = request.repo_name or repo_path.name

    # Build graph
    builder = GraphBuilder(neo4j_client)
    stats = builder.build_from_repo(repo_path, repo_name)

    # Run summarization and embedding in background
    background_tasks.add_task(enrich_repo, repo_name, repo_path)

    return IngestResponse(
        status="ingested",
        repo_name=repo_name,
        files_processed=stats.files_processed,
        functions_created=stats.functions_created,
        classes_created=stats.classes_created,
    )


async def enrich_repo(repo_name: str, repo_path: Path):
    """Background task to run summarization and embedding."""
    try:
        summarizer = Summarizer(neo4j_client)
        summarizer.summarize_repo(repo_name, repo_path)

        embedder.embed_repo(repo_name)
    except Exception as e:
        print(f"Error enriching repo {repo_name}: {e}")


@app.get("/repos/{repo_name}")
async def get_repo(repo_name: str):
    """Get details about a specific repository."""
    repo = neo4j_client.run_query("""
        MATCH (r:Repository {name: $name})
        RETURN r.name as name, r.primary_language as language,
               r.file_count as file_count, r.summary as summary
    """, {"name": repo_name})

    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_name}")

    modules = neo4j_client.run_query("""
        MATCH (r:Repository {name: $name})-[:CONTAINS]->(m:Module)
        RETURN m.name as name, m.summary as summary
    """, {"name": repo_name})

    return {
        "repository": repo[0],
        "modules": modules,
    }


@app.get("/repos/{repo_name}/files")
async def list_files(repo_name: str, limit: int = 50):
    """List files in a repository."""
    files = neo4j_client.run_query("""
        MATCH (r:Repository {name: $name})-[:CONTAINS*]->(f:File)
        RETURN f.relative_path as path, f.language as language,
               f.lines_of_code as loc, f.function_count as functions,
               f.summary as summary
        ORDER BY f.function_count DESC
        LIMIT $limit
    """, {"name": repo_name, "limit": limit})

    return {"files": files}


@app.get("/repos/{repo_name}/file/{file_path:path}")
async def get_file(repo_name: str, file_path: str):
    """Get a specific file's content and metadata."""
    file = neo4j_client.run_query("""
        MATCH (f:File)
        WHERE f.relative_path = $path OR f.relative_path ENDS WITH $path
        RETURN f.relative_path as path, f.language as language,
               f.lines_of_code as loc, f.content as content,
               f.summary as summary
        LIMIT 1
    """, {"path": file_path})

    if not file:
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # Get functions in this file
    functions = neo4j_client.run_query("""
        MATCH (f:File)-[:CONTAINS]->(fn:Function)
        WHERE f.relative_path = $path OR f.relative_path ENDS WITH $path
        RETURN fn.name as name, fn.line_start as line_start,
               fn.line_end as line_end, fn.parameters as parameters,
               fn.is_method as is_method, fn.class_name as class_name
    """, {"path": file_path})

    # Get classes in this file
    classes = neo4j_client.run_query("""
        MATCH (f:File)-[:CONTAINS]->(c:Class)
        WHERE f.relative_path = $path OR f.relative_path ENDS WITH $path
        RETURN c.name as name, c.line_start as line_start,
               c.line_end as line_end, c.bases as bases
    """, {"path": file_path})

    return {
        "file": file[0],
        "functions": functions,
        "classes": classes,
    }


@app.get("/repos/{repo_name}/function/{function_name}")
async def get_function(repo_name: str, function_name: str):
    """Get a specific function's code."""
    func = neo4j_client.run_query("""
        MATCH (fn:Function)-[:DEFINED_IN]->(f:File)
        WHERE fn.name = $name
        RETURN fn.name as name, fn.body as body, fn.parameters as parameters,
               fn.docstring as docstring, fn.line_start as line_start,
               fn.line_end as line_end, f.relative_path as file_path
        LIMIT 1
    """, {"name": function_name})

    if not func:
        raise HTTPException(status_code=404, detail=f"Function not found: {function_name}")

    return {"function": func[0]}


@app.get("/repos/{repo_name}/class/{class_name}")
async def get_class(repo_name: str, class_name: str):
    """Get a specific class's code."""
    cls = neo4j_client.run_query("""
        MATCH (c:Class)-[:DEFINED_IN]->(f:File)
        WHERE c.name = $name
        RETURN c.name as name, c.body as body, c.bases as bases,
               c.docstring as docstring, c.line_start as line_start,
               c.line_end as line_end, f.relative_path as file_path
        LIMIT 1
    """, {"name": class_name})

    if not cls:
        raise HTTPException(status_code=404, detail=f"Class not found: {class_name}")

    return {"class": cls[0]}


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Ask a question about the codebase.

    Uses RAG with tool-based code retrieval. The LLM receives summaries
    first and can request actual code when needed.
    """
    result = query_engine.query(
        question=request.question,
        repo_name=request.repo_name,
        n_context=request.n_context,
    )

    return QueryResponse(
        answer=result.answer,
        sources=[{
            "path": s.path,
            "type": s.node_type,
            "relevance": s.relevance,
        } for s in result.sources],
        tool_calls_made=result.tool_calls_made,
        tokens_used=result.tokens_used,
    )


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Semantic search over the knowledge base.

    Returns relevant files/summaries based on the query.
    """
    results = embedder.search(
        query=request.query,
        repo_name=request.repo_name,
        n_results=request.n_results,
    )

    return SearchResponse(
        results=[{
            "path": r.path,
            "type": r.node_type,
            "summary": r.summary,
            "score": r.score,
        } for r in results]
    )


# ============================================================================
# Run server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
