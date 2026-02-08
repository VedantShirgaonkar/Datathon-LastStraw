from __future__ import annotations

import json
from typing import Any, Dict, List

from openai import AsyncOpenAI


GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def get_async_llm(*, provider: str, api_key: str) -> AsyncOpenAI:
    p = (provider or "").strip().lower()
    if p == "groq":
        return AsyncOpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
    return AsyncOpenAI(api_key=api_key)


async def embed_text(client: AsyncOpenAI, *, model: str, text: str) -> List[float]:
    res = await client.embeddings.create(model=model, input=text)
    return list(res.data[0].embedding)


async def generate_questions_json(
    client: AsyncOpenAI,
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_questions: int,
) -> Dict[str, Any]:
    schema_hint = {
        "questions": [
            {
                "question": "string",
                "category": "accomplishments|goals|blockers|collaboration|growth|wellbeing|feedback|alignment",
                "rationale": "string",
                "followups": ["string"],
            }
        ]
    }

    msg = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": user_prompt
            + "\n\nReturn STRICT JSON only with this shape (no markdown):\n"
            + json.dumps(schema_hint)
            + f"\nConstraints: produce 3..{max_questions} questions. Each question must be specific to the person/month context.",
        },
    ]

    resp = await client.chat.completions.create(
        model=model,
        messages=msg,
        temperature=0.4,
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content or "{}"
    return json.loads(content)
