# MAGI

> **MAGI SYSTEMS — DECISION SUPPORT**
>
> `質問 / QUESTION` · `審議 / DELIBERATION` · `解決 / SOLUTION`

A small **Evangelion-inspired multi-agent decision system** powered by local LLMs via LM Studio.

<img width="auto" height="520" alt="image" src="https://github.com/user-attachments/assets/8a40f493-5816-4f0b-981e-43aefbf32b12" />

<img width="auto" height="520" alt="image" src="https://github.com/user-attachments/assets/78dfca3f-c98a-4206-a1a9-6480e691fa6c" />


### The MAGI

`MELCHIOR-01` — The Scientist: evidence, logic, truth, causality.

`BALTHASAR-02` — The Mother: consequences, risk, responsibility, practicality.

`CASPER-03` — The Woman: human behavior, motivation, perception, social context.

### How it works

All three independently evaluate the proposition.<br />
If they disagree, they see the previous round's judgments.<br />
Each MAGI may defend or change its position.<br />
This repeats for `MAX_ROUNDS`.<br />

Unanimous agreement produces `CONSENSUS`.<br />
If the final round still has disagreement, the 2–1 majority becomes the final decision.<br />

The LLMs provide the reasoning and votes; the Python engine controls the deliberation protocol and final vote.<br />

### `MAGI DECISION SUPPORT SYSTEM`
#### `質問 — PROPOSITION / QUESTION`

## Status

🟢 Working demo

- Local LM Studio models
- 3-agent MAGI deliberation
- Multi-round decision process
- Consensus + majority determination
- Individual reasoning + confidence
- Evangelion MAGI-inspired CRT UI
- Live deliberation status
- Configurable rounds and response limits
- Responsive interface

## Setup venv

First, setup your `.env` file (theres a `.env.example` file in the repo)

```env
MODEL_ID=your-model-id
OPEN_AI_BASE_URL=http://localhost:1234/v1
OPEN_AI_API_KEY=your-api-key

MAX_ROUNDS=5
MAX_RESPONSE_TOKENS=300
```

Python 3.14 needed

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

#### Add your config to the `.env` file first!

Start the LM Studio local server.

Then start the APP server:

```bash
uvicorn app:app --reload --port 8765
```

Web interface will be at `http://localhost:8765/`

## TODO

- More advanced consensus logic
- Even more MAGI aesthetics
