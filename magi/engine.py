"""
MAGI DELIBERATION ENGINE
========================

Runs MELCHIOR, BALTHASAR, and CASPER through repeated
deliberation rounds.

Architecture:

    ROUND 1
        Independent judgments

    ROUND 2+
        Reassessment of previous MAGI arguments

    FINAL ROUND
        Final independent judgments

    ENGINE
        Determines CONSENSUS or MAJORITY

The MAGI members themselves never determine the system result.
They only provide their individual judgments.

The engine is responsible for:

    - calling members
    - validating responses
    - preserving previous positions on failure
    - detecting vote changes
    - evaluating rounds
    - determining consensus / majority
    - exposing live state to the API
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

from .config import (
    MAX_RESPONSE_TOKENS,
    MAX_ROUNDS,
    MEMBER_NAMES,
    MODEL_ID,
)
from .json_utils import (
    clamp_confidence,
    extract_binary_decision,
    extract_json_object,
    normalize_decision,
)
from .members import MAGI
from .prompts import build_round_instruction
from .types import MAGIState, MemberConfig, MemberResult, RoundState

# =============================================================
# CONFIGURATION
# =============================================================

_MAX_ATTEMPTS_PER_MEMBER = 3

# Round 1 establishes independent judgments.
# Do not terminate on unanimity until the MAGI have had at least
# one opportunity to challenge one another.
_MIN_DELIBERATION_ROUNDS = 2


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

Your previous response violated the MAGI output protocol.

Return ONLY valid JSON.

The "decision" field MUST contain exactly:

YES

or:

NO

"confidence" MUST be a number between 0 and 1.

"reason" MUST directly address the proposition.

No markdown.
No additional fields.
No commentary outside the JSON.
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
    Query one MAGI member for its judgment in the current round.

    Each attempt is independent at the API level, but receives the
    same deliberation context.

    A member gets up to three attempts to satisfy the output
    protocol before the engine activates its fallback behavior.
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
                max_tokens=MAX_RESPONSE_TOKENS,
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
            print(
                f"[{member['name']}] "
                f"API ERROR "
                f"(attempt {attempt}/{_MAX_ATTEMPTS_PER_MEMBER}): "
                f"{type(exc).__name__}: {exc}"
            )

            continue

        text = (response.choices[0].message.content or "").strip()

        result = _parse_member_reply(
            text=text,
            member=member,
            current_round=current_round,
        )

        if result is not None:
            return result

        print(
            f"[{member['name']}] "
            f"INVALID RESPONSE "
            f"(attempt {attempt}/{_MAX_ATTEMPTS_PER_MEMBER})"
        )

    return _fallback_result(
        member=member,
        current_round=current_round,
        previous_rounds=previous_rounds,
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
    Convert a raw model response into a validated MemberResult.

    JSON is preferred.

    A plain YES/NO response is accepted as a defensive fallback
    because local models occasionally ignore the JSON instruction.

    Plain-text responses receive confidence 0.5 because the model
    did not provide a valid confidence value.
    """

    parsed = extract_json_object(text)

    if parsed:
        decision = normalize_decision(parsed.get("decision"))

        if decision:
            reason = str(
                parsed.get(
                    "reason",
                    "No reasoning supplied.",
                )
            ).strip()

            return {
                "member": member["name"],
                "role": member["role"],
                "decision": decision,
                "confidence": clamp_confidence(parsed.get("confidence")),
                "reason": reason,
                "round": current_round,
                "fallback": False,
            }

    # ---------------------------------------------------------
    # Defensive plain-text parser.
    # ---------------------------------------------------------

    decision = extract_binary_decision(text)

    if decision:
        return {
            "member": member["name"],
            "role": member["role"],
            "decision": decision,
            "confidence": 0.5,
            "reason": text[:1000],
            "round": current_round,
            "fallback": False,
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
    Produce a safe result when a member cannot produce a valid
    response after all attempts.

    If a previous valid position exists, preserve it.

    If no previous position exists, use NO as the deterministic
    protocol fallback.

    Fallback is explicitly marked so the API/frontend can
    distinguish a real MAGI judgment from a technical fallback.
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
                        "No valid response was received during "
                        "this round. Previous valid position "
                        "retained."
                    ),
                    "round": current_round,
                    "fallback": True,
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
        "fallback": True,
    }


# =============================================================
# VOTE CHANGE DETECTION
# =============================================================


def _previous_member_result(
    member_name: str,
    previous_rounds: list[RoundState],
) -> MemberResult | None:
    """
    Find the most recent result for one MAGI member.
    """

    for round_state in reversed(previous_rounds):
        for result in round_state.get(
            "members",
            [],
        ):
            if result.get("member") == member_name:
                return result

    return None


def _mark_vote_change(
    result: MemberResult,
    previous_rounds: list[RoundState],
) -> MemberResult:
    """
    Add explicit vote-change metadata to a result.

    Round 1 cannot have changed=True because there is no previous
    position.
    """

    previous = _previous_member_result(
        result["member"],
        previous_rounds,
    )

    if previous is None:
        result["changed"] = False
        return result

    previous_decision = normalize_decision(previous.get("decision"))

    result["changed"] = (
        previous_decision is not None and previous_decision != result["decision"]
    )

    return result


# =============================================================
# ROUND EVALUATION
# =============================================================


def evaluate_round(
    results: list[MemberResult],
    round_number: int,
) -> RoundState:
    """
    Evaluate one completed MAGI round.

    The engine distinguishes:

        CONSENSUS
            All three MAGI agree after the minimum deliberation.

        DELIBERATION_REQUIRED
            Disagreement remains and another round is available.

        FINAL_MAJORITY
            Maximum rounds reached without consensus.

    The decision field represents the current majority position.
    It does NOT imply consensus.
    """

    yes = sum(1 for result in results if result.get("decision") == "YES")
    no = sum(1 for result in results if result.get("decision") == "NO")

    unanimous = yes == 3 or no == 3
    decision = "YES" if yes >= 2 else "NO"

    if unanimous and round_number >= _MIN_DELIBERATION_ROUNDS:
        phase = "CONSENSUS_REACHED"
    elif round_number >= MAX_ROUNDS:
        phase = "FINAL_MAJORITY"
    else:
        phase = "DELIBERATION_REQUIRED"

    return {
        "round": round_number,
        "phase": phase,
        "members": results,
        "yes": yes,
        "no": no,
        "decision": decision,
        "unanimous": unanimous,
    }


# =============================================================
# FINAL DETERMINATION
# =============================================================


def _determine_final_state(
    state: MAGIState,
    round_state: RoundState,
) -> None:
    """
    Apply the final round's result to the session state.

    This function is deliberately deterministic.

    Three YES  -> YES / CONSENSUS
    Two YES    -> YES / MAJORITY
    One YES    -> NO  / MAJORITY
    Zero YES   -> NO  / CONSENSUS
    """

    yes = int(round_state["yes"])
    no = int(round_state["no"])

    consensus = yes == 3 or no == 3
    decision = "YES" if yes >= 2 else "NO"

    state["decision"] = decision
    state["votes"] = {
        "yes": yes,
        "no": no,
    }
    state["consensus"] = consensus
    state["determination"] = "CONSENSUS" if consensus else "MAJORITY"
    state["phase"] = "CONSENSUS_REACHED" if consensus else "FINAL_MAJORITY"


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
        changed = " CHANGED" if result.get("changed") else ""
        fallback = " FALLBACK" if result.get("fallback") else ""
        print(
            f"│ {result['member']:<14}: "
            f"{result['decision']:<3} "
            f"({result['confidence']:.0%})"
            f"{changed}"
            f"{fallback}"
        )
    print(f"│ VOTE       : {round_state['yes']} YES / {round_state['no']} NO")
    print(f"│ STATUS     : {round_state['phase']}")
    print(f"└────────────────────────────────────────────")


# =============================================================
# STATE UPDATE
# =============================================================


async def _notify_update(
    on_update: StateUpdateCallback | None,
    state: MAGIState,
) -> None:
    """
    Notify the API layer about a new state.

    Callback failures never terminate the MAGI session.
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
    Run a complete MAGI deliberation.

    Round 1:
        Independent initial analysis.

    Round 2+:
        Reassessment against previous MAGI arguments.

    Final round:
        Final independent judgments.

    The engine determines whether the final result is consensus
    or majority.
    """

    # ---------------------------------------------------------
    # Initialize state.
    # ---------------------------------------------------------

    state: MAGIState = {
        "session_id": (session_id or uuid.uuid4().hex[:8]),
        "question": question,
        "phase": "INITIALIZING",
        "round": 0,
        "max_rounds": MAX_ROUNDS,
        "decision": "PENDING",
        "determination": None,
        "consensus": False,
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
    print(f" ROUNDS  : {MAX_ROUNDS}")
    print(f" MIN CONSENSUS ROUND: {_MIN_DELIBERATION_ROUNDS}")
    print("=" * 60)

    # ---------------------------------------------------------
    # Initial state update.
    # ---------------------------------------------------------
    await _notify_update(
        on_update,
        state,
    )

    # ---------------------------------------------------------
    # Deliberation loop.
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
        # Notify frontend that the round has started.
        # -----------------------------------------------------
        await _notify_update(
            on_update,
            state,
        )

        print(f"\n[ MAGI ] BEGIN ROUND {round_number}/{MAX_ROUNDS}")

        # -----------------------------------------------------
        # Ask all three MAGI concurrently.
        #
        # They all receive the same previous-round transcript,
        # but each has its own persistent system prompt.
        # -----------------------------------------------------
        results = list(
            await asyncio.gather(
                *[
                    ask_member(
                        client=client,
                        member=MAGI[name],
                        question=question,
                        current_round=round_number,
                        previous_rounds=state["rounds"],
                    )
                    for name in MEMBER_NAMES
                ]
            )
        )

        # -----------------------------------------------------
        # Mark whether each MAGI changed its vote.
        # -----------------------------------------------------
        for result in results:
            _mark_vote_change(
                result,
                state["rounds"],
            )

        # -----------------------------------------------------
        # Evaluate the completed round.
        # -----------------------------------------------------
        round_state = evaluate_round(
            results=results,
            round_number=round_number,
        )
        state["rounds"].append(round_state)
        state["members"] = results
        state["votes"] = {
            "yes": round_state["yes"],
            "no": round_state["no"],
        }

        _log_round(
            round_number=round_number,
            results=results,
            round_state=round_state,
        )

        # -----------------------------------------------------
        # Publish completed round.
        # -----------------------------------------------------
        await _notify_update(
            on_update,
            state,
        )

        # -----------------------------------------------------
        # Consensus.
        #
        # Consensus is only allowed after the minimum number
        # of deliberation rounds.
        # -----------------------------------------------------
        if round_state["unanimous"] and round_number >= _MIN_DELIBERATION_ROUNDS:
            _determine_final_state(
                state,
                round_state,
            )
            await _notify_update(
                on_update,
                state,
            )

            print(f"\n[ MAGI ] CONSENSUS REACHED: {state['decision']}")
            print(f"[ MAGI ] DETERMINATION: {state['determination']}")
            break

        # -----------------------------------------------------
        # Continue if rounds remain.
        # -----------------------------------------------------
        if round_number < MAX_ROUNDS:
            print(f"[ MAGI ] DELIBERATION CONTINUES → ROUND {round_number + 1}")

            continue

        # -----------------------------------------------------
        # Maximum rounds reached.
        #
        # At this point the final round's majority becomes the
        # system determination.
        # -----------------------------------------------------
        _determine_final_state(
            state,
            round_state,
        )

        await _notify_update(
            on_update,
            state,
        )

        print(f"\n[ MAGI ] MAXIMUM DELIBERATION REACHED")
        print(f"[ MAGI ] FINAL DETERMINATION: {state['decision']}")
        print(f"[ MAGI ] TYPE: {state['determination']}")

    # ---------------------------------------------------------
    # Absolute safety net.
    #
    # This should never normally execute, but guarantees that
    # the API never receives PENDING after deliberate() returns.
    # ---------------------------------------------------------

    if state["decision"] not in {
        "YES",
        "NO",
    }:
        final_round = state["rounds"][-1]
        yes = int(final_round["yes"])
        no = int(final_round["no"])
        state["decision"] = "YES" if yes >= 2 else "NO"
        state["votes"] = {
            "yes": yes,
            "no": no,
        }

        state["consensus"] = yes == 3 or no == 3
        state["determination"] = "CONSENSUS" if state["consensus"] else "MAJORITY"
        state["phase"] = (
            "CONSENSUS_REACHED" if state["consensus"] else "FORCED_FINAL_MAJORITY"
        )

        await _notify_update(
            on_update,
            state,
        )

    return state
