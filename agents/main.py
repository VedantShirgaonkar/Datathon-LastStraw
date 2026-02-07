"""
Engineering Intelligence Agent - Main Entry Point
Interactive CLI and programmatic interface for the agent system.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.utils.logger import get_logger, PhaseLogger
from agents.utils.config import load_config
from agents.utils.db_clients import close_all_connections
from agents.supervisor import get_supervisor

logger = get_logger(__name__, "MAIN")


def run_interactive():
    """Run the agent in interactive CLI mode."""
    print("\n" + "=" * 60)
    print("🤖 Engineering Intelligence Agent")
    print("=" * 60)
    print("Ask questions about your engineering organization.")
    print("Type 'exit' or 'quit' to end the session.")
    print("Type 'help' for example queries.")
    print("=" * 60 + "\n")
    
    supervisor = get_supervisor()
    supervisor.initialize()
    
    while True:
        try:
            user_input = input("\n📝 Your question: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if user_input.lower() == 'help':
                print_help()
                continue
            
            print("\n🔄 Processing...\n")
            
            # Use streaming for better UX
            for event in supervisor.stream_query(user_input):
                if event.get("type") == "routing":
                    print(f"  ↪ Routing to: {event['agent']}")
                elif event.get("type") == "tool_request":
                    print(f"  🔧 Using tools: {', '.join(event['tools'])}")
                elif event.get("type") == "tool_result":
                    print(f"  ✓ Got result from: {event['tool']}")
                elif event.get("type") == "response":
                    print("\n" + "─" * 40)
                    print(f"\n🤖 Response:\n\n{event['content']}")
                    print("\n" + "─" * 40)
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


def run_single_query(query: str):
    """Run a single query and print the result."""
    logger.info(f"Running single query: {query}")
    
    supervisor = get_supervisor()
    supervisor.initialize()
    
    print("\n🔄 Processing query...\n")
    
    response = supervisor.query(query)
    
    print("─" * 60)
    print(f"\n🤖 Response:\n\n{response}")
    print("\n" + "─" * 60)
    
    return response


def print_help():
    """Print example queries."""
    print("""
📚 Example Queries:

DEVELOPER INFO:
  - "Who is Priya Sharma?"
  - "List all developers on the Platform Engineering team"
  - "What is Alex Kumar's current workload?"

PROJECT INFO:
  - "Tell me about the API Gateway project"
  - "What are the active high-priority projects?"
  - "Who is working on the Customer Dashboard?"

METRICS & ANALYTICS:
  - "What are the DORA metrics for API Gateway?"
  - "Show me developer activity for the last week"
  - "Which projects have the best deployment frequency?"

SKILLS & COLLABORATION:
  - "Find developers with Kubernetes expertise"
  - "Who does Priya collaborate with the most?"
  - "Who are the API experts in the organization?"

PLANNING & WORKLOAD:
  - "Which developers are overallocated?"
  - "What's the velocity of the Platform team?"
  - "Which projects are at risk?"
""")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Engineering Intelligence Agent - Query your engineering data using natural language"
    )
    parser.add_argument(
        "-q", "--query",
        type=str,
        help="Single query to run (non-interactive mode)"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Run in interactive mode (default if no query provided)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        with PhaseLogger(logger, "Configuration"):
            load_config("/Users/rahul/Desktop/Datathon/.env")
        
        if args.query:
            run_single_query(args.query)
        else:
            run_interactive()
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        close_all_connections()


if __name__ == "__main__":
    main()
