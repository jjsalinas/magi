import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

app = FastAPI(title="MAGI")

client = AsyncOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
)


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

# Put the exact model identifier shown by LM Studio here.
MODEL = os.getenv(
    "MAGI_MODEL",
    "your-model-id-here",
)

MAGI = {
    "melchior": {
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
    },

    "balthasar": {
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
    },

    "casper": {
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
    },
}


# ---------------------------------------------------------
# API
# ---------------------------------------------------------

class DecisionRequest(BaseModel):
    question: str


async def ask_magi(member, question):
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

    result["member"] = member["name"]
    result["role"] = member["role"]

    return result


@app.post("/api/decide")
async def decide(request: DecisionRequest):

    question = request.question.strip()

    if not question:
        return {
            "error": "No proposition supplied."
        }

    # All three deliberate independently and concurrently.
    results = await asyncio.gather(
        ask_magi(MAGI["melchior"], question),
        ask_magi(MAGI["balthasar"], question),
        ask_magi(MAGI["casper"], question),
    )

    yes = sum(
        1 for result in results
        if result["decision"].upper() == "YES"
    )

    no = sum(
        1 for result in results
        if result["decision"].upper() == "NO"
    )

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
    return FileResponse(
        Path(__file__).parent / "static" / "index.html"
    )
