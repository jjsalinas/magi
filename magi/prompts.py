"""Builds the per-round prompt sent to each MAGI member."""

from .config import MAX_ROUNDS
from .types import MemberConfig, RoundState

_DIVIDER = "━" * 60


def format_previous_rounds(rounds: list[RoundState], current_round: int) -> str:
    """Render prior deliberation rounds as a transcript for the next round's prompt."""
    if not rounds:
        return "NO PREVIOUS DELIBERATION.\nThis is the first independent analysis."

    sections: list[str] = []

    for round_state in rounds:
        if int(round_state.get("round", 0)) >= current_round:
            continue

        yes = round_state.get("yes", 0)
        no = round_state.get("no", 0)

        sections.append(
            f"\n{_DIVIDER}\n"
            f"ROUND {round_state.get('round', 0)}\n"
            f"VOTE: {yes} YES / {no} NO\n"
            f"{_DIVIDER}\n"
        )

        for member in round_state.get("members", []):
            sections.append(
                f"\n{member.get('member', 'UNKNOWN')}\n"
                f"ROLE: {member.get('role', 'UNKNOWN')}\n"
                f"POSITION: {member.get('decision', 'UNKNOWN')}\n"
                f"CONFIDENCE: {member.get('confidence', 0):.2f}\n\n"
                f"ARGUMENT:\n{member.get('reason', '')}\n"
            )

    return "\n".join(sections)


def _first_round_prompt(question: str, member: MemberConfig) -> str:
    return f"""
╔══════════════════════════════════════════════════════════╗
║                 MAGI DELIBERATION                        ║
║                 ROUND 1 / {MAX_ROUNDS}                              ║
║                 INDEPENDENT ANALYSIS                      ║
╚══════════════════════════════════════════════════════════╝

QUESTION:

{question}

You are {member["name"]}.
Your assigned perspective is {member["role"]}.

This is the initial independent analysis.

Do NOT attempt to predict the opinions of the other MAGI.

Analyze the proposition independently.

At the end of your analysis you MUST cast a binary vote:

YES or NO.

Your vote is provisional and may be reconsidered during
later deliberation rounds.

Return ONLY JSON.
"""


def _final_round_banner() -> str:
    return f"""
╔══════════════════════════════════════════════════════════╗
║              FINAL MAGI DETERMINATION                    ║
║                    ROUND {MAX_ROUNDS} / {MAX_ROUNDS}                           ║
╚══════════════════════════════════════════════════════════╝

THIS IS THE FINAL ROUND.

There will be NO ROUND {MAX_ROUNDS + 1}.

The MAGI system MUST reach a final determination after this
round.

You MUST choose YES or NO.

No abstention is permitted.

No UNRESOLVED result is permitted.

No deferral is permitted.

If disagreement remains, the majority vote of the three
members becomes the final MAGI determination.

Before voting:

1. Review the complete deliberation.
2. Identify the strongest argument from each member.
3. Determine whether your previous position still survives.
4. Change your vote if warranted.
5. Cast your FINAL binary vote.

Do not vote for consensus merely because agreement is desirable.

Vote for the position you genuinely judge to be strongest.
"""


def _mid_round_banner(current_round: int) -> str:
    return f"""
╔══════════════════════════════════════════════════════════╗
║              MAGI DELIBERATION ROUND                    ║
║                 ROUND {current_round} / {MAX_ROUNDS}                          ║
╚══════════════════════════════════════════════════════════╝

The MAGI members currently disagree.

A majority exists, but it is NOT yet sufficient to conclude.

The purpose of this round is to challenge the current
positions and attempt to reach genuine convergence.

Review the other members' arguments.

Ask yourself:

- Did another member identify something I missed?
- Is my current reasoning based on an unsupported assumption?
- Is the majority position actually stronger?
- Is the minority position exposing a serious flaw?
- What evidence would justify changing my vote?
- Does my current position remain defensible?

You MAY change your vote.

You MAY retain your vote.

Do NOT change your vote merely to create agreement.

A binary vote is mandatory.
"""


def build_round_instruction(
    question: str,
    current_round: int,
    previous_rounds: list[RoundState],
    member: MemberConfig,
) -> str:
    """Build the full user-turn prompt for one member in one round."""
    if current_round == 1:
        return _first_round_prompt(question, member)

    banner = _final_round_banner() if current_round == MAX_ROUNDS else _mid_round_banner(current_round)
    transcript = format_previous_rounds(previous_rounds, current_round)

    return f"""
{banner}

QUESTION:

{question}

{_DIVIDER}
PREVIOUS MAGI DELIBERATION
{_DIVIDER}

{transcript}

{_DIVIDER}
YOUR ROLE
{_DIVIDER}

You are {member["name"]}, the {member["role"]} intelligence.

Conduct your reassessment through your assigned perspective.

You are participating in an adversarial but constructive
deliberation.

The other MAGI are not your enemies.

However, their arguments must survive scrutiny.

Your objective is not unanimity.

Your objective is intellectual integrity.

{_DIVIDER}
REQUIRED OUTPUT
{_DIVIDER}

Return ONLY:

{{
  "decision": "YES" or "NO",
  "confidence": number between 0 and 1,
  "reason": "concise explanation of your current position"
}}
"""
