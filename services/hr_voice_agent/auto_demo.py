#!/usr/bin/env python3
"""
Automated HR Voice Review Demo - Runs without user input
Demonstrates the complete end-to-end flow with TTS audio output.
"""

import json
import subprocess
import sys
import time
import urllib.request

API_BASE = "http://127.0.0.1:8081"

# Simulated employee responses for the demo
DEMO_RESPONSES = [
    "I completed the new design system migration for the dashboard components. The team has been using the new component library and it's improved our consistency.",
    "The biggest challenge was coordinating with the backend team on API changes. We managed to resolve it through better documentation.",
    "I'm feeling pretty positive about my growth. I've learned a lot about TypeScript and improved my testing skills.",
    "I'd like to focus more on accessibility standards and maybe take on some mentoring responsibilities.",
    "I think the team communication has been great. The new standup format really helps.",
]


def api_post(endpoint: str, data: dict) -> dict:
    """Make a POST request to the API."""
    url = f"{API_BASE}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def speak(text: str, voice: str = "Samantha") -> None:
    """Speak text using macOS say command."""
    print(f"\n🔊 HR Assistant: {text}\n")
    try:
        # Use macOS say command with a nice voice - wait for it to complete
        subprocess.run(["say", "-v", voice, "-r", "180", text], check=True)
        time.sleep(1.5)  # Pause after speaking to avoid overlap
    except FileNotFoundError:
        print("   (TTS not available - macOS only)")
    except Exception as e:
        print(f"   (TTS error: {e})")


def speak_employee(text: str) -> None:
    """Speak employee response with different voice."""
    print(f"👤 Employee: {text}\n")
    try:
        subprocess.run(["say", "-v", "Alex", "-r", "190", text], check=True)
        time.sleep(1.0)  # Pause after employee speaks
    except:
        pass


def main():
    print("\n" + "=" * 70)
    print("🎙️  AUTOMATED HR VOICE REVIEW DEMO")
    print("    Complete end-to-end demonstration with voice synthesis")
    print("=" * 70)
    
    # Check server
    try:
        req = urllib.request.Request(f"{API_BASE}/healthz")
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception as e:
        print(f"\n❌ Server not running on {API_BASE}")
        print("   Start it first!")
        sys.exit(1)
    
    print("\n✅ Server connected")
    
    # Introduction
    speak("Welcome to your monthly performance review. I'm your HR assistant and I'll be guiding you through this session.", "Samantha")
    time.sleep(0.5)
    
    # Create session
    employee = "sarah.c@endurance.ai"
    month = "2026-02"
    
    print(f"\n📋 Creating review session for Sarah Chen ({employee})...")
    
    try:
        session = api_post("/hr/monthly-review/session", {
            "person": {"email": employee},
            "month": month,
        })
    except Exception as e:
        print(f"❌ Failed: {e}")
        sys.exit(1)
    
    session_id = session["session_id"]
    person = session["person"]
    first_question = session["first_question"]
    
    print(f"\n✅ Session created!")
    print(f"   Name: {person.get('name', 'Unknown')}")
    print(f"   Role: {person.get('role', 'Unknown')}")
    print(f"   Team: {person.get('team_name', 'Unknown')}")
    print("-" * 70)
    
    # Q&A Loop
    current_question = first_question
    turn = 0
    
    while turn < len(DEMO_RESPONSES):
        print(f"\n{'='*70}")
        print(f"📝 QUESTION {turn + 1}")
        print(f"{'='*70}")
        
        # Speak the question
        speak(current_question)
        
        time.sleep(1)
        
        # Simulate employee response
        response = DEMO_RESPONSES[turn]
        print(f"\n--- Simulated Employee Response ---")
        speak_employee(response)
        
        time.sleep(0.5)
        
        # Send to API
        print("\n⏳ Processing response...")
        try:
            result = api_post(f"/hr/monthly-review/session/{session_id}/turn", {
                "transcript_text": response,
            })
        except Exception as e:
            print(f"❌ Error: {e}")
            break
        
        current_question = result["assistant_question"]
        done = result["done"]
        summary = result.get("running_summary", "")
        
        if done:
            print(f"\n{'='*70}")
            print("✅ REVIEW COMPLETE!")
            print(f"{'='*70}")
            
            speak(current_question)
            
            if summary:
                print("\n📊 Session Summary:")
                print("-" * 50)
                # Word wrap
                words = summary.split()
                line = ""
                for word in words:
                    if len(line) + len(word) > 65:
                        print(f"   {line}")
                        line = word
                    else:
                        line = f"{line} {word}".strip()
                if line:
                    print(f"   {line}")
                print("-" * 50)
            
            speak("Thank you for completing your monthly review, Sarah. Your responses have been recorded and will be shared with your manager. Have a great day!", "Samantha")
            break
        
        turn += 1
    
    print("\n" + "=" * 70)
    print("🎉 DEMO COMPLETE!")
    print("=" * 70)
    print("\nThis demo showed:")
    print("  ✓ Personalized session creation with employee context")
    print("  ✓ AI-generated questions based on employee profile")
    print("  ✓ Text-to-speech for all assistant responses")
    print("  ✓ Natural conversation flow with follow-up questions")
    print("  ✓ Review completion with summary")
    print("\n")


if __name__ == "__main__":
    main()
