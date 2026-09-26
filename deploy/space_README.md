---
title: Self-Improving Research Agent
emoji: 🔎
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 8501
pinned: false
short_description: Research agent that learns lessons and trusted sources
---

# Self-Improving Research Agent

A research agent that plans research steps, runs each one as a ReAct tool loop (web search, page fetch, calculator),
writes a cited markdown report, checks every cited number against its source, has a critic review the draft, and
**learns from each run**: lessons and trusted sources are stored in SQLite and used before the next plan.

- **Research tab:** run a task live (plan checklist + step-by-step trace), or pick **Replay a recorded run** to watch a
  complete recorded run without any LLM calls.
- **Memory tab:** lessons, trusted sources, and the score / revisions / tokens of every run. The seed memory comes from
  development runs where the agent learned to use Pinecone's official pricing page: the same kind of task went from
  1 revision and 28,411 tokens to 0 revisions and 13,604 tokens.

This demo runs on free-tier APIs (Groq, NVIDIA NIM, Gemini, Tavily) in token-saver mode. When every model is out of
quota, the app stops gracefully with a partial report; use Replay mode instead.

Source: https://github.com/shaikasadahmed2k23/self-improving-research-agent_Submission
