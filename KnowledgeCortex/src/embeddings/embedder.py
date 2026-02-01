"""Embeddings and semantic search using LanceDB + OpenAI."""

from pathlib import Path
from dataclasses import dataclass
import lancedb
from openai import OpenAI

from config import settings
from src.graph.neo4j_client import Neo4jClient


@dataclass
class EmbedStats:
    """Statistics from embedding run."""
    files_embedded: int = 0
    repos_embedded: int = 0
    total_embedded: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass
class SearchResult:
    """A single search result."""
    node_type: str  # "file", "repository"
    node_id: str
    path: str  # relative_path for files, name for repos
    summary: str
    score: float  # similarity score (higher = more similar for LanceDB)


class Embedder:
    """
    Embed code summaries and enable semantic search.

    Uses:
        - OpenAI text-embedding-3-small for embeddings
        - LanceDB for vector storage (local/embedded)
    """

    EMBEDDING_DIM = 1536  # text-embedding-3-small dimension

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        embedding_model: str = "text-embedding-3-small",
        db_path: str = None,
    ):
        self.neo4j = neo4j_client
        self.embedding_model = embedding_model
        self.openai = OpenAI(api_key=settings.openai_api_key)

        # Set up LanceDB
        if db_path is None:
            db_path = str(Path(__file__).parent.parent.parent / "lancedb_data")

        self.db = lancedb.connect(db_path)
        self._ensure_table()

    def _ensure_table(self):
        """Ensure the embeddings table exists."""
        if "code_summaries" not in self.db.table_names():
            # Create empty table with schema
            import pyarrow as pa
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.EMBEDDING_DIM)),
                pa.field("type", pa.string()),
                pa.field("repo", pa.string()),
                pa.field("path", pa.string()),
                pa.field("node_id", pa.string()),
                pa.field("summary", pa.string()),
                pa.field("language", pa.string()),
                pa.field("funcs", pa.int32()),
            ])
            self.db.create_table("code_summaries", schema=schema)

        self.table = self.db.open_table("code_summaries")

    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for a single text."""
        response = self.openai.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding

    def _get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for multiple texts in one API call."""
        response = self.openai.embeddings.create(
            model=self.embedding_model,
            input=texts
        )
        return [item.embedding for item in response.data]

    def embed_repo(self, repo_name: str, batch_size: int = 50) -> EmbedStats:
        """
        Embed all summaries for a repository.

        Embeds:
            - File summaries
            - Repository summary
        """
        stats = EmbedStats()

        print(f"Embedding summaries for {repo_name}...")

        # 1. Get all file summaries
        files = self.neo4j.run_query("""
            MATCH (r:Repository {name: $repo_name})-[:CONTAINS*]->(f:File)
            WHERE f.summary IS NOT NULL
            RETURN f.id as id, f.relative_path as path, f.summary as summary,
                   f.language as language, f.function_count as funcs
        """, {"repo_name": repo_name})

        print(f"Found {len(files)} files with summaries")

        # Check which are already embedded
        try:
            existing = self.table.search().where(f"repo = '{repo_name}'", prefilter=True).limit(10000).to_list()
            existing_ids = {r["id"] for r in existing}
        except Exception:
            existing_ids = set()

        files_to_embed = [f for f in files if f"file:{f['id']}" not in existing_ids]
        print(f"  {len(files_to_embed)} need embedding ({len(existing_ids)} already done)")

        # Embed in batches
        for i in range(0, len(files_to_embed), batch_size):
            batch = files_to_embed[i:i + batch_size]

            try:
                # Prepare texts (summary + context)
                texts = [
                    f"File: {f['path']}\nLanguage: {f['language']}\n\n{f['summary']}"
                    for f in batch
                ]

                # Get embeddings
                embeddings = self._get_embeddings_batch(texts)

                # Prepare data for LanceDB
                data = [
                    {
                        "id": f"file:{f['id']}",
                        "vector": emb,
                        "type": "file",
                        "repo": repo_name,
                        "path": f['path'],
                        "node_id": f['id'],
                        "summary": f['summary'],
                        "language": f['language'] or "",
                        "funcs": f['funcs'] or 0,
                    }
                    for f, emb in zip(batch, embeddings)
                ]

                # Add to LanceDB
                self.table.add(data)

                stats.files_embedded += len(batch)
                print(f"  Embedded {stats.files_embedded}/{len(files_to_embed)} files")

            except Exception as e:
                stats.errors.append(f"Error embedding batch at {i}: {e}")
                print(f"  Error: {e}")

        # 2. Embed repository summary
        repo = self.neo4j.run_query("""
            MATCH (r:Repository {name: $repo_name})
            WHERE r.summary IS NOT NULL
            RETURN r.summary as summary
        """, {"repo_name": repo_name})

        if repo and repo[0]["summary"]:
            repo_id = f"repo:{repo_name}"
            if repo_id not in existing_ids:
                try:
                    embedding = self._get_embedding(
                        f"Repository: {repo_name}\n\n{repo[0]['summary']}"
                    )

                    self.table.add([{
                        "id": repo_id,
                        "vector": embedding,
                        "type": "repository",
                        "repo": repo_name,
                        "path": repo_name,
                        "node_id": repo_name,
                        "summary": repo[0]["summary"],
                        "language": "",
                        "funcs": 0,
                    }])

                    stats.repos_embedded = 1
                    print(f"  Embedded repository summary")

                except Exception as e:
                    stats.errors.append(f"Error embedding repo: {e}")

        stats.total_embedded = stats.files_embedded + stats.repos_embedded

        print(f"\nEmbedding complete:")
        print(f"  Files: {stats.files_embedded}")
        print(f"  Repository: {stats.repos_embedded}")
        print(f"  Total vectors: {self.table.count_rows()}")

        return stats

    def search(
        self,
        query: str,
        repo_name: str = None,
        n_results: int = 5,
        node_type: str = None,  # "file" or "repository"
    ) -> list[SearchResult]:
        """
        Semantic search over embedded summaries.

        Args:
            query: Natural language query
            repo_name: Optional filter by repository
            n_results: Number of results to return
            node_type: Optional filter by node type

        Returns:
            List of SearchResult objects, ordered by relevance
        """
        # Get query embedding
        query_embedding = self._get_embedding(query)

        # Build search
        search = self.table.search(query_embedding)

        # Apply filters
        filters = []
        if repo_name:
            filters.append(f"repo = '{repo_name}'")
        if node_type:
            filters.append(f"type = '{node_type}'")

        if filters:
            search = search.where(" AND ".join(filters), prefilter=True)

        # Execute search
        results = search.limit(n_results).to_list()

        # Convert to SearchResult objects
        return [
            SearchResult(
                node_type=r["type"],
                node_id=r["node_id"],
                path=r["path"],
                summary=r["summary"],
                score=1 - r["_distance"]  # Convert distance to similarity
            )
            for r in results
        ]

    def get_stats(self) -> dict:
        """Get statistics about the vector store."""
        return {
            "total_vectors": self.table.count_rows(),
            "table_name": "code_summaries",
        }
