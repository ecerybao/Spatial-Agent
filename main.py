#!/usr/bin/env python3
"""Interactive command-line entry point for SpatialAgent."""

import os
import sys

# Add the local src directory to Python path when running from source.
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.agent.spatial_agent import create_spatial_agent


def main():
    """Run an interactive SpatialAgent session."""
    print("SpatialAgent")
    print("=" * 50)

    try:
        agent = create_spatial_agent()
        print("Agent initialized successfully.")

        print("\nAvailable workflows:")
        print("1. Nearby search: find restaurants, attractions, and services near a place")
        print("2. Routing: answer route and navigation questions")
        print("3. Trip planning: optimize multi-stop visits")
        print("4. POI lookup: answer questions about a specific place")
        print("\nType 'quit' to exit.")

        while True:
            try:
                print("\n" + "-" * 50)
                question = input("Question: ").strip()

                if question.lower() in {"quit", "exit", "q"}:
                    print("Goodbye.")
                    break

                if not question:
                    continue

                print("\nProcessing...")
                result = agent.process_question(question)

                if result.get("error"):
                    print(f"Error: {result['error']}")
                    continue

                print(f"Intent: {result.get('intent', 'unknown')}")
                locations = result.get("locations", [])
                if locations:
                    print(f"Locations: {', '.join([loc['name'] for loc in locations])}")

                print("\nAnswer:")
                print(result["answer"])

            except KeyboardInterrupt:
                print("\nInterrupted. Goodbye.")
                break
            except Exception as exc:
                print(f"Error while processing question: {exc}")

    except Exception as exc:
        print(f"Initialization failed: {exc}")
        print("\nCheck the following:")
        print("1. API keys in your .env file")
        print("2. Network access")
        print("3. Dependencies installed with: pip install -r requirements.txt")


if __name__ == "__main__":
    main()
