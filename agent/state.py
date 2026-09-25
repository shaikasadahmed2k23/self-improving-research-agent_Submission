"""Shared LangGraph state and the structured-output models the nodes exchange."""
import operator
from typing import Annotated, TypedDict

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


class AgentState(TypedDict, total=False):
    task: str
    plan: list[dict]  # {id, goal, search_query, status: pending|done, result}
    current_step: int
    messages: Annotated[list[AnyMessage], add_messages]  # ReAct scratchpad for the current step only
    step_iterations: int  # LLM calls used in the current step
    sources: list[dict]  # {id, title, url, content, provider} – ids are citation numbers
    draft: str
    trace: Annotated[list[dict], operator.add]  # UI/CLI events, append-only


def event(node: str, kind: str, content: str) -> dict:
    """One trace entry. kind: plan | thought | action | observation | result | report | error."""
    return {"node": node, "kind": kind, "content": content}
