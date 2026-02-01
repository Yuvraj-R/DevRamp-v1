"""Graph builder - constructs Neo4j graph from parsed code."""

from pathlib import Path
from dataclasses import dataclass
import hashlib

from src.ingestion.discovery import discover_repo, RepoDiscovery
from src.ingestion.parser import CodeParser, ParsedFile
from src.graph.neo4j_client import Neo4jClient


def generate_id(*parts: str) -> str:
    """Generate a unique ID from parts."""
    combined = ":".join(str(p) for p in parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


@dataclass
class BuildStats:
    """Statistics from a graph build."""
    files_processed: int = 0
    files_skipped: int = 0
    functions_created: int = 0
    classes_created: int = 0
    imports_created: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class GraphBuilder:
    """
    Builds a Neo4j graph from a code repository.

    Creates nodes for:
        - Repository
        - Module (top-level directories)
        - File
        - Function
        - Class

    Creates edges for:
        - CONTAINS (Repository -> Module -> File -> Function/Class)
        - IMPORTS (File -> File or File -> external module)
        - DEFINED_IN (Function/Class -> File)
    """

    def __init__(self, client: Neo4jClient):
        self.client = client
        self.parser = CodeParser()

    def build_from_repo(self, repo_path: Path, repo_name: str | None = None) -> BuildStats:
        """
        Build the graph from a repository.

        Args:
            repo_path: Path to the repository root
            repo_name: Optional name for the repo (defaults to directory name)

        Returns:
            BuildStats with counts and any errors
        """
        stats = BuildStats()

        if repo_name is None:
            repo_name = repo_path.name

        # Discover repository structure
        print(f"Discovering repository: {repo_path}")
        discovery = discover_repo(repo_path)

        print(f"Found {len(discovery.files)} source files")
        print(f"Languages: {discovery.languages}")
        print(f"Modules: {[m.name for m in discovery.modules]}")

        # Create repository node
        repo_id = generate_id("repo", repo_name)
        self._create_repo_node(repo_id, repo_name, repo_path, discovery)

        # Create module nodes
        module_ids = {}
        for module_path in discovery.modules:
            module_id = generate_id("module", repo_name, module_path.name)
            module_ids[module_path.name] = module_id
            self._create_module_node(module_id, module_path, repo_id)

        # Process each file
        file_path_to_id = {}  # For resolving imports later

        for file_path in discovery.files:
            try:
                parsed = self.parser.parse_file(file_path)

                if parsed.parse_errors:
                    stats.errors.extend(parsed.parse_errors)
                    stats.files_skipped += 1
                    continue

                # Create file node
                relative_path = file_path.relative_to(repo_path)
                file_id = generate_id("file", repo_name, str(relative_path))
                file_path_to_id[str(relative_path)] = file_id

                # Determine parent module
                parent_module_id = None
                for module_path in discovery.modules:
                    if str(file_path).startswith(str(module_path)):
                        parent_module_id = module_ids.get(module_path.name)
                        break

                self._create_file_node(
                    file_id,
                    file_path,
                    relative_path,
                    parsed,
                    repo_id,
                    parent_module_id
                )

                # Create function nodes
                for func in parsed.functions:
                    func_id = generate_id("func", repo_name, str(relative_path), func.name, str(func.line_start))
                    self._create_function_node(func_id, func, file_id)
                    stats.functions_created += 1

                # Create class nodes
                for cls in parsed.classes:
                    cls_id = generate_id("class", repo_name, str(relative_path), cls.name)
                    self._create_class_node(cls_id, cls, file_id)
                    stats.classes_created += 1

                # Store imports for later resolution
                for imp in parsed.imports:
                    self._create_import_edge(file_id, imp, repo_name, file_path_to_id)
                    stats.imports_created += 1

                stats.files_processed += 1

            except Exception as e:
                stats.errors.append(f"Error processing {file_path}: {e}")
                stats.files_skipped += 1

        print(f"\nBuild complete:")
        print(f"  Files processed: {stats.files_processed}")
        print(f"  Files skipped: {stats.files_skipped}")
        print(f"  Functions: {stats.functions_created}")
        print(f"  Classes: {stats.classes_created}")
        print(f"  Imports: {stats.imports_created}")

        if stats.errors:
            print(f"  Errors: {len(stats.errors)}")

        return stats

    def _create_repo_node(self, repo_id: str, name: str, path: Path, discovery: RepoDiscovery):
        """Create a Repository node."""
        query = """
        MERGE (r:Repository {id: $id})
        SET r.name = $name,
            r.path = $path,
            r.primary_language = $primary_language,
            r.file_count = $file_count
        """
        self.client.run_write(query, {
            "id": repo_id,
            "name": name,
            "path": str(path),
            "primary_language": discovery.primary_language,
            "file_count": len(discovery.files),
        })

    def _create_module_node(self, module_id: str, module_path: Path, repo_id: str):
        """Create a Module node and link to Repository."""
        query = """
        MERGE (m:Module {id: $id})
        SET m.name = $name,
            m.path = $path
        WITH m
        MATCH (r:Repository {id: $repo_id})
        MERGE (r)-[:CONTAINS]->(m)
        """
        self.client.run_write(query, {
            "id": module_id,
            "name": module_path.name,
            "path": str(module_path),
            "repo_id": repo_id,
        })

    def _create_file_node(
        self,
        file_id: str,
        file_path: Path,
        relative_path: Path,
        parsed: ParsedFile,
        repo_id: str,
        module_id: str | None
    ):
        """Create a File node and link to Module or Repository."""
        # Read file content
        try:
            content = file_path.read_text(errors="replace")
        except Exception:
            content = None

        query = """
        MERGE (f:File {id: $id})
        SET f.name = $name,
            f.path = $path,
            f.relative_path = $relative_path,
            f.language = $language,
            f.lines_of_code = $lines_of_code,
            f.function_count = $function_count,
            f.class_count = $class_count,
            f.content = $content
        """
        self.client.run_write(query, {
            "id": file_id,
            "name": file_path.name,
            "path": str(file_path),
            "relative_path": str(relative_path),
            "language": parsed.language,
            "lines_of_code": parsed.lines_of_code,
            "function_count": len(parsed.functions),
            "class_count": len(parsed.classes),
            "content": content,
        })

        # Link to parent (Module or Repository)
        if module_id:
            self.client.run_write("""
                MATCH (m:Module {id: $module_id})
                MATCH (f:File {id: $file_id})
                MERGE (m)-[:CONTAINS]->(f)
            """, {"module_id": module_id, "file_id": file_id})
        else:
            self.client.run_write("""
                MATCH (r:Repository {id: $repo_id})
                MATCH (f:File {id: $file_id})
                MERGE (r)-[:CONTAINS]->(f)
            """, {"repo_id": repo_id, "file_id": file_id})

    def _create_function_node(self, func_id: str, func, file_id: str):
        """Create a Function node and link to File."""
        query = """
        MERGE (fn:Function {id: $id})
        SET fn.name = $name,
            fn.line_start = $line_start,
            fn.line_end = $line_end,
            fn.parameters = $parameters,
            fn.is_method = $is_method,
            fn.class_name = $class_name,
            fn.docstring = $docstring,
            fn.body = $body
        WITH fn
        MATCH (f:File {id: $file_id})
        MERGE (f)-[:CONTAINS]->(fn)
        MERGE (fn)-[:DEFINED_IN]->(f)
        """
        self.client.run_write(query, {
            "id": func_id,
            "name": func.name,
            "line_start": func.line_start,
            "line_end": func.line_end,
            "parameters": func.parameters,
            "is_method": func.is_method,
            "class_name": func.class_name,
            "docstring": func.docstring,
            "body": func.body,
            "file_id": file_id,
        })

    def _create_class_node(self, cls_id: str, cls, file_id: str):
        """Create a Class node and link to File."""
        query = """
        MERGE (c:Class {id: $id})
        SET c.name = $name,
            c.line_start = $line_start,
            c.line_end = $line_end,
            c.bases = $bases,
            c.docstring = $docstring,
            c.body = $body
        WITH c
        MATCH (f:File {id: $file_id})
        MERGE (f)-[:CONTAINS]->(c)
        MERGE (c)-[:DEFINED_IN]->(f)
        """
        self.client.run_write(query, {
            "id": cls_id,
            "name": cls.name,
            "line_start": cls.line_start,
            "line_end": cls.line_end,
            "bases": cls.bases,
            "docstring": cls.docstring,
            "body": cls.body,
            "file_id": file_id,
        })

    def _create_import_edge(self, file_id: str, imp, repo_name: str, file_path_to_id: dict):
        """Create import relationships."""
        # Try to resolve to an internal file
        # This is a simplified resolution - real resolution would need language-specific logic

        # For now, just store the import as a property on an IMPORTS edge
        # We create a virtual "ExternalModule" node for external imports

        module_name = imp.module
        if not module_name:
            return

        # Check if it's an internal import (starts with . or matches a known file)
        is_internal = module_name.startswith(".")

        if is_internal:
            # Relative import - would need proper resolution
            # For MVP, just note it
            pass
        else:
            # Create or match external module node
            ext_id = generate_id("ext", module_name)
            query = """
            MERGE (e:ExternalModule {id: $ext_id})
            SET e.name = $name
            WITH e
            MATCH (f:File {id: $file_id})
            MERGE (f)-[:IMPORTS {names: $names}]->(e)
            """
            self.client.run_write(query, {
                "ext_id": ext_id,
                "name": module_name,
                "file_id": file_id,
                "names": imp.names,
            })

    def clear_repo(self, repo_name: str):
        """Clear all nodes for a specific repository."""
        repo_id = generate_id("repo", repo_name)
        # This is a simplified clear - in production you'd want cascading deletes
        self.client.run_write("""
            MATCH (r:Repository {id: $repo_id})-[*]->(n)
            DETACH DELETE n
        """, {"repo_id": repo_id})
        self.client.run_write("""
            MATCH (r:Repository {id: $repo_id})
            DETACH DELETE r
        """, {"repo_id": repo_id})
