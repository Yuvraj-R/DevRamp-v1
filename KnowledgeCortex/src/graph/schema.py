"""Neo4j schema setup - constraints and indexes."""

from .neo4j_client import Neo4jClient


def setup_schema(client: Neo4jClient) -> None:
    """
    Set up the Neo4j schema with constraints and indexes.

    Node types:
        - Repository: A code repository
        - Module: Top-level directory/package in a repo
        - File: A source code file
        - Function: A function or method
        - Class: A class definition
        - Import: An import statement (links files)

    Relationship types:
        - CONTAINS: Repository -> Module -> File -> Function/Class
        - IMPORTS: File -> File (internal) or File -> ExternalDep
        - CALLS: Function -> Function
        - DEFINED_IN: Function/Class -> File
    """

    # Constraints (also create indexes)
    constraints = [
        # Repository
        "CREATE CONSTRAINT repo_id IF NOT EXISTS FOR (r:Repository) REQUIRE r.id IS UNIQUE",
        # Module
        "CREATE CONSTRAINT module_id IF NOT EXISTS FOR (m:Module) REQUIRE m.id IS UNIQUE",
        # File
        "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE f.id IS UNIQUE",
        # Function
        "CREATE CONSTRAINT function_id IF NOT EXISTS FOR (fn:Function) REQUIRE fn.id IS UNIQUE",
        # Class
        "CREATE CONSTRAINT class_id IF NOT EXISTS FOR (c:Class) REQUIRE c.id IS UNIQUE",
    ]

    # Additional indexes for common queries
    indexes = [
        "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
        "CREATE INDEX file_language IF NOT EXISTS FOR (f:File) ON (f.language)",
        "CREATE INDEX function_name IF NOT EXISTS FOR (fn:Function) ON (fn.name)",
        "CREATE INDEX class_name IF NOT EXISTS FOR (c:Class) ON (c.name)",
    ]

    print("Setting up Neo4j schema...")

    for constraint in constraints:
        try:
            client.run_write(constraint)
        except Exception as e:
            # Constraint might already exist
            if "already exists" not in str(e).lower():
                print(f"Warning: {e}")

    for index in indexes:
        try:
            client.run_write(index)
        except Exception as e:
            if "already exists" not in str(e).lower():
                print(f"Warning: {e}")

    print("Schema setup complete.")


def get_schema_info(client: Neo4jClient) -> dict:
    """Get information about the current schema."""
    constraints = client.run_query("SHOW CONSTRAINTS")
    indexes = client.run_query("SHOW INDEXES")
    return {
        "constraints": constraints,
        "indexes": indexes,
    }
