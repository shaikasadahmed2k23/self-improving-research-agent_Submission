"""LangGraph wiring.

M1:  START -> planner -> executor (loops once per step) -> writer -> END
"""
from langgraph.graph import END, START, StateGraph

from agent.nodes.executor import executor, route_after_executor
from agent.nodes.planner import planner
from agent.nodes.writer import writer
from agent.state import AgentState


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("planner", planner)
    g.add_node("executor", executor)
    g.add_node("writer", writer)

    g.add_edge(START, "planner")
    g.add_edge("planner", "executor")
    g.add_conditional_edges("executor", route_after_executor, {"executor": "executor", "writer": "writer"})
    g.add_edge("writer", END)
    return g.compile()
