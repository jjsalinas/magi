"""
The MAGI deliberation engine.

Runs the three MAGI members through N rounds of voting.

The engine supports an optional async `on_update` callback.
The callback is invoked after every completed round, allowing
the API layer to expose live deliberation state to the frontend.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

from .config import MAX_ROUNDS, MEMBER_NAMES, MODEL_ID
from .json_utils import (
    clamp_confidence,
    extract_binary_decision,
    extract_json_object,
    normalize_decision,
)
from .members import MAGI
from .prompts import build_round_instruction
from .types import MAGIState, MemberConfig, MemberResult, RoundState

_MAX_ATTEMPTS_PER_MEMBER = 3


# =============================================================
# TYPES
# =============================================================

StateUpdateCallback = Callable[
    [MAGIState],
    Awaitable[None],
]


# =============================================================
# CORRECTION PROMPT
# =============================================================

_CORRECTION_NOTICE = """

╔══════════════════════════════════════════════════════════╗
║                  MAGI CORRECTION                         ║
╚══════════════════════════════════════════════════════════╝

Your previous response could not be interpreted as a valid
binary MAGI decision.

This is a protocol violation.

Return ONLY valid JSON.

The "decision" field MUST contain exactly:

YES

or:

NO

No other value is permitted.
"""


# =============================================================
# MEMBER REQUEST
# =============================================================


async def ask_member(
    client: AsyncOpenAI,
    member: MemberConfig,
    question: str,
    current_round: int,
    previous_rounds: list[RoundState],
) -> MemberResult:
    """
    Query one MAGI member for its vote this round.

    Members are retried up to three times if their response cannot
    be interpreted as a valid MAGI decision.
    """

    base_prompt = build_round_instruction(
        question=question,
        current_round=current_round,
        previous_rounds=previous_rounds,
        member=member,
    )

    for attempt in range(
        1,
        _MAX_ATTEMPTS_PER_MEMBER + 1,
    ):
        prompt = base_prompt if attempt == 1 else base_prompt + _CORRECTION_NOTICE

        try:
            response = await client.chat.completions.create(
                model=MODEL_ID,
                temperature=0.25,
                messages=[
                    {
                        "role": "system",
                        "content": member["prompt"],
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            )

        except Exception as exc:
            print(f"[{member['name']}] API ERROR: {exc}")
            continue

        text = (response.choices[0].message.content or "").strip()

        result = _parse_member_reply(
            text,
            member,
            current_round,
        )

        if result:
            return result

    return _fallback_result(
        member,
        current_round,
        previous_rounds,
    )


# =============================================================
# MEMBER RESPONSE PARSER
# =============================================================


def _parse_member_reply(
    text: str,
    member: MemberConfig,
    current_round: int,
) -> MemberResult | None:
    """
    Try to turn a raw model reply into a MemberResult.

    JSON is preferred, but a plain YES/NO response is accepted
    as a defensive fallback.
    """

    parsed = extract_json_object(text)

    if parsed:
        decision = normalize_decision(parsed.get("decision"))

        if decision:
            return {
                "member": member["name"],
                "role": member["role"],
                "decision": decision,
                "confidence": clamp_confidence(parsed.get("confidence")),
                "reason": str(
                    parsed.get(
                        "reason",
                        "No reasoning supplied.",
                    )
                ).strip(),
                "round": current_round,
            }

    decision = extract_binary_decision(text)

    if decision:
        return {
            "member": member["name"],
            "role": member["role"],
            "decision": decision,
            "confidence": 0.5,
            "reason": text[:1000],
            "round": current_round,
        }

    return None


# =============================================================
# FALLBACK
# =============================================================


def _fallback_result(
    member: MemberConfig,
    current_round: int,
    previous_rounds: list[RoundState],
) -> MemberResult:
    """
    When every attempt fails, retain the member's last valid vote.

    If there is no previous vote, default to NO.
    """

    for round_state in reversed(previous_rounds):
        for previous_member in round_state.get(
            "members",
            [],
        ):
            if previous_member.get("member") != member["name"]:
                continue

            previous_vote = normalize_decision(previous_member.get("decision"))

            if previous_vote:
                return {
                    "member": member["name"],
                    "role": member["role"],
                    "decision": previous_vote,
                    "confidence": 0.0,
                    "reason": (
                        "No valid response was received "
                        "during this round. Previous valid "
                        "position retained."
                    ),
                    "round": current_round,
                }

    return {
        "member": member["name"],
        "role": member["role"],
        "decision": "NO",
        "confidence": 0.0,
        "reason": (
            "MAGI protocol fallback activated. "
            "Member failed to produce a valid binary vote."
        ),
        "round": current_round,
    }


# =============================================================
# ROUND EVALUATION
# =============================================================


def evaluate_round(
    results: list[MemberResult],
    round_number: int,
) -> RoundState:
    """
    Tally one round's votes and determine its phase.
    """

    yes = sum(1 for result in results if result.get("decision") == "YES")

    no = sum(1 for result in results if result.get("decision") == "NO")

    unanimous = yes == 3 or no == 3

    if unanimous:
        phase = "UNANIMOUS_CONSENSUS"

    elif round_number == MAX_ROUNDS:
        phase = "FINAL_MAJORITY"

    else:
        phase = "DELIBERATION_REQUIRED"

    return {
        "round": round_number,
        "phase": phase,
        "members": results,
        "yes": yes,
        "no": no,
        "decision": ("YES" if yes > no else "NO"),
        "unanimous": unanimous,
    }


# =============================================================
# LOGGING
# =============================================================


def _log_round(
    round_number: int,
    results: list[MemberResult],
    round_state: RoundState,
) -> None:
    """
    Print a compact round summary to the server console.
    """

    print(f"\n┌── ROUND {round_number}/{MAX_ROUNDS} ────────────────────────┐")

    for result in results:
        print(
            f"│ {result['member']:<11}: "
            f"{result['decision']} "
            f"({result['confidence']:.0%})"
        )

    print(f"│ VOTE       : {round_state['yes']} YES / {round_state['no']} NO")

    print(f"│ STATUS     : {round_state['phase']}")


# =============================================================
# STATE UPDATE
# =============================================================


async def _notify_update(
    on_update: StateUpdateCallback | None,
    state: MAGIState,
) -> None:
    """
    Notify the API layer about a new state.

    Callback errors are deliberately swallowed so a problem in
    the live-status mechanism can never kill the MAGI session.
    """

    if on_update is None:
        return

    try:
        await on_update(state)

    except Exception as exc:
        print(f"[MAGI] STATE UPDATE ERROR: {type(exc).__name__}: {exc}")


# =============================================================
# MAIN DELIBERATION
# =============================================================


async def deliberate(
    client: AsyncOpenAI,
    question: str,
    on_update: StateUpdateCallback | None = None,
    session_id: str | None = None,
) -> MAGIState:
    """
    Run a complete MAGI session.

    Parameters
    ----------
    client:
        OpenAI-compatible async client.

    question:
        Proposition being evaluated.

    on_update:
        Optional async callback invoked after every completed
        round.

    The callback is what allows the FastAPI layer to expose
    intermediate rounds while the MAGI system is still working.
    """

    state: MAGIState = {
        "session_id": session_id or uuid.uuid4().hex[:8],
        "question": question,
        "phase": "INITIALIZING",
        "round": 0,
        "max_rounds": MAX_ROUNDS,
        "decision": "PENDING",
        "votes": {
            "yes": 0,
            "no": 0,
        },
        "members": [],
        "rounds": [],
    }

    print(f"\n{'=' * 60}\n MAGI SESSION\n{'=' * 60}")

    print(f" SESSION : {state['session_id']}")

    print(f" QUESTION: {question}")

    print("=" * 60)

    # ---------------------------------------------------------
    # Initial state update.
    # ---------------------------------------------------------

    await _notify_update(
        on_update,
        state,
    )

    # ---------------------------------------------------------
    # MAGI rounds.
    # ---------------------------------------------------------

    for round_number in range(
        1,
        MAX_ROUNDS + 1,
    ):
        state["round"] = round_number

        if round_number == 1:
            state["phase"] = "INITIAL_ANALYSIS"

        elif round_number == MAX_ROUNDS:
            state["phase"] = "FINAL_DETERMINATION"

        else:
            state["phase"] = "DELIBERATING"

        # -----------------------------------------------------
        # Notify frontend that a new round has started.
        #
        # At this point members are still thinking.
        # -----------------------------------------------------

        await _notify_update(
            on_update,
            state,
        )

        print(f"\n[ MAGI ] BEGIN ROUND {round_number}/{MAX_ROUNDS}")

        # -----------------------------------------------------
        # Ask all three MAGI members concurrently.
        # -----------------------------------------------------

        results = list(
            await asyncio.gather(
                *[
                    ask_member(
                        client,
                        MAGI[name],
                        question,
                        round_number,
                        state["rounds"],
                    )
                    for name in MEMBER_NAMES
                ]
            )
        )

        # -----------------------------------------------------
        # Evaluate completed round.
        # -----------------------------------------------------

        round_state = evaluate_round(
            results,
            round_number,
        )

        state["rounds"].append(round_state)

        state["members"] = results

        state["votes"] = {
            "yes": round_state["yes"],
            "no": round_state["no"],
        }

        _log_round(
            round_number,
            results,
            round_state,
        )

        # -----------------------------------------------------
        # IMPORTANT:
        #
        # This is the live update.
        #
        # The API receives the completed round immediately,
        # before the engine proceeds to the next round.
        # -----------------------------------------------------

        await _notify_update(
            on_update,
            state,
        )

        # -----------------------------------------------------
        # Unanimous consensus.
        # -----------------------------------------------------

        if round_state["unanimous"]:
            state["decision"] = round_state["decision"]

            state["phase"] = "CONSENSUS_REACHED"

            await _notify_update(
                on_update,
                state,
            )

            print(f"│\n└── CONSENSUS: {state['decision']} ────────────────────")

            break

        # -----------------------------------------------------
        # Continue deliberation.
        # -----------------------------------------------------

        if round_number < MAX_ROUNDS:
            print(
                "│\n│ MAJORITY DETECTED. CONSENSUS NOT REACHED. DELIBERATION CONTINUES."
            )

            print(f"└── ADVANCING TO ROUND {round_number + 1} ─────────────────")

            continue

        # -----------------------------------------------------
        # Final majority.
        # -----------------------------------------------------

        state["decision"] = round_state["decision"]

        state["phase"] = "FINAL_MAJORITY"

        await _notify_update(
            on_update,
            state,
        )

        print(f"│\n│ MAXIMUM DELIBERATION REACHED. FINAL MAJORITY: {state['decision']}")

        print("└── MAGI DETERMINATION COMPLETE ────────────────")

    # ---------------------------------------------------------
    # Absolute safety net.
    # ---------------------------------------------------------

    if state["decision"] not in {
        "YES",
        "NO",
    }:
        final_round = state["rounds"][-1]

        yes = int(final_round["yes"])

        no = int(final_round["no"])

        state["decision"] = "YES" if yes > no else "NO"

        state["votes"] = {
            "yes": yes,
            "no": no,
        }

        state["phase"] = "FORCED_FINAL_MAJORITY"

        await _notify_update(
            on_update,
            state,
        )

    return state
