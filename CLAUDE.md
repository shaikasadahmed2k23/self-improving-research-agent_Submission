# CLAUDE.md — Self-Improving Research Agent

Contest entry for the Techvruk "AI Agentic System Challenge" (see ASSIGNMENT.md). **Deadline: Sep 27, 2026, 11:30 PM.**
Repo: https://github.com/shaikasadahmed2k23/self-improving-research-agent_Submission (branch `main`).

## What it is
A research agent that takes a topic or question, plans research steps, runs each step as a ReAct tool loop (search, fetch, calculate), writes a cited markdown report, reviews it with a critic, and **learns from each run**: lessons and trusted sources are stored in SQLite and checked before the next plan.
Pattern: Plan-and-Execute + ReAct executor + Critic/Reflection loop.

## Stack
- Python 3.11 (`.venv`), LangGraph (shared `AgentState`), langchain-core 1.x
- LLM: Groq (primary) with Gemini (fallback), wired in `agent/llm.py:get_llm(role, tools=, schema=)`
- Search: Tavily (primary) with DuckDuckGo (`ddgs`) as fallback; pages are fetched with httpx + trafilatura
- Memory: SQLite (`data/agent_memory.db`); UI: Streamlit; deploy target: HF Spaces

## Models (set in `.env`, defaults in `agent/config.py`)
- `GROQ_MODEL=openai/gpt-oss-20b`: dev default for every role. **Groq Llama models are enterprise-only now.**
- `GROQ_MODEL_STRONG=openai/gpt-oss-120b`: used by the planner, writer and critic when `USE_STRONG_MODEL=true` (final runs and demo)
- `GEMINI_MODEL=gemini-2.5-flash`: fallback
- gpt-oss is a reasoning model. Always use `reasoning_effort=low` (`GROQ_REASONING_EFFORT`) and `max_tokens` ≥ 512 (`LLM_MAX_TOKENS=4096`), or the reasoning uses up the whole budget and the visible content comes back empty.
- gpt-oss sometimes writes citations as fullwidth `【n】`; `normalize_citations()` in `agent/nodes/writer.py` converts them.

## How to run
```powershell
.venv\Scripts\python scripts\check_setup.py            # verify keys: Groq, Gemini, Tavily, DDG
.venv\Scripts\python cli.py "your research task" --out reports\x.md
.venv\Scripts\python -m pytest tests -q
```

## Rules
- **Never create or read `.env`**; only edit `.env.example`. `.env`, `data/*.db` and `reports/*` are gitignored.
- End commits with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The README must include a Disclosure section: built with Claude Code as a coding assistant; all APIs are free tier (Groq, Gemini, Tavily).
- The full build plan is in `C:\Users\DELL\.claude\plans\pasted-content-id-339d-read-assignment-breezy-tower.md`.

## Milestone status
| # | Milestone | Status |
|---|---|---|
| M0 | Setup, config, `check_setup.py` | ✅ done |
| M1 | Thin end-to-end: planner → executor (1 search per step) → writer, CLI | ✅ done |
| M2 | ReAct executor: tools loop (web_search, fetch_page, calculator), advance node, context from earlier steps, sequential citations, duplicate-call guard | ✅ done |
| M3 | Critic + routing (rewrite / replan / accept, max 2 revisions) | todo |
| M4 | SQLite memory: recall + reflect + save_report | todo |
| M5 | Streamlit UI with live trace + Memory tab | todo |
| M6 | Hardening: fallback test, tool errors, retries, tests | todo |
| M7 | Deploy to HF Spaces | todo |
| M8 | README, samples, slides, demo video | todo |

## Critic test cases for M3 (real errors seen in M1 output)
The critic must flag these:
1. **Unit error**: Weaviate "$0.095 per million dimensions" was shown as "$0.095 / GB-month" in the pricing table.
2. **Contradiction**: Qdrant has a "$25 minimum" in one place but "no minimum" in another (and storage is both $0.12 and $0.28/GB).
   Also seen in M2: Pinecone reads are "$16-18 / M units" in one step but "$0.00000025/RU" (= $0.25/M) in another.
3. **Misattributed citation** (M2): "$0.33/GB" was cited to pinecone.io/pricing, but that page's static HTML has no per-GB
   rate; the figure came from third-party snippets (spendark, pecollective, withorb). Idea: a deterministic grounding
   check that every number next to a citation [n] appears in source n's stored `content`.
Test tasks: `Compare the pricing of the top 3 managed vector databases` and
`Using Pinecone's official pricing page, what would 10 GB of storage cost per month on the Standard plan, and how does that compare to the plan's monthly minimum?`

## Known behaviour (M2)
- gpt-oss-20b rarely uses `fetch_page` or `calculator` unless the task explicitly calls for them (it prefers `web_search`).
- The graph: planner → executor ⇄ tools → advance → (executor | writer) → END. Recursion limit 150 in cli.py.
