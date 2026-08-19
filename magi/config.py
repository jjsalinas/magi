"""Environment configuration and runtime constants for the MAGI system."""

import os

from dotenv import load_dotenv

load_dotenv()

MODEL_ID = os.getenv("MODEL_ID")
OPEN_AI_BASE_URL = os.getenv("OPEN_AI_BASE_URL")
OPEN_AI_API_KEY = os.getenv("OPEN_AI_API_KEY")

MAX_ROUNDS = 5
MEMBER_NAMES = ("melchior", "balthasar", "casper")

_REQUIRED_ENV_VARS = {
    "MODEL_ID": "The model identifier",
    "OPEN_AI_BASE_URL": "The base URL for the API endpoint",
    "OPEN_AI_API_KEY": "The API key or token",
}


def validate_environment() -> None:
    """Raise ValueError listing any missing required environment variables."""
    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]

    if missing:
        details = "\n".join(f"  - {name}: {_REQUIRED_ENV_VARS[name]}" for name in missing)
        raise ValueError(f"Missing required environment variable(s):\n{details}")
