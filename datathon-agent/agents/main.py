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
from agents.utils.streaming import render_stream_to_console, StreamEvent
from agents.supervisor import get_supervisor

logger = get_logger(__name__, "MAIN")


def run_interactive():
    """Run the agent in interactive CLI mode with conversation memory."""
    print("\n" + "=" * 60)
    print("🤖 Engineering Intelligence Agent")
    print("=" * 60)
    print("Ask questions about your engineering organization.")
    print("Conversations are remembered within a thread.")
    print()
    print("Commands:")
    print("  /new [title]   — Start a new conversation thread")
    print("  /threads       — List all threads")
    print("  /switch <id>   — Switch to a different thread")
    print("  /thread        — Show current thread info")
    print("  /delete <id>   — Delete a thread")
    print("  help           — Show example queries")
    print("  exit / quit    — End session")
    print("=" * 60 + "\n")
    
    supervisor = get_supervisor()
    supervisor.initialize()
    
    # Auto-create the first conversation thread
    thread_id = supervisor.new_thread("Session start")
    print(f"  💬 Thread started: {thread_id}\n")
    
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

            # ── Slash commands for thread management ────────────────
            if user_input.startswith("/"):
                thread_id = _handle_slash_command(user_input, supervisor, thread_id)
                continue
            
            print("\n🔄 Processing...\n")
            
            # Use the new StreamEvent-based streaming with console renderer
            response_text = render_stream_to_console(
                supervisor.stream_query(user_input, thread_id=thread_id),
                show_tools=True,
                show_routing=True,
                show_model=True,
                show_tokens=True,
            )
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


def _handle_slash_command(cmd: str, supervisor, current_thread_id: str) -> str:
    """
    Handle slash commands for thread management.
    Returns the (possibly updated) current thread_id.
    """
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "/new":
        title = arg or ""
        new_id = supervisor.new_thread(title)
        print(f"  💬 New thread: {new_id}" + (f" — '{title}'" if title else ""))
        return new_id

    elif command == "/threads":
        threads = supervisor.list_threads()
        if not threads:
            print("  (no threads)")
        else:
            print("\n  💬 Conversation Threads:")
            print("  " + "─" * 50)
            for t in threads:
                marker = " ◀" if t["thread_id"] == current_thread_id else ""
                print(
                    f"  {t['thread_id']}  │  {t['title']:<24}  │  "
                    f"msgs: {t['message_count']}{marker}"
                )
            print("  " + "─" * 50)
        return current_thread_id

    elif command == "/switch":
        if not arg:
            print("  ⚠️  Usage: /switch <thread_id>")
            return current_thread_id
        threads = {t["thread_id"]: t for t in supervisor.list_threads()}
        if arg in threads:
            print(f"  ↪ Switched to thread: {arg} — '{threads[arg]['title']}'")
            return arg
        else:
            print(f"  ⚠️  Thread '{arg}' not found. Use /threads to list.")
            return current_thread_id

    elif command == "/thread":
        threads = {t["thread_id"]: t for t in supervisor.list_threads()}
        info = threads.get(current_thread_id)
        if info:
            print(f"  💬 Current thread: {info['thread_id']}")
            print(f"     Title: {info['title']}")
            print(f"     Messages: {info['message_count']}")
            print(f"     Created: {info['created_at']}")
            print(f"     Last active: {info['last_active']}")
        else:
            print(f"  Thread: {current_thread_id} (no metadata)")
        return current_thread_id

    elif command == "/delete":
        if not arg:
            print("  ⚠️  Usage: /delete <thread_id>")
            return current_thread_id
        if arg == current_thread_id:
            print("  ⚠️  Cannot delete the active thread. Switch first.")
            return current_thread_id
        if supervisor.delete_thread(arg):
            print(f"  🗑️  Deleted thread: {arg}")
        else:
            print(f"  ⚠️  Thread '{arg}' not found.")
        return current_thread_id

    else:
        print(f"  ⚠️  Unknown command: {command}")
        print("  Available: /new, /threads, /switch, /thread, /delete")
        return current_thread_id


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
