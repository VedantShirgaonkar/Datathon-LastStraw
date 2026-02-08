# HR Voice Agent (Personalized Monthly Review)

This service generates **highly personalized monthly HR review questions** using:
- **Postgres** for structured employee/org data
- **Neo4j** for relationship context (team/project graph)
- **Pinecone** for semantic memory (RAG evidence)

It exposes HTTP endpoints for question-plan generation and a simple session-based conversation loop (text in/out). Audio STT/TTS can be layered on top by a client.

## Quickstart

```bash
cd Datathon-LastStraw

# Use the SINGLE root venv (already present in this repo)
source venv/bin/activate

# Install service deps into the root venv
python -m pip install -r services/hr_voice_agent/requirements.txt

# copy env template
cp services/hr_voice_agent/.env.example services/hr_voice_agent/.env

# run
python -m uvicorn --app-dir services/hr_voice_agent hr_voice_agent.app:app --host 0.0.0.0 --port 8081 --reload
```

Health check:
```bash
curl -s http://localhost:8081/healthz | python -m json.tool
```

## Endpoints

- `POST /hr/monthly-review/questions` → returns a question plan for a person+month
- `POST /hr/monthly-review/session` → creates a session and returns the first question
- `POST /hr/monthly-review/session/{session_id}/turn` → send transcript text, receive next question

### Real-time (WebSocket)

- `WS /ws/hr/monthly-review/session/{session_id}` → send transcript text, receive assistant question + TTS audio (WAV)

Message format:

Client → server:
```json
{"type": "turn", "transcript_text": "I shipped the auth refactor but got blocked on QA"}
```

Server → client:
```json
{"type": "assistant", "text": "...", "audio_wav_base64": "...", "done": false}
```

## Environment variables

See `.env.example` for all settings.

### Groq support

You can generate questions using Groq by setting:
- `LLM_PROVIDER=groq`
- `GROQ_API_KEY=...`

Note: Groq does not provide embeddings. If `EMBEDDING_PROVIDER=none`, the agent will still work (Postgres + Neo4j personalization), but Pinecone semantic retrieval will be skipped.

### Pinecone semantic retrieval (without OpenAI)

This repo’s Postgres includes an `embeddings` table (pgvector) with 1024-dim vectors for:
- `developer_profile` (employees)
- `project_doc` (projects)

To use **Groq for question generation** and still enable **Pinecone semantic retrieval**:

1) Set in `services/hr_voice_agent/.env`:
- `LLM_PROVIDER=groq`
- `GROQ_API_KEY=...`
- `EMBEDDING_PROVIDER=postgres`
- `PINECONE_INDEX=policy-index` (or any existing 1024-dim index in your Pinecone project)

2) Sync Postgres vectors into Pinecone (one-time / whenever data changes):

```bash
PYTHONPATH=services/hr_voice_agent python -m hr_voice_agent.tools.sync_pinecone --limit 1000
```

After that, `POST /hr/monthly-review/questions` will include Pinecone matches under evidence.

## Free TTS options

### Option A (macOS): built-in `say` (works immediately)

Set `TTS_BACKEND=macos_say`.

### Option B (Piper): free open-source voice models

1) Install Piper binary (one-time) and download any `.onnx` voice model.
2) Set:
	- `TTS_BACKEND=piper`
	- `PIPER_MODEL_PATH=/absolute/path/to/voice.onnx`

The service will return WAV bytes for the assistant responses.

## DB introspection (optional)

If you provide DB credentials, you can print a quick shape summary:

```bash
python -m hr_voice_agent.tools.introspect
```
