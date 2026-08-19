"""
MAGI DECISION SUPPORT SYSTEM — FastAPI entrypoint.

Serves the static frontend and exposes the MAGI session API.

POST /api/decide
    Starts a new MAGI deliberation and immediately returns a session ID.

GET /api/decide/{session_id}
    Returns the current state of that MAGI session.

The frontend can poll the session endpoint while the MAGI system
deliberates through its rounds.

Run with:
    uvicorn app:app --reload
"""

import asyncio
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from magi.config import (
    MAX_ROUNDS,
    MODEL_ID,
    OPEN_AI_API_KEY,
    OPEN_AI_BASE_URL,
    validate_environment,
)
from magi.engine import deliberate


if sys.version_info[:2] != (3, 14):
    raise RuntimeError(
        f"This project requires Python 3.14, "
        f"found {sys.version.split()[0]}"
    )


# =============================================================
# CLIENT
# =============================================================

def setup_client() -> AsyncOpenAI:
    print(
        f"\n{'=' * 60}\n"
        f" MAGI SYSTEM INITIALIZATION\n"
        f"{'=' * 60}\n"
    )

    validate_environment()

    client = AsyncOpenAI(
        base_url=OPEN_AI_BASE_URL,
        api_key=OPEN_AI_API_KEY,
    )

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


# =============================================================
# FASTAPI
# =============================================================

app = FastAPI(
    title="MAGI"
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)


# =============================================================
# REQUEST MODEL
# =============================================================

class DecisionRequest(BaseModel):
    question: str = Field(
        min_length=1
    )


# =============================================================
# LIVE SESSION STORAGE
# =============================================================

"""
Active and recently completed MAGI sessions.

The key is the session ID.

Example:

MAGI_SESSIONS["a81f42c1"] = {
    "status": "RUNNING",
    "question": "...",
    "state": {...},
    "error": None,
}

This is intentionally in-memory.

If the server restarts, the sessions disappear.

That is perfectly fine for this local MAGI application.
"""

MAGI_SESSIONS: dict[str, dict] = {}


# =============================================================
# SESSION WORKER
# =============================================================

async def run_magi_session(
    session_id: str,
    question: str,
) -> None:
    """
    Run the MAGI deliberation in the background.

    The HTTP request that created the session does not wait for
    this function to finish.
    """

    session = MAGI_SESSIONS.get(session_id)

    if session is None:
        return

    try:
        session["status"] = "RUNNING"

        print(
            f"\n[SESSION {session_id}] "
            f"MAGI deliberation started."
        )

        state = await deliberate(
            client,
            question,
        )

        session["state"] = state
        session["status"] = "COMPLETE"

        print(
            f"\n[SESSION {session_id}] "
            f"MAGI deliberation complete: "
            f"{state['decision']}"
        )

    except Exception as exc:
        print(
            f"\n{'=' * 60}\n"
            f" MAGI SESSION FAILURE\n"
            f"{'=' * 60}"
        )

        print(
            f"SESSION: {session_id}"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        print("=" * 60)

        session["status"] = "ERROR"
        session["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }


# =============================================================
# START SESSION
# =============================================================

@app.post("/api/decide")
async def decide(
    request: DecisionRequest,
):
    """
    Start a MAGI deliberation.

    IMPORTANT:
    This endpoint does NOT wait for the MAGI system to finish.

    It creates a session and returns immediately.
    """

    question = request.question.strip()

    if not question:
        return {
            "error": "No question supplied."
        }

    # ---------------------------------------------------------
    # Create session ID.
    # ---------------------------------------------------------

    session_id = uuid.uuid4().hex[:8]

    # ---------------------------------------------------------
    # Initial session state.
    # ---------------------------------------------------------

    MAGI_SESSIONS[session_id] = {
        "status": "STARTING",
        "question": question,
        "state": {
            "session_id": session_id,
            "question": question,
            "phase": "INITIALIZING",
            "round": 0,
            "max_rounds": MAX_ROUNDS,
            "decision": "PENDING",
            "votes": {
                "yes": 0,
                "no": 0,
            },
            "members": [],
            "rounds": [],
        },
        "error": None,
    }

    print(
        f"\n{'=' * 60}\n"
        f" MAGI SESSION CREATED\n"
        f"{'=' * 60}"
    )

    print(
        f" SESSION : {session_id}"
    )

    print(
        f" QUESTION: {question}"
    )

    print("=" * 60)

    # ---------------------------------------------------------
    # Start deliberation without blocking this request.
    # ---------------------------------------------------------

    asyncio.create_task(
        run_magi_session(
            session_id,
            question,
        )
    )

    # ---------------------------------------------------------
    # Return immediately.
    # ---------------------------------------------------------

    return {
        "session_id": session_id,
        "status": "STARTING",
        "question": question,
        "state": MAGI_SESSIONS[session_id]["state"],
    }


# =============================================================
# POLL SESSION
# =============================================================

@app.get("/api/decide/{session_id}")
async def get_decision(
    session_id: str,
):
    """
    Return the current state of a MAGI session.

    The frontend polls this endpoint while deliberation is running.
    """

    session = MAGI_SESSIONS.get(session_id)

    if session is None:
        return {
            "error": "MAGI session not found.",
            "session_id": session_id,
        }

    response = {
        "session_id": session_id,
        "status": session["status"],
        "question": session["question"],
        "state": session["state"],
    }

    # ---------------------------------------------------------
    # Completed MAGI state.
    # ---------------------------------------------------------

    state = session.get("state") or {}

    if state:
        response.update(
            {
                "decision": state.get(
                    "decision",
                    "PENDING",
                ),
                "votes": state.get(
                    "votes",
                    {
                        "yes": 0,
                        "no": 0,
                    },
                ),
                "members": state.get(
                    "members",
                    [],
                ),
                "rounds": state.get(
                    "rounds",
                    [],
                ),
            }
        )

    # ---------------------------------------------------------
    # Error information.
    # ---------------------------------------------------------

    if session["status"] == "ERROR":
        response["error"] = (
            session.get("error")
            or {
                "message": "MAGI deliberation failed."
            }
        )

    return response


# =============================================================
# INDEX
# =============================================================

@app.get("/")
async def index():
    return FileResponse(
        Path(__file__).parent
        / "static"
        / "index.html"
    )
