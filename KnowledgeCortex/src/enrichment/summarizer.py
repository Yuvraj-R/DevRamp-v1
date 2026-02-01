"""LLM-based code summarization using OpenAI."""

from pathlib import Path
from dataclasses import dataclass
from openai import OpenAI

from config import settings
from src.graph.neo4j_client import Neo4jClient


@dataclass
class SummarizeStats:
    """Statistics from summarization run."""
    files_summarized: int = 0
    modules_summarized: int = 0
    repos_summarized: int = 0
    tokens_used: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class Summarizer:
    """
    Generate summaries for code at multiple levels using OpenAI.

    Levels:
        - File: What does this file do? Key functions/classes?
        - Module: What is this module responsible for? How do files relate?
        - Repository: What is this project? Architecture overview?
    """

    def __init__(
        self,
        client: Neo4jClient,
        model: str = "gpt-5-mini-2025-08-07",
        max_tokens: int = 1024,
    ):
        self.neo4j = client
        self.model = model
        self.max_tokens = max_tokens
        self.openai = OpenAI(api_key=settings.openai_api_key)

    def summarize_repo(self, repo_name: str, repo_path: Path | str) -> SummarizeStats:
        """
        Summarize an entire repository at all levels.

        Order: Files -> Modules -> Repository (bottom-up)
        """
        stats = SummarizeStats()
        repo_path = Path(repo_path)

        print(f"Starting summarization for {repo_name} using {self.model}...")

        # 1. Summarize files (that don't have summaries yet)
        files = self._get_files_to_summarize(repo_name)
        print(f"Found {len(files)} files to summarize")

        for i, file_info in enumerate(files):
            try:
                # Try direct path first
                file_path = repo_path / file_info["relative_path"]
                if not file_path.exists():
                    # Maybe relative_path includes repo name, try stripping first component
                    parts = file_info["relative_path"].split("/", 1)
                    if len(parts) > 1:
                        file_path = repo_path / parts[1]

                if not file_path.exists():
                    stats.errors.append(f"File not found: {file_info['relative_path']}")
                    continue

                print(f"  [{i+1}/{len(files)}] {file_info['relative_path']}...", end=" ", flush=True)

                summary, tokens = self._summarize_file(file_path, file_info)
                self._store_file_summary(file_info["id"], summary)

                stats.files_summarized += 1
                stats.tokens_used += tokens
                print(f"done ({tokens} tokens)")

            except Exception as e:
                stats.errors.append(f"Error summarizing {file_info['relative_path']}: {e}")
                print(f"error: {e}")

        # 2. Summarize modules
        modules = self._get_modules_to_summarize(repo_name)
        print(f"\nFound {len(modules)} modules to summarize")

        for module_info in modules:
            try:
                print(f"  Summarizing module: {module_info['name']}...", end=" ", flush=True)

                summary, tokens = self._summarize_module(module_info)
                self._store_module_summary(module_info["id"], summary)

                stats.modules_summarized += 1
                stats.tokens_used += tokens
                print(f"done ({tokens} tokens)")

            except Exception as e:
                stats.errors.append(f"Error summarizing module {module_info['name']}: {e}")
                print(f"error: {e}")

        # 3. Summarize repository
        print(f"\nSummarizing repository: {repo_name}...", end=" ", flush=True)
        try:
            summary, tokens = self._summarize_repository(repo_name)
            self._store_repo_summary(repo_name, summary)

            stats.repos_summarized = 1
            stats.tokens_used += tokens
            print(f"done ({tokens} tokens)")

        except Exception as e:
            stats.errors.append(f"Error summarizing repo: {e}")
            print(f"error: {e}")

        print(f"\nSummarization complete:")
        print(f"  Files: {stats.files_summarized}")
        print(f"  Modules: {stats.modules_summarized}")
        print(f"  Total tokens: {stats.tokens_used}")
        if stats.errors:
            print(f"  Errors: {len(stats.errors)}")

        return stats

    def _get_files_to_summarize(self, repo_name: str) -> list[dict]:
        """Get files that don't have summaries yet."""
        return self.neo4j.run_query("""
            MATCH (r:Repository {name: $repo_name})-[:CONTAINS*]->(f:File)
            WHERE f.summary IS NULL
            RETURN f.id as id, f.relative_path as relative_path,
                   f.language as language, f.function_count as function_count,
                   f.class_count as class_count, f.lines_of_code as loc
            ORDER BY f.lines_of_code DESC
        """, {"repo_name": repo_name})

    def _get_modules_to_summarize(self, repo_name: str) -> list[dict]:
        """Get modules that don't have summaries yet."""
        return self.neo4j.run_query("""
            MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(m:Module)
            WHERE m.summary IS NULL
            RETURN m.id as id, m.name as name
        """, {"repo_name": repo_name})

    def _call_llm(self, prompt: str) -> tuple[str, int]:
        """Call OpenAI API and return response + token count."""
        response = self.openai.chat.completions.create(
            model=self.model,
            max_completion_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        summary = response.choices[0].message.content
        tokens = response.usage.total_tokens

        return summary, tokens

    def _summarize_file(self, file_path: Path, file_info: dict) -> tuple[str, int]:
        """Generate a summary for a single file."""
        content = file_path.read_text(errors="replace")

        # Truncate if too long (keep ~8k chars to leave room for response)
        if len(content) > 8000:
            content = content[:8000] + "\n\n... [truncated]"

        # Get functions and classes for context
        functions = self.neo4j.run_query("""
            MATCH (f:File {id: $file_id})-[:CONTAINS]->(fn:Function)
            RETURN fn.name as name, fn.is_method as is_method, fn.class_name as class_name
        """, {"file_id": file_info["id"]})

        classes = self.neo4j.run_query("""
            MATCH (f:File {id: $file_id})-[:CONTAINS]->(c:Class)
            RETURN c.name as name, c.bases as bases
        """, {"file_id": file_info["id"]})

        func_list = ", ".join(f["name"] for f in functions) if functions else "none"
        class_list = ", ".join(f["name"] for f in classes) if classes else "none"

        prompt = f"""Analyze this {file_info['language']} file and provide a concise summary.

File: {file_info['relative_path']}
Lines of code: {file_info['loc']}
Classes: {class_list}
Functions: {func_list}

```{file_info['language']}
{content}
```

Provide a 2-4 sentence summary covering:
1. The primary purpose of this file
2. Key functionality it provides
3. Important classes/functions and what they do

Be specific and technical. Focus on WHAT it does, not HOW the code is structured."""

        return self._call_llm(prompt)

    def _summarize_module(self, module_info: dict) -> tuple[str, int]:
        """Generate a summary for a module based on its file summaries."""
        # Get all file summaries in this module
        files = self.neo4j.run_query("""
            MATCH (m:Module {id: $module_id})-[:CONTAINS]->(f:File)
            WHERE f.summary IS NOT NULL
            RETURN f.relative_path as path, f.summary as summary
            ORDER BY f.function_count DESC
            LIMIT 20
        """, {"module_id": module_info["id"]})

        if not files:
            return "No files with summaries found in this module.", 0

        file_summaries = "\n\n".join(
            f"**{f['path']}**\n{f['summary']}" for f in files
        )

        prompt = f"""Based on these file summaries, provide a module-level summary for the "{module_info['name']}" module.

{file_summaries}

Provide a 3-5 sentence summary covering:
1. The overall responsibility of this module
2. Key components and how they work together
3. What other parts of the system would use this module

Be specific about the module's role in the larger system."""

        return self._call_llm(prompt)

    def _summarize_repository(self, repo_name: str) -> tuple[str, int]:
        """Generate a repository-level summary."""
        # Get repo info
        repo_info = self.neo4j.run_query("""
            MATCH (r:Repository {name: $repo_name})
            RETURN r.primary_language as language, r.file_count as file_count
        """, {"repo_name": repo_name})[0]

        # Get module summaries
        modules = self.neo4j.run_query("""
            MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(m:Module)
            RETURN m.name as name, m.summary as summary
        """, {"repo_name": repo_name})

        # Get top external dependencies
        deps = self.neo4j.run_query("""
            MATCH (r:Repository {name: $repo_name})-[:CONTAINS*]->(f:File)-[:IMPORTS]->(e:ExternalModule)
            RETURN e.name as name, count(f) as count
            ORDER BY count DESC
            LIMIT 10
        """, {"repo_name": repo_name})

        module_summaries = "\n\n".join(
            f"**{m['name']}/**\n{m['summary'] or 'No summary yet'}" for m in modules
        ) if modules else "No modules found."

        dep_list = ", ".join(f"{d['name']} ({d['count']} files)" for d in deps) if deps else "none"

        prompt = f"""Provide a comprehensive summary of this code repository.

Repository: {repo_name}
Primary language: {repo_info['language']}
Total files: {repo_info['file_count']}
Key dependencies: {dep_list}

Module summaries:
{module_summaries}

Provide a 4-6 sentence summary covering:
1. What this project/application does (its purpose)
2. The high-level architecture
3. Key technologies and patterns used
4. Who would use this and why

This summary will be used to help new engineers understand the codebase quickly."""

        return self._call_llm(prompt)

    def _store_file_summary(self, file_id: str, summary: str):
        """Store summary on file node."""
        self.neo4j.run_write("""
            MATCH (f:File {id: $file_id})
            SET f.summary = $summary
        """, {"file_id": file_id, "summary": summary})

    def _store_module_summary(self, module_id: str, summary: str):
        """Store summary on module node."""
        self.neo4j.run_write("""
            MATCH (m:Module {id: $module_id})
            SET m.summary = $summary
        """, {"module_id": module_id, "summary": summary})

    def _store_repo_summary(self, repo_name: str, summary: str):
        """Store summary on repository node."""
        self.neo4j.run_write("""
            MATCH (r:Repository {name: $repo_name})
            SET r.summary = $summary
        """, {"repo_name": repo_name, "summary": summary})

    def get_repo_summary(self, repo_name: str) -> dict:
        """Get all summaries for a repository."""
        repo = self.neo4j.run_query("""
            MATCH (r:Repository {name: $repo_name})
            RETURN r.summary as summary, r.primary_language as language, r.file_count as file_count
        """, {"repo_name": repo_name})

        modules = self.neo4j.run_query("""
            MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(m:Module)
            RETURN m.name as name, m.summary as summary
        """, {"repo_name": repo_name})

        return {
            "repository": repo[0] if repo else None,
            "modules": modules,
        }
