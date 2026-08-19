import asyncio
import json
import os
import sys
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel

## Python 3.14 check
if sys.version_info[:2] != (3, 14):
    raise RuntimeError(
        f"This project requires Python 3.14, found {sys.version.split()[0]}"
    )

## read .env file
load_dotenv()

app = FastAPI(title="MAGI")

MODEL = os.getenv("MODEL_ID")

# ---------------------------------------------------------
# TYPE DEFINITIONS
# ---------------------------------------------------------


class MemberConfig(TypedDict):
    """Defines the structure for a single MAGI member's configuration."""

    name: str
    role: str
    color: str
    prompt: str


# ---------------------------------------------------------
# MEMBER DEFINITIONS
# ---------------------------------------------------------


def define_melchior() -> MemberConfig:
    """Defines the configuration for Melchior."""
    return {
        "name": "MELCHIOR",
        "role": "LOGIC",
        "color": "#ff3030",
        "prompt": """
You are MELCHIOR, the logical and scientific member of a
three-part decision system.

Analyze the proposition using:
- logic
- evidence
- consistency
- probabilities
- expected outcomes

Do not focus primarily on emotions or morality.

You must make an independent decision.

Return ONLY valid JSON in this exact format:

{
  "decision": "YES" or "NO",
  "confidence": number between 0 and 1,
  "reason": "short explanation"
}
""",
    }


def define_balthasar() -> MemberConfig:
    """Defines the configuration for Balthasar."""
    return {
        "name": "BALTHASAR",
        "role": "PRACTICAL",
        "color": "#ff9d00",
        "prompt": """
You are BALTHASAR, the practical member of a three-part
decision system.

Analyze the proposition using:
- feasibility
- cost
- resources
- risks
- implementation difficulty
- likely real-world consequences

Think like an experienced engineer or operator.

You must make an independent decision.

Return ONLY valid JSON in this exact format:

{
  "decision": "YES" or "NO",
  "confidence": number between 0 and 1,
  "reason": "short explanation"
}
""",
    }


def define_casper() -> MemberConfig:
    """Defines the configuration for Casper."""
    return {
        "name": "CASPER",
        "role": "ETHICS",
        "color": "#ffe600",
        "prompt": """
You are CASPER, the ethical and human member of a
three-part decision system.

Analyze the proposition using:
- harm
- fairness
- autonomy
- responsibility
- human consequences
- ethical principles

You must make an independent decision.

Return ONLY valid JSON in this exact format:

{
  "decision": "YES" or "NO",
  "confidence": number between 0 and 1,
  "reason": "short explanation"
}
""",
    }


# ---------------------------------------------------------
# FINAL CONFIGURATION ASSEMBLY
# ---------------------------------------------------------

MAGI: dict[str, MemberConfig] = {
    "melchior": define_melchior(),
    "balthasar": define_balthasar(),
    "casper": define_casper(),
}


# ---------------------------------------------------------
# SETUP AND INITIALIZATION
# ---------------------------------------------------------


def setup_client():
    """Initializes the OpenAI client and validates required environment variables."""

    required_vars = {
        "MODEL_ID": "The model identifier (e.g., liquid/lfm2.5-1.2b)",
        "OPEN_AI_BASE_URL": "The base URL for the API endpoint",
        "OPEN_AI_API_KEY": "The API key or token",
    }

    print("--- Starting MAGI Setup ---")

    # Check for required variables
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value:
            raise ValueError(
                f"FATAL ERROR: Environment variable '{var}' is missing. {description}"
            )

    client = AsyncOpenAI(
        base_url=os.getenv("OPEN_AI_BASE_URL"),
        api_key=os.getenv("OPEN_AI_API_KEY"),
    )
    print("✅ Environment variables loaded successfully.")

    return client


try:
    client = setup_client()
except ValueError as e:
    print(e)
    exit(1)

# Maps URL /static to physical directory ./static
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------
# API
# ---------------------------------------------------------


class DecisionRequest(BaseModel):
    question: str


async def ask_magi(member: MemberConfig, question: str) -> dict:
    """Sends the prompt to the LLM and parses the JSON response."""
    response = await client.chat.completions.create(
        model=MODEL,
        temperature=0.4,
        messages=[
            {
                "role": "system",
                "content": member["prompt"],
            },
            {
                "role": "user",
                "content": f"""
Proposition to evaluate:

{question}

Make your decision independently.
""",
            },
        ],
    )

    text = response.choices[0].message.content.strip()

    # Handle models that put JSON inside ```json ... ```
    if text.startswith("```"):
        text = text.replace("```json", "")
        text = text.replace("```", "")
        text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        result = {
            "decision": "UNKNOWN",
            "confidence": 0,
            "reason": text,
        }

    # Ensure the result dictionary is correctly typed and augmented
    result["member"] = member["name"]
    result["role"] = member["role"]

    return result


@app.post("/api/decide")
async def decide(request: DecisionRequest):

    question = request.question.strip()

    if not question:
        return {"error": "No proposition supplied."}

    # All three deliberate independently and concurrently.
    results = await asyncio.gather(
        ask_magi(MAGI["melchior"], question),
        ask_magi(MAGI["balthasar"], question),
        ask_magi(MAGI["casper"], question),
    )

    yes = sum(1 for result in results if result["decision"].upper() == "YES")

    no = sum(1 for result in results if result["decision"].upper() == "NO")

    if yes >= 2:
        decision = "YES"
    elif no >= 2:
        decision = "NO"
    else:
        decision = "UNRESOLVED"

    return {
        "question": question,
        "decision": decision,
        "votes": {
            "yes": yes,
            "no": no,
        },
        "members": results,
    }


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
