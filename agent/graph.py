"""LangGraph wiring.

M4:  START -> recall -> planner -> executor <-> tools            (ReAct loop per step)
                 ^          |  (plain answer)
                 |          v
                 |       advance --(more steps)--> executor
                 |          |  (plan done)
                 |          v
                 |        writer -> verify -> critic --(accept or revision limit)--> reflect -> END
                 |          ^                    |
                 |          +---(needs_rewrite)--+
                 +--------------(needs_research: append fix-up steps)

recall reads lessons + trusted sources from SQLite; reflect writes them back. use_memory=False skips both
(for with/without-memory comparisons).
"""
from langgraph.graph import END, START, StateGraph

from agent.nodes.advance import advance, route_after_advance
from agent.nodes.critic import critic, route_after_critic
from agent.nodes.executor import executor, route_after_executor
from agent.nodes.planner import planner
from agent.nodes.recall import recall
from agent.nodes.reflect import reflect
from agent.nodes.tools_node import tools
from agent.nodes.verify import verify
from agent.nodes.writer import writer
from agent.state import AgentState


def build_graph(use_memory: bool = True):
    g = StateGraph(AgentState)
    g.add_node("planner", planner)
    g.add_node("executor", executor)
    g.add_node("tools", tools)
    g.add_node("advance", advance)
    g.add_node("writer", writer)
    g.add_node("verify", verify)
    g.add_node("critic", critic)

    if use_memory:
        g.add_node("recall", recall)
        g.add_node("reflect", reflect)
        g.add_edge(START, "recall")
        g.add_edge("recall", "planner")
        g.add_edge("reflect", END)
    else:
        g.add_edge(START, "planner")
    g.add_edge("planner", "executor")
    g.add_conditional_edges("executor", route_after_executor, {"tools": "tools", "advance": "advance"})
    g.add_edge("tools", "executor")
    g.add_conditional_edges("advance", route_after_advance, {"executor": "executor", "writer": "writer"})
    g.add_edge("writer", "verify")
    g.add_edge("verify", "critic")
    g.add_conditional_edges("critic", route_after_critic, {"planner": "planner", "writer": "writer", "end": "reflect" if use_memory else END})
    return g.compile()
