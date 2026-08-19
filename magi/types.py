"""Shared type definitions for the MAGI deliberation system."""

from typing import TypedDict


class MemberConfig(TypedDict):
    name: str
    role: str
    color: str
    prompt: str


class MemberResult(TypedDict, total=False):
    member: str
    role: str
    decision: str
    confidence: float
    reason: str
    round: int


class RoundState(TypedDict, total=False):
    round: int
    phase: str
    members: list[MemberResult]
    yes: int
    no: int
    decision: str
    unanimous: bool


class MAGIState(TypedDict, total=False):
    session_id: str
    question: str
    phase: str
    round: int
    max_rounds: int
    decision: str
    votes: dict[str, int]
    members: list[MemberResult]
    rounds: list[RoundState]
