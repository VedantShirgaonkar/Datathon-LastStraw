from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from hr_voice_agent.clients.neo4j_client import Neo4jClient
from hr_voice_agent.clients.pinecone_client import PineconeClient
from hr_voice_agent.clients.postgres_client import PostgresClient
from hr_voice_agent.config import get_settings
from hr_voice_agent.models import (
    CreateSessionRequest,
    CreateSessionResponse,
    MonthlyReviewQuestionsRequest,
    MonthlyReviewQuestionsResponse,
    SessionTurnRequest,
    SessionTurnResponse,
    TTSRequest,
)
from hr_voice_agent.services.context_builder import build_context
from hr_voice_agent.services.openai_client import embed_text, generate_questions_json, get_async_llm
from hr_voice_agent.services.question_generator import SYSTEM_PROMPT, build_user_prompt, parse_questions
from hr_voice_agent.services.session_logic import apply_turn, create_session
from hr_voice_agent.services.session_store import InMemorySessionStore
from hr_voice_agent.services.tts import TTSError, build_tts_backend


app = FastAPI(title="HR Voice Agent", version="0.1.0")

# Allow CORS for Swagger UI and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_store = InMemorySessionStore()


@app.get("/healthz")
def healthz():
    return {"ok": True}


async def _get_postgres_pool():
    settings = get_settings()
    if not settings.postgres_enabled():
        return None
    # Create a pool per request is not ideal, but keeps this hackathon service simple.
    # If you want, we can add FastAPI lifespan hooks for a shared pool.
    return await PostgresClient(settings.postgres_dsn).connect()


def _get_neo4j() -> Optional[Neo4jClient]:
    s = get_settings()
    if not s.neo4j_enabled():
        return None
    return Neo4jClient(uri=s.neo4j_uri, username=s.neo4j_username, password=s.neo4j_password, database=s.neo4j_database)


def _get_pinecone() -> Optional[PineconeClient]:
    s = get_settings()
    if not s.pinecone_enabled():
        return None
    return PineconeClient(api_key=s.pinecone_api_key, index_name=s.pinecone_index)


def _get_tts():
    s = get_settings()
    return build_tts_backend(
        backend_name=s.tts_backend,
        piper_binary=s.piper_binary,
        piper_model_path=s.piper_model_path,
        piper_speaker_id=s.piper_speaker_id,
    )


@app.post("/hr/tts")
def tts(req: TTSRequest):
    """Synthesize assistant audio (WAV).

    This is intentionally simple: it lets a UI layer fetch audio
    for any text (including questions, summaries, etc.).
    """
    tts_backend = _get_tts()
    try:
        wav = tts_backend.synthesize_wav(req.text).wav_bytes
    except TTSError as e:
        raise HTTPException(status_code=501, detail=str(e))

    return Response(content=wav, media_type="audio/wav")


@app.post("/hr/monthly-review/questions", response_model=MonthlyReviewQuestionsResponse)
async def monthly_review_questions(req: MonthlyReviewQuestionsRequest):
    s = get_settings()
    top_k = int(req.top_k or s.default_top_k)
    max_q = int(req.max_questions or s.max_questions)

    if not req.person.employee_id and not req.person.email:
        raise HTTPException(status_code=400, detail="Provide person.employee_id or person.email")

    postgres_pool = await _get_postgres_pool()
    neo4j = _get_neo4j()
    pinecone = _get_pinecone()

    try:
        if not s.llm_enabled():
            raise HTTPException(
                status_code=500,
                detail="LLM not configured. Set LLM_PROVIDER=openai with OPENAI_API_KEY or LLM_PROVIDER=groq with GROQ_API_KEY",
            )

        if (s.llm_provider or "").strip().lower() == "groq":
            llm = get_async_llm(provider="groq", api_key=s.groq_api_key)
            llm_model = s.groq_model
        else:
            llm = get_async_llm(provider="openai", api_key=s.openai_api_key)
            llm_model = s.openai_model

        embed_fn = None
        if s.embeddings_enabled():
            # embeddings are always OpenAI in this implementation
            openai_for_embeddings = get_async_llm(provider="openai", api_key=s.openai_api_key)

            async def _embed(text: str):
                return await embed_text(openai_for_embeddings, model=s.openai_embedding_model, text=text)

            embed_fn = _embed

        ctx = await build_context(
            month=req.month,
            employee_id=req.person.employee_id,
            email=req.person.email,
            top_k=top_k,
            postgres_pool=postgres_pool,
            neo4j=neo4j,
            pinecone=pinecone,
            pinecone_namespace_developer_profiles=s.pinecone_namespace_developer_profiles,
            pinecone_namespace_project_docs=s.pinecone_namespace_project_docs,
            embedding_provider=s.embedding_provider,
            openai_embed_fn=embed_fn,
        )

        user_prompt = build_user_prompt(person=ctx.person, month=ctx.month, evidence=ctx.evidence)
        raw = await generate_questions_json(
            llm,
            model=llm_model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_questions=max_q,
        )

        questions = parse_questions(raw)
        if not questions:
            raise HTTPException(status_code=502, detail="LLM returned no questions")

        return MonthlyReviewQuestionsResponse(
            person=ctx.person,
            month=ctx.month,
            questions=questions,
            evidence_used=[
                {
                    "source": e["source"],
                    "title": e["title"],
                    "content": e["content"],
                    "metadata": e.get("metadata") or {},
                }
                for e in ctx.evidence
            ],
            warnings=ctx.warnings,
        )
    finally:
        if neo4j:
            neo4j.close()
        if postgres_pool:
            await postgres_pool.close()


@app.post("/hr/monthly-review/session", response_model=CreateSessionResponse)
async def create_monthly_review_session(req: CreateSessionRequest):
    # Create a question plan, then convert it into a session.
    plan = await monthly_review_questions(
        MonthlyReviewQuestionsRequest(person=req.person, month=req.month)
    )

    q_texts = [q.question for q in plan.questions]
    state = create_session(store=_store, person=plan.person, month=plan.month, questions=q_texts)

    first = q_texts[0] if q_texts else "How are you feeling about this month?"
    return CreateSessionResponse(session_id=state.session_id, first_question=first, month=plan.month, person=plan.person)


@app.post("/hr/monthly-review/session/{session_id}/turn", response_model=SessionTurnResponse)
async def session_turn(session_id: str, req: SessionTurnRequest):
    try:
        next_q, summary, done = apply_turn(store=_store, session_id=session_id, transcript_text=req.transcript_text)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionTurnResponse(
        session_id=session_id,
        assistant_question=next_q,
        running_summary=summary,
        done=done,
    )


@app.websocket("/ws/hr/monthly-review/session/{session_id}")
async def ws_monthly_review_session(websocket: WebSocket, session_id: str):
    """Real-time turn loop over WebSocket.

    Client sends JSON messages like:
      {"type":"turn","transcript_text":"..."}

    Server responds with:
      {"type":"assistant","text":"...","audio_wav_base64":"...","done":false}
    """

    await websocket.accept()
    tts_backend = _get_tts()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await websocket.send_text(json.dumps({"type": "error", "error": "Invalid JSON"}))
                continue

            if msg.get("type") != "turn":
                await websocket.send_text(json.dumps({"type": "error", "error": "Unsupported message type"}))
                continue

            transcript_text = str(msg.get("transcript_text") or "")
            try:
                next_q, summary, done = apply_turn(
                    store=_store,
                    session_id=session_id,
                    transcript_text=transcript_text,
                )
            except KeyError:
                await websocket.send_text(json.dumps({"type": "error", "error": "Session not found"}))
                continue

            audio_b64 = None
            try:
                audio_b64 = tts_backend.synthesize_wav(next_q).wav_base64()
            except TTSError:
                audio_b64 = None

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "text": next_q,
                        "audio_wav_base64": audio_b64,
                        "running_summary": summary,
                        "done": done,
                    }
                )
            )
    except WebSocketDisconnect:
        return
