# CLAUDE.md — Self-Improving Research Agent

Contest entry for the Techvruk "AI Agentic System Challenge" (see ASSIGNMENT.md). **Deadline: Sep 27, 2026, 11:30 PM.**
Repo: https://github.com/shaikasadahmed2k23/self-improving-research-agent_Submission (branch `main`).

## What it is
A research agent that takes a topic or question, plans research steps, runs each step as a ReAct tool loop (search, fetch, calculate), writes a cited markdown report, reviews it with a critic, and **learns from each run**: lessons and trusted sources are stored in SQLite and checked before the next plan.
Pattern: Plan-and-Execute + ReAct executor + Critic/Reflection loop.

## Stack
- Python 3.11 (`.venv`), LangGraph (shared `AgentState`), langchain-core 1.x
- LLM: `agent/llm.py:get_llm(role, tools=, schema=)`. Fallback chain: the role's Groq model → the other gpt-oss model → Gemini
- Search: Tavily (primary) with DuckDuckGo (`ddgs`) as fallback. `fetch_page` uses **Tavily Extract** first (it renders
  JavaScript, e.g. pinecone.io/pricing's price table) and falls back to httpx + trafilatura
- Memory: SQLite (`data/agent_memory.db`); UI: Streamlit; deploy target: HF Spaces

## Models (set in `.env`, defaults in `agent/config.py`)
- `GROQ_MODEL=openai/gpt-oss-20b`: dev default for every role. **Groq Llama models are enterprise-only now.**
- `GROQ_MODEL_STRONG=openai/gpt-oss-120b`: **always used by the critic**; also used by the planner and writer when `USE_STRONG_MODEL=true`
- `GEMINI_MODEL=gemini-2.5-flash`: last-resort fallback
- **Free-tier quotas are the real constraint.** Groq: ~200k tokens/day **per model** (rolling 24h). Gemini 2.5 Flash: only
  **20 requests/day**. Measured cost per run: narrow task on 120B ≈ 15k tokens; broad comparison with revisions ≈ 70-100k.
  So there is room for only a few full runs per model per day. Save quota for the demo. The CLI prints tokens per model.
- The only other chat model this Groq key can use is `qwen/qwen3.8-27b` (untested; could serve as a third quota pool).
- gpt-oss is a reasoning model. Always use `reasoning_effort=low` (`GROQ_REASONING_EFFORT`) and `max_tokens` ≥ 512 (`LLM_MAX_TOKENS=4096`), or the reasoning uses up the whole budget and the visible content comes back empty.
- gpt-oss writes citations in its native formats `【n】`, `【n†L1-L3】` and `[n†source]`; `normalize_citations()` in
  `agent/nodes/writer.py` converts them to `[n]`.
- Structured output on gpt-oss uses Groq `json_schema` with `strict=True`. The default function calling sometimes produced
  invalid JSON (`'`), and non-strict json_schema made the model echo the schema back.
- gpt-oss-120b sometimes calls a non-existent built-in `find` tool (Groq returns 400 `tool_use_failed`). The executor
  corrects it once, then answers without tools.

## How to run
```powershell
.venv\Scripts\python scripts\check_setup.py            # verify keys: Groq, Gemini, Tavily, DDG
.venv\Scripts\python cli.py "your research task" --out reports\x.md
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python scripts\critic_eval.py            # critic on the fixed failure cases (uses about 40k 120B tokens)
```
To run every role on the 120B model for one run (PowerShell): `$env:GROQ_MODEL="openai/gpt-oss-120b"; .venv\Scripts\python cli.py "..."`

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
| M3 | Deterministic citation check + 120B critic + routing (accept / needs_rewrite / needs_research → fix-up steps), max 2 revisions | ✅ done |
| M4 | SQLite memory: recall + reflect + save_report | todo |
| M5 | Streamlit UI with live trace + Memory tab | todo |
| M6 | Hardening: fallback test, tool errors, retries, tests. **When all models are out of quota, save the partial report + trace instead of crashing.** | todo |
| M7 | Deploy to HF Spaces | todo |
| M8 | README, samples, slides, demo video | todo |

## Critic test cases (M3): results
`scripts/critic_eval.py` runs fixed test inputs that reproduce each real failure: **6/6 as expected** (Sep 26).
| Case | Caught by | Result |
|---|---|---|
| 1. Unit error: Weaviate "$0.095 per 1M dimensions" shown as "/ GB-month" | deterministic `unit_mismatch` + critic | ✅ needs_rewrite |
| 2a. Contradiction: Qdrant "$25 minimum" vs "no minimum" | critic | ✅ needs_rewrite |
| 2b. Contradiction: Pinecone reads "$16/M" vs "$0.00000025/RU" (= $0.25/M) | critic (converted the units itself) | ✅ needs_rewrite |
| 3. Misattributed citation: $0.33 cited to a source that lacks it | deterministic `not_in_source` (also names where it really is) + critic | ✅ |
| 4. Task says "official pricing page" but it was never fetched | critic `constraint_violations` → fix-up steps "fetch_page https://www.pinecone.io/pricing/ ..." | ✅ needs_research |
| 4b. Calculator result $3.30 must not be flagged | deterministic `calculated` | ✅ |
| Control: clean, consistent report | critic | ✅ accept (8/10) |

**Correction to case 3 (found in M3):** pinecone.io/pricing *does* list $0.33/GB/mo, but only after JavaScript runs.
The M2 "misattribution" was a false positive caused by (a) the httpx fetch not rendering JavaScript and (b)
`…/pricing` and `…/pricing/` being registered as two sources. Fixed with Tavily Extract + canonical-URL deduplication.

Live runs (Sep 25-26):
- Official-page task, all roles on 120B: web_search → fetch_page ×2 → calculator; the check verified $0.33 and $50 on the
  official page and marked $3.30 as calculated; the critic accepted with 9/10 at revision 0; about 15k tokens.
- Official-page task on 20B: the critic flagged the constraint → needs_research → fix-up steps fetched the official page → revision.
- Broad comparison on 120B: the critic caught an unsupported "$0.0001 per 1M queries" → needs_research → fix-ups
  fetched 3 official pages. Both broad runs ran out of daily quota before finishing revision 2.

Test tasks: `Compare the pricing of the top 3 managed vector databases` and
`Using Pinecone's official pricing page, what would 10 GB of storage cost per month on the Standard plan, and how does that compare to the plan's monthly minimum?`

## Known behaviour
- **Tool use:** gpt-oss-20b rarely calls `fetch_page`/`calculator` unless the task asks for them (broad task: 0 fetches).
  **gpt-oss-120b uses them readily** (broad task: 5 fetches incl. `focus`; narrow task: fetch + calculator).
  Consider the 120B model for the executor in the demo if quota allows.
- The graph: planner → executor ⇄ tools → advance → (executor | writer) → verify → critic → (END | writer | planner).
  Recursion limit 250 in cli.py.
- Duplicate tool calls are blocked within a step only; the same page can be fetched again in later steps.
- When every provider is out of quota the run crashes and partial work is lost. Fix in M6 (graceful stop + partial report).
- The planner sometimes writes "as of 2024-2025" even though today's date is in its prompt.
