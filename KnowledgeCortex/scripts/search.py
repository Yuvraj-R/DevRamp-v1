#!/usr/bin/env python3
"""Semantic search over the knowledge base."""

import sys
sys.path.insert(0, '.')

from src.graph.neo4j_client import get_client
from src.embeddings.embedder import Embedder


def main():
    client = get_client()
    embedder = Embedder(client)

    print("\n" + "=" * 60)
    print("  KNOWLEDGE BASE SEMANTIC SEARCH")
    print("=" * 60)
    print(f"\nVector store: {embedder.get_stats()['total_vectors']} embeddings")
    print("\nType a question about the codebase (or 'quit' to exit)")
    print("-" * 60)

    while True:
        try:
            query = input("\n🔍 Query: ").strip()

            if not query:
                continue
            if query.lower() in ('quit', 'exit', 'q'):
                print("Goodbye!")
                break

            results = embedder.search(query, repo_name='LiveEngine', n_results=5)

            print(f"\n📊 Top {len(results)} results:")
            print("-" * 60)

            for i, r in enumerate(results, 1):
                print(f"\n{i}. [{r.node_type.upper()}] {r.path}")
                print(f"   Relevance: {r.score:.3f}")
                print(f"   {r.summary[:200]}...")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

    client.close()


if __name__ == "__main__":
    main()
