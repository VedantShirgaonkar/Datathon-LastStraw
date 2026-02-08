#!/usr/bin/env python3
"""
End-to-end HR Voice Review Demo

This script demonstrates the complete voice-based HR monthly review flow:
1. Creates a personalized review session for an employee
2. Plays each question aloud via TTS
3. Records your spoken response via microphone
4. Transcribes and processes the response
5. Continues until all questions are answered

Usage:
    cd Datathon-LastStraw
    source venv/bin/activate
    python services/hr_voice_agent/demo_voice_review.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

API_BASE = "http://127.0.0.1:8081"


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


def speak(text: str) -> None:
    """Speak text using macOS say command."""
    print(f"\n🔊 Assistant: {text}\n")
    try:
        subprocess.run(["say", "-v", "Samantha", text], check=True)
    except Exception as e:
        print(f"(TTS failed: {e})")


def record_audio(duration: int = 8) -> str:
    """Record audio from microphone and return the file path."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name

    print(f"🎤 Recording for {duration} seconds... (speak now)")
    print("   [Press Ctrl+C to stop early]")
    
    try:
        # Use sox (rec) for recording - install with: brew install sox
        subprocess.run(
            ["rec", "-q", wav_path, "trim", "0", str(duration)],
            check=True,
            timeout=duration + 2,
        )
    except subprocess.TimeoutExpired:
        pass
    except FileNotFoundError:
        # Fallback: use macOS's built-in recording via afrecord (if available)
        # or just ask for typed input
        print("⚠️  'rec' (sox) not found. Install with: brew install sox")
        print("   Falling back to typed input.")
        return None
    except KeyboardInterrupt:
        print("\n   [Recording stopped]")
    
    return wav_path


def transcribe_audio(wav_path: str) -> str:
    """Transcribe audio using Whisper (if installed) or return None."""
    try:
        # Try using whisper CLI
        result = subprocess.run(
            ["whisper", wav_path, "--model", "tiny", "--output_format", "txt", "--output_dir", "/tmp"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        txt_path = wav_path.replace(".wav", ".txt")
        if os.path.exists(f"/tmp/{os.path.basename(txt_path)}"):
            with open(f"/tmp/{os.path.basename(txt_path)}") as f:
                return f.read().strip()
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Whisper transcription failed: {e}")
    
    return None


def get_user_response(use_voice: bool = True) -> str:
    """Get user response via voice or typed input."""
    if use_voice:
        wav_path = record_audio(duration=10)
        if wav_path and os.path.exists(wav_path):
            transcript = transcribe_audio(wav_path)
            if transcript:
                print(f"📝 Transcribed: {transcript}")
                os.unlink(wav_path)
                return transcript
            os.unlink(wav_path)
    
    # Fallback to typed input
    print("⌨️  Type your response (or press Enter to skip):")
    return input("> ").strip()


def run_review(employee_email: str, month: str, use_voice: bool = True):
    """Run the complete HR review session."""
    print("\n" + "=" * 60)
    print("🎙️  HR VOICE REVIEW - End-to-End Demo")
    print("=" * 60)
    print(f"\nEmployee: {employee_email}")
    print(f"Month: {month}")
    print("-" * 60)

    # Step 1: Create session
    print("\n📋 Creating personalized review session...")
    try:
        session = api_post("/hr/monthly-review/session", {
            "person": {"email": employee_email},
            "month": month,
        })
    except Exception as e:
        print(f"❌ Failed to create session: {e}")
        print("   Make sure the server is running: ./scripts/run_hr_voice_agent.sh")
        return

    session_id = session["session_id"]
    person = session["person"]
    first_question = session["first_question"]

    print(f"\n✅ Session created for: {person.get('name', employee_email)}")
    print(f"   Role: {person.get('role', 'N/A')}")
    print(f"   Team: {person.get('team_name', 'N/A')}")
    print(f"   Session ID: {session_id[:8]}...")
    print("-" * 60)

    # Step 2: Start the Q&A loop
    current_question = first_question
    turn_count = 0
    max_turns = 10

    while turn_count < max_turns:
        turn_count += 1
        print(f"\n--- Question {turn_count} ---")
        
        # Speak the question
        speak(current_question)

        # Get user response
        response = get_user_response(use_voice=use_voice)
        
        if not response:
            response = "I'd like to skip this question."

        # Send response to API
        print("\n⏳ Processing response...")
        try:
            turn_result = api_post(f"/hr/monthly-review/session/{session_id}/turn", {
                "transcript_text": response,
            })
        except Exception as e:
            print(f"❌ API error: {e}")
            break

        current_question = turn_result["assistant_question"]
        done = turn_result["done"]
        summary = turn_result.get("running_summary", "")

        if done:
            speak(current_question)
            print("\n" + "=" * 60)
            print("✅ REVIEW COMPLETE!")
            print("=" * 60)
            if summary:
                print("\n📝 Session Summary:")
                print("-" * 40)
                # Print summary nicely wrapped
                words = summary.split()
                line = ""
                for word in words:
                    if len(line) + len(word) > 70:
                        print(f"   {line}")
                        line = word
                    else:
                        line = f"{line} {word}".strip()
                if line:
                    print(f"   {line}")
            print("\n🎉 Thank you for completing your monthly review!")
            break

    print("\n" + "=" * 60)


def main():
    print("\n" + "=" * 60)
    print("🎙️  HR VOICE REVIEW DEMO")
    print("=" * 60)
    
    # Check if server is running
    try:
        req = urllib.request.Request(f"{API_BASE}/healthz")
        with urllib.request.urlopen(req, timeout=5) as resp:
            pass
    except Exception:
        print("\n❌ Server not running!")
        print("   Start it with:")
        print("   cd /Users/newusername/Desktop/Datathon2026/Datathon-LastStraw")
        print("   ./scripts/run_hr_voice_agent.sh")
        sys.exit(1)

    print("\n✅ Server is running")
    
    # Show available employees
    print("\n📋 Available employees:")
    employees = [
        ("sarah.c@endurance.ai", "Sarah Chen", "Senior Frontend Engineer"),
        ("mike.r@endurance.ai", "Mike Ross", "Backend Lead"),
        ("alex.t@endurance.ai", "Alex Thompson", "DevOps Engineer"),
        ("jessica.l@endurance.ai", "Jessica Lee", "Product Designer"),
        ("david.k@endurance.ai", "David Kim", "QA Automation Engineer"),
    ]
    for i, (email, name, role) in enumerate(employees, 1):
        print(f"   {i}. {name} ({role})")

    print("\n" + "-" * 40)
    choice = input("Select employee (1-5) or enter email: ").strip()
    
    if choice.isdigit() and 1 <= int(choice) <= 5:
        email = employees[int(choice) - 1][0]
    elif "@" in choice:
        email = choice
    else:
        email = employees[0][0]
        print(f"   Using default: {email}")

    month = input("Enter month (YYYY-MM) [default: 2026-02]: ").strip() or "2026-02"
    
    # Check for voice input capability
    print("\n🎤 Checking voice input...")
    has_sox = subprocess.run(["which", "rec"], capture_output=True).returncode == 0
    has_whisper = subprocess.run(["which", "whisper"], capture_output=True).returncode == 0
    
    use_voice = False
    if has_sox and has_whisper:
        print("   ✅ Voice input available (sox + whisper)")
        use_voice_input = input("   Use voice input? (y/n) [default: n]: ").strip().lower()
        use_voice = use_voice_input == "y"
    else:
        if not has_sox:
            print("   ⚠️  sox not found (install: brew install sox)")
        if not has_whisper:
            print("   ⚠️  whisper not found (install: pip install openai-whisper)")
        print("   Using typed input instead.")

    print("\n" + "=" * 60)
    print("Starting review... (TTS will speak questions)")
    print("=" * 60)
    
    run_review(email, month, use_voice=use_voice)


if __name__ == "__main__":
    main()
