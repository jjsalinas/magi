"""
MAGI DECISION SUPPORT SYSTEM — FastAPI entrypoint.

Serves the static frontend and exposes /api/decide, which runs a
multi-round, 3-persona LLM deliberation (see magi/engine.py) against
an OpenAI-compatible endpoint (e.g. LM Studio's local server).

Run with:  uvicorn app:app --reload
"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from magi.config import MAX_ROUNDS, MODEL_ID, OPEN_AI_API_KEY, OPEN_AI_BASE_URL, validate_environment
from magi.engine import deliberate

if sys.version_info[:2] != (3, 14):
    raise RuntimeError(f"This project requires Python 3.14, found {sys.version.split()[0]}")


def setup_client() -> AsyncOpenAI:
    print(f"\n{'=' * 60}\n MAGI SYSTEM INITIALIZATION\n{'=' * 60}\n")

    validate_environment()

    client = AsyncOpenAI(base_url=OPEN_AI_BASE_URL, api_key=OPEN_AI_API_KEY)

    print("ENVIRONMENT ............ ONLINE")
    print(f"MODEL .................. {MODEL_ID}")
    print(f"DELIBERATION LIMIT ..... {MAX_ROUNDS} ROUNDS")
    print("MELCHIOR ............... ONLINE")
    print("BALTHASAR .............. ONLINE")
    print("CASPER ................. ONLINE")
    print("\nMAGI SYSTEM READY.\n")

    return client


try:
    client = setup_client()
except ValueError as exc:
    print(exc)
    raise SystemExit(1)


app = FastAPI(title="MAGI")
app.mount("/static", StaticFiles(directory="static"), name="static")


class DecisionRequest(BaseModel):
    question: str = Field(min_length=1)


@app.post("/api/decide")
async def decide(request: DecisionRequest):
    question = request.question.strip()

    if not question:
        return {"error": "No question supplied."}

    try:
        state = await deliberate(client, question)
    except Exception as exc:
        print(f"\n{'=' * 60}\n MAGI SYSTEM FAILURE\n{'=' * 60}")
        print(f"{type(exc).__name__}: {exc}")
        print("=" * 60)

        return {"error": "MAGI deliberation failed.", "detail": str(exc)}

    return {
        "question": question,
        "decision": state["decision"],
        "votes": state["votes"],
        "members": state["members"],
        "state": {
            "session_id": state["session_id"],
            "phase": state["phase"],
            "round": state["round"],
            "max_rounds": state["max_rounds"],
        },
        "rounds": state["rounds"],
    }


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
