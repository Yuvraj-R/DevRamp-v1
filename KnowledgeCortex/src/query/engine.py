"""RAG Query Engine with tool-based code retrieval."""

from dataclasses import dataclass, field
import json
from openai import OpenAI

from config import settings
from src.graph.neo4j_client import Neo4jClient
from src.embeddings.embedder import Embedder, SearchResult


@dataclass
class Source:
    """A source citation for an answer."""
    path: str
    node_type: str  # "file", "function", "class", "repository"
    relevance: float = 0.0
    summary: str = ""


@dataclass
class QueryResult:
    """Result from a query."""
    answer: str
    sources: list[Source] = field(default_factory=list)
    tokens_used: int = 0
    tool_calls_made: int = 0


# Tool definitions for OpenAI function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": "Get the full source code content of a file. Use this when you need to see the actual implementation details of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path of the file (e.g., 'src/core/execution.py')"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_function_code",
            "description": "Get the source code of a specific function. Use this when you need to see how a particular function is implemented.",
            "parameters": {
                "type": "object",
                "properties": {
                    "function_name": {
                        "type": "string",
                        "description": "The name of the function"
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional: the file path if you know it, to disambiguate functions with the same name"
                    }
                },
                "required": ["function_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_class_code",
            "description": "Get the source code of a specific class. Use this when you need to see a class definition and its methods.",
            "parameters": {
                "type": "object",
                "properties": {
                    "class_name": {
                        "type": "string",
                        "description": "The name of the class"
                    }
                },
                "required": ["class_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for code related to a concept or functionality. Returns relevant file summaries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for (e.g., 'authentication logic', 'database queries')"
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5)"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


class QueryEngine:
    """
    RAG-based query engine with tool-based code retrieval.

    The LLM can choose to request code when needed using function calling.
    This avoids wasting context on code that isn't relevant to the question.

    Flow:
        1. Embed the query and retrieve relevant summaries
        2. Send to LLM with summaries + available tools
        3. LLM may call tools to get more code context
        4. Loop until LLM produces final answer
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        embedder: Embedder = None,
        model: str = "gpt-5.2-2025-12-11",
        reasoning_level: str = "low",
        max_tool_calls: int = 10,
    ):
        self.neo4j = neo4j_client
        self.embedder = embedder or Embedder(neo4j_client)
        self.model = model
        self.reasoning_level = reasoning_level
        self.max_tool_calls = max_tool_calls
        self.openai = OpenAI(api_key=settings.openai_api_key)
        self._current_repo = None

    def query(
        self,
        question: str,
        repo_name: str,
        n_context: int = 5,
    ) -> QueryResult:
        """
        Answer a question about the codebase.

        The LLM receives summaries first, then can request actual code as needed.
        """
        self._current_repo = repo_name
        sources = []
        tool_calls_made = 0
        total_tokens = 0

        # 1. Retrieve relevant summaries via semantic search
        search_results = self.embedder.search(
            query=question,
            repo_name=repo_name,
            n_results=n_context,
        )

        # Build initial context from summaries
        context = self._build_summary_context(search_results)

        # Track sources
        for r in search_results:
            sources.append(Source(
                path=r.path,
                node_type=r.node_type,
                relevance=r.score,
                summary=r.summary[:200] + "..." if len(r.summary) > 200 else r.summary,
            ))

        # 2. Build initial messages
        system_prompt = f"""You are a helpful assistant that answers questions about the "{repo_name}" codebase.

You have access to summaries of the code. If you need to see actual source code to answer accurately, use the available tools to retrieve it.

Be specific and reference actual file paths and function/class names when relevant.

Available tools:
- get_file_content: Get full source code of a file
- get_function_code: Get source code of a specific function
- get_class_code: Get source code of a specific class
- search_code: Search for code related to a concept

Only request code if you genuinely need it to answer the question accurately. Don't request code just to be thorough."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"## Context (summaries):\n{context}\n\n## Question:\n{question}"}
        ]

        # 3. Agentic loop with tool calling
        while tool_calls_made < self.max_tool_calls:
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                reasoning_effort=self.reasoning_level,
            )

            total_tokens += response.usage.total_tokens
            assistant_message = response.choices[0].message

            # Add assistant message to history
            messages.append(assistant_message)

            # Check if we're done (no tool calls)
            if not assistant_message.tool_calls:
                # Final answer
                return QueryResult(
                    answer=assistant_message.content,
                    sources=sources,
                    tokens_used=total_tokens,
                    tool_calls_made=tool_calls_made,
                )

            # Process tool calls
            for tool_call in assistant_message.tool_calls:
                tool_calls_made += 1
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                # Execute tool
                result, new_source = self._execute_tool(function_name, arguments)

                # Track source
                if new_source:
                    sources.append(new_source)

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        # Max tool calls reached, get final answer
        response = self.openai.chat.completions.create(
            model=self.model,
            messages=messages + [{"role": "user", "content": "Please provide your final answer based on the information gathered."}],
            reasoning_effort=self.reasoning_level,
        )

        total_tokens += response.usage.total_tokens

        return QueryResult(
            answer=response.choices[0].message.content,
            sources=sources,
            tokens_used=total_tokens,
            tool_calls_made=tool_calls_made,
        )

    def _build_summary_context(self, search_results: list[SearchResult]) -> str:
        """Build context string from search results."""
        parts = []
        for i, r in enumerate(search_results, 1):
            parts.append(f"### {i}. {r.path} ({r.node_type})\n{r.summary}")
        return "\n\n".join(parts)

    def _execute_tool(self, function_name: str, arguments: dict) -> tuple[str, Source | None]:
        """Execute a tool and return the result."""

        if function_name == "get_file_content":
            return self._tool_get_file_content(arguments["file_path"])

        elif function_name == "get_function_code":
            return self._tool_get_function_code(
                arguments["function_name"],
                arguments.get("file_path")
            )

        elif function_name == "get_class_code":
            return self._tool_get_class_code(arguments["class_name"])

        elif function_name == "search_code":
            return self._tool_search_code(
                arguments["query"],
                arguments.get("n_results", 5)
            )

        return f"Unknown tool: {function_name}", None

    def _tool_get_file_content(self, file_path: str) -> tuple[str, Source | None]:
        """Get full content of a file from Neo4j."""
        result = self.neo4j.run_query("""
            MATCH (f:File)
            WHERE f.relative_path = $path OR f.relative_path ENDS WITH $path
            RETURN f.relative_path as path, f.content as content, f.language as language
            LIMIT 1
        """, {"path": file_path})

        if not result:
            return f"File not found: {file_path}", None

        file = result[0]
        content = file["content"] or "Content not available"

        # Truncate if too long
        if len(content) > 15000:
            content = content[:15000] + "\n\n... [truncated, file too large]"

        source = Source(
            path=file["path"],
            node_type="file",
        )

        return f"```{file['language']}\n{content}\n```", source

    def _tool_get_function_code(self, function_name: str, file_path: str = None) -> tuple[str, Source | None]:
        """Get code of a specific function from Neo4j."""
        if file_path:
            result = self.neo4j.run_query("""
                MATCH (fn:Function)-[:DEFINED_IN]->(f:File)
                WHERE fn.name = $name AND (f.relative_path = $path OR f.relative_path ENDS WITH $path)
                RETURN fn.name as name, fn.body as body, f.relative_path as file_path, f.language as language
                LIMIT 1
            """, {"name": function_name, "path": file_path})
        else:
            result = self.neo4j.run_query("""
                MATCH (fn:Function)-[:DEFINED_IN]->(f:File)
                WHERE fn.name = $name
                RETURN fn.name as name, fn.body as body, f.relative_path as file_path, f.language as language
                LIMIT 1
            """, {"name": function_name})

        if not result:
            return f"Function not found: {function_name}", None

        func = result[0]
        body = func["body"] or "Body not available"

        source = Source(
            path=f"{func['file_path']}::{func['name']}",
            node_type="function",
        )

        return f"Function `{func['name']}` in `{func['file_path']}`:\n```{func['language']}\n{body}\n```", source

    def _tool_get_class_code(self, class_name: str) -> tuple[str, Source | None]:
        """Get code of a specific class from Neo4j."""
        result = self.neo4j.run_query("""
            MATCH (c:Class)-[:DEFINED_IN]->(f:File)
            WHERE c.name = $name
            RETURN c.name as name, c.body as body, f.relative_path as file_path, f.language as language
            LIMIT 1
        """, {"name": class_name})

        if not result:
            return f"Class not found: {class_name}", None

        cls = result[0]
        body = cls["body"] or "Body not available"

        source = Source(
            path=f"{cls['file_path']}::{cls['name']}",
            node_type="class",
        )

        return f"Class `{cls['name']}` in `{cls['file_path']}`:\n```{cls['language']}\n{body}\n```", source

    def _tool_search_code(self, query: str, n_results: int = 5) -> tuple[str, Source | None]:
        """Search for code using semantic search."""
        results = self.embedder.search(
            query=query,
            repo_name=self._current_repo,
            n_results=n_results,
        )

        if not results:
            return f"No results found for: {query}", None

        parts = []
        for r in results:
            parts.append(f"- **{r.path}** (relevance: {r.score:.2f})\n  {r.summary[:200]}...")

        return f"Search results for '{query}':\n\n" + "\n\n".join(parts), None
