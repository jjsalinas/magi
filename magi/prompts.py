"""Build compact per-round prompts for the MAGI members."""

from .config import MAX_ROUNDS
from .types import MemberConfig, RoundState

_DIVIDER = "─" * 48


# =============================================================
# PREVIOUS ROUNDS
# =============================================================
def format_previous_rounds(
    rounds: list[RoundState],
    current_round: int,
) -> str:
    """
    Create a compact deliberation history.

    Only the latest position and reason from each MAGI are kept.
    Full historical transcripts are intentionally avoided because
    they grow rapidly with every round.
    """

    if not rounds:
        return "No previous deliberation."

    # Only send the most recent round.
    #
    # The latest round already represents the MAGI's current
    # understanding of all earlier discussion.
    previous = rounds[-1]

    if int(previous.get("round", 0)) >= current_round:
        return "No previous deliberation."

    sections = [
        f"ROUND {previous.get('round', 0)}",
        f"VOTE: {previous.get('yes', 0)} YES / {previous.get('no', 0)} NO",
        _DIVIDER,
    ]

    for member in previous.get("members", []):
        reason = str(member.get("reason", "")).strip()

        # Keep previous reasoning deliberately short.
        reason = reason[:600]

        sections.append(
            f"{member.get('member', 'UNKNOWN')}: "
            f"{member.get('decision', 'UNKNOWN')} "
            f"({float(member.get('confidence', 0)):.0%})\n"
            f"{reason}"
        )

    return "\n".join(sections)


# =============================================================
# ROUND 1
# =============================================================
def _first_round_prompt(
    question: str,
    member: MemberConfig,
) -> str:
    return f"""
MAGI ROUND 1/{MAX_ROUNDS}

PROPOSITION:
{question}

You are {member["name"]}, {member["role"]}.

This is your independent initial judgment.
Do not predict the other MAGI.

Determine whether the proposition should be accepted.

Return ONLY JSON:

{{
  "decision": "YES" or "NO",
  "confidence": 0.0 to 1.0,
  "reason": "brief justification"
}}
"""


# =============================================================
# FINAL ROUND
# =============================================================
def _final_round_banner() -> str:
    return f"""
FINAL MAGI ROUND {MAX_ROUNDS}/{MAX_ROUNDS}

This is the final judgment.

Review the previous positions.
Challenge weak reasoning.
Concede strong reasoning.
Change your vote only if warranted.

You MUST choose YES or NO.
"""


# =============================================================
# MIDDLE ROUND
# =============================================================
def _mid_round_banner(
    current_round: int,
) -> str:
    return f"""
MAGI DELIBERATION ROUND {current_round}/{MAX_ROUNDS}

Reassess your position using the previous MAGI judgments.

Ask:
- What did I miss?
- What assumption may be wrong?
- Does another MAGI have a stronger argument?
- Should I change my vote?

Agreement is not required.
Changing your vote is permitted.
"""


# =============================================================
# BUILD PROMPT
# =============================================================
def build_round_instruction(
    question: str,
    current_round: int,
    previous_rounds: list[RoundState],
    member: MemberConfig,
) -> str:
    """
    Build a compact user prompt.

    The member's identity and personality remain in the system
    prompt. This prompt contains only the current proposition and
    the minimum deliberation context required.
    """

    if current_round == 1:
        return _first_round_prompt(
            question,
            member,
        )

    banner = (
        _final_round_banner()
        if current_round == MAX_ROUNDS
        else _mid_round_banner(current_round)
    )

    history = format_previous_rounds(
        previous_rounds,
        current_round,
    )

    return f"""
{banner}

PROPOSITION:
{question}

{_DIVIDER}
PREVIOUS MAGI JUDGMENTS
{_DIVIDER}

{history}

{_DIVIDER}

You are {member["name"]}, {member["role"]}.

Give your current judgment.

Return ONLY JSON:

{{
  "decision": "YES" or "NO",
  "confidence": 0.0 to 1.0,
  "reason": "brief justification"
}}
"""
