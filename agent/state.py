"""Shared LangGraph state and the structured-output models the nodes exchange."""
import operator
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    goal: str = Field(description="What this step must find out, phrased as a concrete sub-question")
    search_query: str = Field(
        description="Suggested first web search (3-10 words). Only concrete terms; never placeholders like X or <provider>"
    )


class Plan(BaseModel):
    steps: list[PlanStep] = Field(description="Ordered research steps")


class Critique(BaseModel):
    score: int = Field(description="Overall quality 1-10 (7+ means ready to deliver)")
    issues: list[str] = Field(default_factory=list, description="Concrete problems: errors, contradictions, unit mistakes, misattributed citations")
    missing_info: list[str] = Field(default_factory=list, description="Information the task needs that the report lacks")
    constraint_violations: list[str] = Field(
        default_factory=list,
        description="Explicit task requirements not satisfied (e.g. 'use the official pricing page' but it was never fetched)",
    )
    verdict: Literal["accept", "needs_research", "needs_rewrite"] = Field(
        description="accept: deliver as is; needs_research: new tool work required; needs_rewrite: findings suffice, report must be fixed"
    )


class AgentState(TypedDict, total=False):
    task: str
    plan: list[dict]  # {id, goal, search_query, status: pending|done, result, origin: initial|fixup}
    current_step: int
    messages: Annotated[list[AnyMessage], add_messages]  # ReAct scratchpad for the current step only
    step_iterations: int  # LLM calls used in the current step
    sources: list[dict]  # {id, title, url, content, provider} – ids are global citation numbers
    tool_log: Annotated[list[dict], operator.add]  # {step, tool, args, error}
    calculations: Annotated[list[dict], operator.add]  # {expression, result} from the calculator tool
    draft_raw: str  # writer output with global source ids (what verify/critic/rewrites work on)
    draft: str  # user-facing report: citations renumbered 1..n + Sources list
    checks: list[dict]  # deterministic citation-check results for the current draft
    critique: dict  # Critique.model_dump() + {"final": bool}
    revision: int  # number of critic-requested revisions so far
    trace: Annotated[list[dict], operator.add]  # UI/CLI events, append-only


def event(node: str, kind: str, content: str) -> dict:
    """One trace entry. kind: plan | thought | action | observation | result | report | check | critique | error."""
    return {"node": node, "kind": kind, "content": content}
