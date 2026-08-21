"""Environment configuration and runtime constants for the MAGI system."""

import os

from dotenv import load_dotenv

load_dotenv()


# =============================================================
# MODEL CONFIGURATION
# =============================================================
MODEL_ID = os.getenv("MODEL_ID")
OPEN_AI_BASE_URL = os.getenv("OPEN_AI_BASE_URL")
OPEN_AI_API_KEY = os.getenv("OPEN_AI_API_KEY")


# =============================================================
# DELIBERATION CONFIGURATION
# =============================================================
def _env_int(
    name: str,
    default: int,
) -> int:
    """
    Read a positive integer from the environment.

    If the variable is missing, invalid, or non-positive,
    the supplied default is used.
    """

    value = os.getenv(name)

    if value is None:
        return default

    try:
        parsed = int(value)
    except ValueError:
        return default

    return parsed if parsed > 0 else default


MAX_ROUNDS = _env_int(
    "MAX_ROUNDS",
    5,
)

MAX_RESPONSE_TOKENS = _env_int(
    "MAX_RESPONSE_TOKENS",
    300,
)


# =============================================================
# MAGI MEMBERS
# =============================================================
MEMBER_NAMES = (
    "melchior",
    "balthasar",
    "casper",
)


# =============================================================
# REQUIRED ENVIRONMENT VARIABLES
# =============================================================
_REQUIRED_ENV_VARS = {
    "MODEL_ID": "The model identifier",
    "OPEN_AI_BASE_URL": "The base URL for the API endpoint",
    "OPEN_AI_API_KEY": "The API key or token",
}


# =============================================================
# VALIDATION
# =============================================================
def validate_environment() -> None:
    """
    Raise ValueError listing any missing required environment
    variables.
    """

    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]

    if missing:
        details = "\n".join(
            f"  - {name}: {_REQUIRED_ENV_VARS[name]}" for name in missing
        )

        raise ValueError(f"Missing required environment variable(s):\n{details}")
