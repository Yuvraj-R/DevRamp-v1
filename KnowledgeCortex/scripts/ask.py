#!/usr/bin/env python3
"""Ask questions about the codebase using RAG with tool-based code retrieval."""

import sys
sys.path.insert(0, '.')

from src.graph.neo4j_client import get_client
from src.query.engine import QueryEngine

#knowledge cortext 
def main():
    client = get_client()
    engine = QueryEngine(client)

    print("\n" + "=" * 70)
    print("  KNOWLEDGE CORTEX - Ask Questions About the Codebase")
    print("=" * 70)
    print("\nModel: GPT-5.2 | Reasoning: low | Tool-based code retrieval: ON")
    print("The LLM will request actual code when needed.")
    print("Type a question (or 'quit' to exit)")
    print("-" * 70)

    while True:
        try:
            question = input("\n❓ Question: ").strip()

            if not question:
                continue
            if question.lower() in ('quit', 'exit', 'q'):
                print("Goodbye!")
                break

            print("\n🔍 Retrieving context...")

            result = engine.query(
                question=question,
                repo_name='LiveEngine',
                n_context=5,
            )

            print("\n" + "=" * 70)
            print("ANSWER:")
            print("=" * 70)
            print(result.answer)

            print("\n" + "-" * 70)
            print(f"📚 Sources ({len(result.sources)}):")
            for s in result.sources:
                print(f"   • [{s.node_type}] {s.path}")

            print(f"\n🔧 Tool calls: {result.tool_calls_made} | 📊 Tokens: {result.tokens_used}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

    client.close()


if __name__ == "__main__":
    main()
