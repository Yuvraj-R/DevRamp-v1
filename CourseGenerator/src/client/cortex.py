"""KnowledgeCortex API client.

This client wraps all calls to the KnowledgeCortex service.
CourseGenerator has ZERO direct access to codebases - everything
goes through this API.
"""

from dataclasses import dataclass
import httpx
from typing import Any

from config import settings


@dataclass
class RepoInfo:
    """Repository information from KnowledgeCortex."""
    name: str
    language: str | None
    file_count: int
    summary: str | None
    modules: list[dict]


@dataclass
class SearchResult:
    """Search result from semantic search."""
    path: str
    node_type: str
    summary: str
    score: float


@dataclass
class QueryResult:
    """Result from asking a question."""
    answer: str
    sources: list[dict]
    tool_calls_made: int
    tokens_used: int


@dataclass
class FileInfo:
    """File information including content."""
    path: str
    language: str | None
    loc: int
    content: str | None
    summary: str | None
    functions: list[dict]
    classes: list[dict]


@dataclass
class FunctionInfo:
    """Function information including code."""
    name: str
    body: str | None
    parameters: list[str] | None
    docstring: str | None
    line_start: int
    line_end: int
    file_path: str


@dataclass
class ClassInfo:
    """Class information including code."""
    name: str
    body: str | None
    bases: list[str] | None
    docstring: str | None
    line_start: int
    line_end: int
    file_path: str


class CortexClient:
    """
    Client for KnowledgeCortex API.

    All CourseGenerator's knowledge about codebases comes through this client.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.cortex_api_url
        self._client = httpx.Client(base_url=self.base_url, timeout=60.0)

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # =========================================================================
    # Repository endpoints
    # =========================================================================

    def list_repos(self) -> list[dict]:
        """List all indexed repositories."""
        response = self._client.get("/repos")
        response.raise_for_status()
        return response.json()["repositories"]

    def get_repo(self, repo_name: str) -> RepoInfo:
        """Get details about a repository."""
        response = self._client.get(f"/repos/{repo_name}")
        response.raise_for_status()
        data = response.json()
        return RepoInfo(
            name=data["repository"]["name"],
            language=data["repository"].get("language"),
            file_count=data["repository"].get("file_count", 0),
            summary=data["repository"].get("summary"),
            modules=data.get("modules", []),
        )

    def list_files(self, repo_name: str, limit: int = 50) -> list[dict]:
        """List files in a repository."""
        response = self._client.get(f"/repos/{repo_name}/files", params={"limit": limit})
        response.raise_for_status()
        return response.json()["files"]

    def get_file(self, repo_name: str, file_path: str) -> FileInfo:
        """Get a specific file's content and metadata."""
        response = self._client.get(f"/repos/{repo_name}/file/{file_path}")
        response.raise_for_status()
        data = response.json()
        return FileInfo(
            path=data["file"]["path"],
            language=data["file"].get("language"),
            loc=data["file"].get("loc", 0),
            content=data["file"].get("content"),
            summary=data["file"].get("summary"),
            functions=data.get("functions", []),
            classes=data.get("classes", []),
        )

    def get_function(self, repo_name: str, function_name: str) -> FunctionInfo:
        """Get a specific function's code."""
        response = self._client.get(f"/repos/{repo_name}/function/{function_name}")
        response.raise_for_status()
        data = response.json()["function"]
        return FunctionInfo(
            name=data["name"],
            body=data.get("body"),
            parameters=data.get("parameters"),
            docstring=data.get("docstring"),
            line_start=data.get("line_start", 0),
            line_end=data.get("line_end", 0),
            file_path=data.get("file_path", ""),
        )

    def get_class(self, repo_name: str, class_name: str) -> ClassInfo:
        """Get a specific class's code."""
        response = self._client.get(f"/repos/{repo_name}/class/{class_name}")
        response.raise_for_status()
        data = response.json()["class"]
        return ClassInfo(
            name=data["name"],
            body=data.get("body"),
            bases=data.get("bases"),
            docstring=data.get("docstring"),
            line_start=data.get("line_start", 0),
            line_end=data.get("line_end", 0),
            file_path=data.get("file_path", ""),
        )

    # =========================================================================
    # Query and Search
    # =========================================================================

    def query(
        self,
        question: str,
        repo_name: str,
        n_context: int = 5,
    ) -> QueryResult:
        """
        Ask a question about the codebase.

        This uses RAG with tool-based retrieval - the LLM can
        request actual code when needed.
        """
        response = self._client.post(
            "/query",
            json={
                "question": question,
                "repo_name": repo_name,
                "n_context": n_context,
            },
        )
        response.raise_for_status()
        data = response.json()
        return QueryResult(
            answer=data["answer"],
            sources=data["sources"],
            tool_calls_made=data["tool_calls_made"],
            tokens_used=data["tokens_used"],
        )

    def search(
        self,
        query: str,
        repo_name: str,
        n_results: int = 5,
    ) -> list[SearchResult]:
        """
        Semantic search over the knowledge base.

        Returns relevant files/summaries based on the query.
        """
        response = self._client.post(
            "/search",
            json={
                "query": query,
                "repo_name": repo_name,
                "n_results": n_results,
            },
        )
        response.raise_for_status()
        data = response.json()
        return [
            SearchResult(
                path=r["path"],
                node_type=r["type"],
                summary=r["summary"],
                score=r["score"],
            )
            for r in data["results"]
        ]

    # =========================================================================
    # Convenience methods for course generation
    # =========================================================================

    def get_architecture_overview(self, repo_name: str) -> dict[str, Any]:
        """
        Get high-level architecture information for a repository.

        Returns:
            - Repository summary
            - Module structure
            - Key files (most functions)
            - Entry points
        """
        repo = self.get_repo(repo_name)
        files = self.list_files(repo_name, limit=100)

        # Sort by function count to find key files
        key_files = sorted(
            [f for f in files if f.get("functions", 0) > 0],
            key=lambda f: f.get("functions", 0),
            reverse=True,
        )[:10]

        return {
            "repo_summary": repo.summary,
            "language": repo.language,
            "file_count": repo.file_count,
            "modules": repo.modules,
            "key_files": key_files,
        }

    def get_focus_area_context(
        self,
        repo_name: str,
        focus_area: str,
        n_results: int = 5,
    ) -> list[dict]:
        """
        Get context about a specific focus area.

        Combines search results with actual file summaries.
        """
        search_results = self.search(
            query=focus_area,
            repo_name=repo_name,
            n_results=n_results,
        )

        context = []
        for result in search_results:
            context.append({
                "path": result.path,
                "type": result.node_type,
                "summary": result.summary,
                "relevance": result.score,
            })

        return context
