# MAGI

A small **Evangelion-inspired multi-agent decision system** powered by local LLMs via LM Studio.

Three independent agents analyze the same question from different perspectives:

- **MELCHIOR • 1** — Logic
- **BALTHASAR • 2** — Practical
- **CASPER • 3** — Ethics

Each returns a structured `YES/NO` vote, confidence, and reasoning. The final MAGI decision is determined by majority vote.

ONLY works properly for YES/NO questions.

## Status

🟢 Working demo

- Local LM Studio models
- 3-agent decision pipeline
- Majority consensus
- MAGI-inspired CRT UI
- Individual reasoning + confidence
- Responsive interface

## Setup venv

Python 3.14 recommended

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

#### Add your config to the .env file first!

Start the LM Studio local server.

Then start the APP server:
```bash
uvicorn app:app --reload --port 8765
```

Web interface will be at `http://localhost:8765/`

## TODO

- Multi-round deliberation
- Agents reviewing each other's arguments
- Streaming responses
- More advanced consensus logic
- Even more MAGI aesthetics
