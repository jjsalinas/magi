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

## Run

Start the LM Studio local server, then start the project backend and open the provided localhost URL in a browser.

```bash
# Indicate the model
export MAGI_MODEL="liquid/lfm2.5-1.2b"

# Start the python server
uvicorn app:app --reload
```

Web interface will be at `http://localhost:8000/`

## TODO

- Multi-round deliberation
- Agents reviewing each other's arguments
- Streaming responses
- More advanced consensus logic
- Even more MAGI aesthetics
