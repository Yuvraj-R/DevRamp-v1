#!/usr/bin/env python3
"""View and evaluate summaries in the knowledge base."""

import sys
sys.path.insert(0, '.')

from src.graph.neo4j_client import get_client


def print_separator():
    print("\n" + "=" * 80 + "\n")


def view_repo_summary(client, repo_name: str):
    """View repository-level summary."""
    result = client.run_query("""
        MATCH (r:Repository {name: $repo_name})
        RETURN r.summary as summary, r.primary_language as language, r.file_count as file_count
    """, {"repo_name": repo_name})

    if result and result[0]["summary"]:
        print(f"REPOSITORY: {repo_name}")
        print(f"Language: {result[0]['language']} | Files: {result[0]['file_count']}")
        print_separator()
        print(result[0]["summary"])
    else:
        print(f"No summary found for repository: {repo_name}")


def view_module_summaries(client, repo_name: str):
    """View module-level summaries."""
    result = client.run_query("""
        MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(m:Module)
        RETURN m.name as name, m.summary as summary
    """, {"repo_name": repo_name})

    print("MODULES:")
    print_separator()
    for m in result:
        print(f"📁 {m['name']}/")
        if m["summary"]:
            print(f"   {m['summary']}")
        else:
            print("   (no summary)")
        print()


def view_file_summaries(client, repo_name: str, path_filter: str = None, limit: int = 10):
    """View file-level summaries."""
    if path_filter:
        result = client.run_query("""
            MATCH (r:Repository {name: $repo_name})-[:CONTAINS*]->(f:File)
            WHERE f.summary IS NOT NULL AND f.relative_path CONTAINS $path_filter
            RETURN f.relative_path as path, f.summary as summary,
                   f.function_count as funcs, f.class_count as classes
            ORDER BY f.function_count DESC
            LIMIT $limit
        """, {"repo_name": repo_name, "path_filter": path_filter, "limit": limit})
    else:
        result = client.run_query("""
            MATCH (r:Repository {name: $repo_name})-[:CONTAINS*]->(f:File)
            WHERE f.summary IS NOT NULL
            RETURN f.relative_path as path, f.summary as summary,
                   f.function_count as funcs, f.class_count as classes
            ORDER BY f.function_count DESC
            LIMIT $limit
        """, {"repo_name": repo_name, "limit": limit})

    print(f"FILE SUMMARIES (top {limit} by function count):")
    if path_filter:
        print(f"Filter: {path_filter}")
    print_separator()

    for f in result:
        print(f"📄 {f['path']}")
        print(f"   Functions: {f['funcs']} | Classes: {f['classes']}")
        print(f"   {f['summary']}")
        print()


def view_summary_stats(client, repo_name: str):
    """View summary statistics."""
    stats = client.run_query("""
        MATCH (r:Repository {name: $repo_name})-[:CONTAINS*]->(f:File)
        RETURN
            count(f) as total_files,
            count(f.summary) as files_with_summaries,
            avg(size(f.summary)) as avg_summary_length
    """, {"repo_name": repo_name})[0]

    print("SUMMARY STATISTICS:")
    print_separator()
    print(f"Total files: {stats['total_files']}")
    print(f"Files with summaries: {stats['files_with_summaries']}")
    print(f"Average summary length: {int(stats['avg_summary_length'] or 0)} chars")


def main():
    client = get_client()
    repo_name = "LiveEngine"

    print("\n" + "=" * 80)
    print("   KNOWLEDGE BASE SUMMARY VIEWER")
    print("=" * 80)

    # 1. Repository summary
    print_separator()
    view_repo_summary(client, repo_name)

    # 2. Module summaries
    print_separator()
    view_module_summaries(client, repo_name)

    # 3. File summaries - strategies
    print_separator()
    view_file_summaries(client, repo_name, path_filter="strategies", limit=5)

    # 4. File summaries - core
    print_separator()
    view_file_summaries(client, repo_name, path_filter="core", limit=5)

    # 5. Stats
    print_separator()
    view_summary_stats(client, repo_name)

    client.close()


if __name__ == "__main__":
    main()
