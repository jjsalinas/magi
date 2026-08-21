"""
MAGI DECISION SUPPORT SYSTEM
============================

FastAPI entrypoint for the MAGI deliberation system.

Endpoints:

    POST /api/decide
        Creates a MAGI session and starts deliberation in the
        background.

    GET /api/decide/{session_id}
        Returns the current live state of a MAGI session.

The frontend can poll the session endpoint while MELCHIOR,
BALTHASAR, and CASPER deliberate.

Run with:

    uvicorn app:app --reload
"""

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from magi.config import (
    MAX_RESPONSE_TOKENS,
    MAX_ROUNDS,
    MODEL_ID,
    OPEN_AI_API_KEY,
    OPEN_AI_BASE_URL,
    validate_environment,
)
from magi.engine import deliberate

# =============================================================
# PYTHON VERSION
# =============================================================

if sys.version_info[:2] != (3, 14):
    raise RuntimeError(
        f"This project requires Python 3.14, found {sys.version.split()[0]}"
    )


# =============================================================
# CLIENT
# =============================================================


def setup_client() -> AsyncOpenAI:
    """
    Validate the environment and create the OpenAI-compatible
    async client used by the MAGI engine.
    """

    print(f"\n{'=' * 60}\n MAGI SYSTEM INITIALIZATION\n{'=' * 60}")

    validate_environment()

    client = AsyncOpenAI(
        base_url=OPEN_AI_BASE_URL,
        api_key=OPEN_AI_API_KEY,
    )

    print("ENVIRONMENT ............ ONLINE")
    print(f"MODEL .................. {MODEL_ID}")
    print(f"DELIBERATION LIMIT ..... {MAX_ROUNDS} ROUNDS")
    print(f"RESPONSE TOKEN LIMIT .. {MAX_RESPONSE_TOKENS} TOKENS")
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
    title="MAGI",
    description=(
        "Three-personality binary deliberation system inspired by the Evangelion MAGI."
    ),
)


# =============================================================
# STATIC FILES
# =============================================================

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)


# =============================================================
# REQUEST MODEL
# =============================================================


class DecisionRequest(BaseModel):
    """
    Request body for a new MAGI deliberation.
    """

    question: str = Field(
        min_length=1,
        description=("The proposition the MAGI must evaluate as YES or NO."),
    )


# =============================================================
# SESSION STORAGE
# =============================================================

"""
In-memory MAGI sessions.

Example:

MAGI_SESSIONS["a81f42c1"] = {
    "status": "RUNNING",
    "question": "...",
    "state": {...},
    "error": None,
}

This is intentionally local and ephemeral.

Restarting the server destroys all sessions.
"""

MAGI_SESSIONS: dict[str, dict[str, Any]] = {}


# =============================================================
# STATE FACTORY
# =============================================================


def create_initial_state(
    session_id: str,
    question: str,
) -> dict[str, Any]:
    """
    Create the initial API-visible MAGI state.

    This mirrors the state structure produced by the engine.
    """

    return {
        "session_id": session_id,
        "question": question,
        "phase": "INITIALIZING",
        "round": 0,
        "max_rounds": MAX_ROUNDS,
        "decision": "PENDING",
        "determination": None,
        "consensus": False,
        "votes": {
            "yes": 0,
            "no": 0,
        },
        "members": [],
        "rounds": [],
    }


# =============================================================
# SESSION WORKER
# =============================================================


async def run_magi_session(
    session_id: str,
    question: str,
) -> None:
    """
    Run one MAGI deliberation in the background.

    The HTTP request that created the session returns immediately;
    this worker continues running asynchronously.
    """

    session = MAGI_SESSIONS.get(session_id)

    if session is None:
        return

    async def on_update(
        state: dict,
    ) -> None:
        """
        Receive live updates from the MAGI engine.

        The state is copied before being stored so the API does
        not retain a reference to an object currently being
        mutated by the engine.
        """

        session["state"] = {
            **state,
            "session_id": session_id,
        }

    try:
        session["status"] = "RUNNING"

        print(f"\n[SESSION {session_id}] MAGI DELIBERATION STARTED")

        state = await deliberate(
            client=client,
            question=question,
            on_update=on_update,
            session_id=session_id,
        )

        # -----------------------------------------------------
        # Final authoritative engine state.
        # -----------------------------------------------------

        session["state"] = {
            **state,
            "session_id": session_id,
        }

        session["status"] = "COMPLETE"

        print(f"\n[SESSION {session_id}] MAGI DELIBERATION COMPLETE")

        print(f"[SESSION {session_id}] DECISION: {state['decision']}")

        print(
            f"[SESSION {session_id}] "
            f"DETERMINATION: "
            f"{state.get('determination', 'UNKNOWN')}"
        )

    except asyncio.CancelledError:
        """
        Do not silently turn task cancellation into a normal
        MAGI failure.
        """

        session["status"] = "CANCELLED"

        print(f"\n[SESSION {session_id}] MAGI DELIBERATION CANCELLED")

        raise

    except Exception as exc:
        print(f"\n{'=' * 60}\n MAGI SESSION FAILURE\n{'=' * 60}")

        print(f"SESSION : {session_id}")

        print(f"ERROR   : {type(exc).__name__}: {exc}")

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
    Start a new MAGI deliberation.

    Returns immediately with a session ID.

    The client should poll:

        GET /api/decide/{session_id}

    until the session reaches COMPLETE or ERROR.
    """

    question = request.question.strip()

    if not question:
        return {"error": "No question supplied."}

    # ---------------------------------------------------------
    # Create session ID.
    # ---------------------------------------------------------
    session_id = uuid.uuid4().hex[:8]

    # ---------------------------------------------------------
    # Create initial state.
    # ---------------------------------------------------------
    initial_state = create_initial_state(
        session_id=session_id,
        question=question,
    )

    MAGI_SESSIONS[session_id] = {
        "status": "STARTING",
        "question": question,
        "state": initial_state,
        "error": None,
    }

    print(f"\n{'=' * 60}\n MAGI SESSION CREATED\n{'=' * 60}")

    print(f" SESSION : {session_id}")

    print(f" QUESTION: {question}")

    print("=" * 60)

    # ---------------------------------------------------------
    # Start background deliberation.
    # ---------------------------------------------------------
    asyncio.create_task(
        run_magi_session(
            session_id=session_id,
            question=question,
        )
    )

    # ---------------------------------------------------------
    # Return immediately.
    # ---------------------------------------------------------
    return {
        "session_id": session_id,
        "status": "STARTING",
        "question": question,
        "state": initial_state,
    }


# =============================================================
# GET SESSION
# =============================================================


@app.get("/api/decide/{session_id}")
async def get_decision(
    session_id: str,
):
    """
    Return the current state of a MAGI session.

    This endpoint is intentionally simple so a frontend can poll
    it repeatedly during deliberation.
    """

    session = MAGI_SESSIONS.get(session_id)

    if session is None:
        return {
            "error": "MAGI session not found.",
            "session_id": session_id,
        }

    state = session.get(
        "state",
        {},
    )

    response = {
        "session_id": session_id,
        "status": session["status"],
        "question": session["question"],
        "state": state,
        # -----------------------------------------------------
        # Convenience fields for the frontend.
        # -----------------------------------------------------
        "decision": state.get(
            "decision",
            "PENDING",
        ),
        "determination": state.get(
            "determination",
            None,
        ),
        "consensus": state.get(
            "consensus",
            False,
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

    # ---------------------------------------------------------
    # Error information.
    # ---------------------------------------------------------
    if session["status"] == "ERROR":
        response["error"] = session.get("error") or {
            "type": "UnknownError",
            "message": ("MAGI deliberation failed."),
        }

    return response


# =============================================================
# INDEX
# =============================================================


@app.get("/")
async def index():
    """
    Serve the MAGI frontend.
    """

    return FileResponse(Path(__file__).parent / "static" / "index.html")
