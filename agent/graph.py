"""LangGraph wiring.

M3:  START -> planner -> executor <-> tools            (ReAct loop per step)
                 ^          |  (plain answer)
                 |          v
                 |       advance --(more steps)--> executor
                 |          |  (plan done)
                 |          v
                 |        writer -> verify -> critic --(accept or revision limit)--> END
                 |          ^                    |
                 |          +---(needs_rewrite)--+
                 +--------------(needs_research: append fix-up steps)
"""
from langgraph.graph import END, START, StateGraph

from agent.nodes.advance import advance, route_after_advance
from agent.nodes.critic import critic, route_after_critic
from agent.nodes.executor import executor, route_after_executor
from agent.nodes.planner import planner
from agent.nodes.tools_node import tools
from agent.nodes.verify import verify
from agent.nodes.writer import writer
from agent.state import AgentState


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("planner", planner)
    g.add_node("executor", executor)
    g.add_node("tools", tools)
    g.add_node("advance", advance)
    g.add_node("writer", writer)
    g.add_node("verify", verify)
    g.add_node("critic", critic)

    g.add_edge(START, "planner")
    g.add_edge("planner", "executor")
    g.add_conditional_edges("executor", route_after_executor, {"tools": "tools", "advance": "advance"})
    g.add_edge("tools", "executor")
    g.add_conditional_edges("advance", route_after_advance, {"executor": "executor", "writer": "writer"})
    g.add_edge("writer", "verify")
    g.add_edge("verify", "critic")
    g.add_conditional_edges("critic", route_after_critic, {"planner": "planner", "writer": "writer", "end": END})
    return g.compile()
