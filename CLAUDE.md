# CLAUDE.md — Self-Improving Research Agent

Contest entry for the Techvruk "AI Agentic System Challenge" (see ASSIGNMENT.md). **Deadline: Sep 27, 2026, 11:30 PM.**
Repo: https://github.com/shaikasadahmed2k23/self-improving-research-agent_Submission (branch `main`).
**Live app: https://asad-research-agent.streamlit.app/** (Streamlit Community Cloud; redeploys automatically on push to `main`).

## What it is
A research agent that takes a topic or question, plans research steps, runs each step as a ReAct tool loop (search, fetch, calculate), writes a cited markdown report, reviews it with a critic, and **learns from each run**: lessons and trusted sources are stored in SQLite and checked before the next plan.
Pattern: Plan-and-Execute + ReAct executor + Critic/Reflection loop.

## Stack
- Python 3.11 (`.venv`), LangGraph (shared `AgentState`), langchain-core 1.x
- LLM: `agent/llm.py:get_llm(role, tools=, schema=)`. Fallback chain: the role's Groq model → the other gpt-oss model →
  NVIDIA NIM (`NVIDIA_MODEL`, only if `NVIDIA_API_KEY` is set) → Gemini
- Search: Tavily (primary) with DuckDuckGo (`ddgs`) as fallback. `fetch_page` uses **Tavily Extract** first (it renders
  JavaScript, e.g. pinecone.io/pricing's price table) and falls back to httpx + trafilatura
- Memory: SQLite + FTS5 (`data/agent_memory.db`, override with `MEMORY_DB_PATH`; `agent/memory/schema.sql`, `store.py`).
  UI: Streamlit; deploy target: **Streamlit Community Cloud** (HF Docker Spaces now need PRO, see M7)

## Models (set in `.env`, defaults in `agent/config.py`)
- `GROQ_MODEL=openai/gpt-oss-20b`: dev default for every role. **Groq Llama models are enterprise-only now.**
- `GROQ_MODEL_STRONG=openai/gpt-oss-120b`: **always used by the critic**; also used by the planner and writer when `USE_STRONG_MODEL=true`
- `GEMINI_MODEL=gemini-2.5-flash`: last-resort fallback
- **Free-tier quotas are the real constraint.** Groq per model: **200k tokens/day** (rolling 24h), 1000 requests/day,
  8000 tokens/min. Only prompt tokens are counted up front ("Requested" in the 429 message); `max_tokens` is not.
  Gemini 2.5 Flash: only **20 requests/day**. Measured cost per run: narrow task ≈ 15-25k tokens; broad comparison with
  revisions ≈ 70-100k. The CLI prints tokens per model: if the 20B line is tiny and 120B is large, 20B hit its quota and
  the chain fell back (this skews comparisons). Check a model's daily use: a 429 message says "Used N".
- **Dev mode:** `TOKEN_SAVER=true` + `cli.py --dev 1..4` (short preset tasks). Saver limits are caps: 3 steps,
  3 LLM calls/step, 1 revision, 1200-char page views, 3 results × 300-char snippets, 600-char step context.
- **NVIDIA NIM** (added Sep 26): OpenAI-compatible (`langchain-openai`), about 40 requests/min, no daily cap published,
  development use only. **NIM retired gpt-oss-120b on 2026-09-03**; the default is `nvidia/nemotron-3-super-120b-a12b`.
  Structured output on NIM uses JSON mode + pydantic validation + one retry (`json_mode_structured`). **Works with the new
  key (Sep 26)**: tool calling OK (correct `fetch_page` with focus, 2 s) and strict json_schema also parsed. The old key
  returned 403 for every model.
- Other free options researched (Sep 26): Cerebras is now a $5 / 30-day trial and needs a card (1M tokens/day,
  gpt-oss-120b). OpenRouter `:free` allows only 50 requests/day. GitHub Models is retired.
- **`qwen/qwen3.8-27b`** (Groq, third quota pool, `GROQ_MODEL_EXTRA`; chain: 20B → 120B → qwen → NIM → Gemini):
  tool calling works well. Free tier: **1000 output tokens/min, and `max_tokens` counts up front**, so it is capped at 1000
  (`GROQ_MAX_TOKENS_CAP`) with 6 retries (429s carry a short retry-after). A run takes about 10 min. Use it with
  `reasoning_effort="none"`: with thinking on, the thinking alone hit the 1000 cap. **Groq does not enforce strict
  json_schema for qwen**: it invented keys (`".lessons"`), which pydantic silently turned into empty defaults. So qwen uses
  function calling, whose arguments Groq validates (`uses_strict_schema()` = gpt-oss only).
- gpt-oss is a reasoning model. Always use `reasoning_effort=low` (`GROQ_REASONING_EFFORT`) and `max_tokens` ≥ 512 (`LLM_MAX_TOKENS=4096`), or the reasoning uses up the whole budget and the visible content comes back empty.
- gpt-oss writes citations in its native formats `【n】`, `【n†L1-L3】` and `[n†source]`; `normalize_citations()` in
  `agent/nodes/writer.py` converts them to `[n]`.
- Structured output on gpt-oss uses Groq `json_schema` with `strict=True`. The default function calling sometimes produced
  invalid JSON (`'`), and non-strict json_schema made the model echo the schema back.
- gpt-oss-120b sometimes calls a non-existent built-in `find` tool (Groq returns 400 `tool_use_failed`). The executor
  corrects it once, then answers without tools.

## How to run
```powershell
.venv\Scripts\python scripts\check_setup.py            # verify keys: Groq, NIM, Gemini, Tavily, DDG
.venv\Scripts\python cli.py "your research task" --out reports\x.md
$env:TOKEN_SAVER="true"; .venv\Scripts\python cli.py --dev 2   # cheap dev run (add --no-memory to skip recall/reflect)
.venv\Scripts\python scripts\show_memory.py            # runs, lessons, trusted sources
.venv\Scripts\python -m streamlit run app.py           # UI; "Replay a recorded run" needs no LLM calls
.venv\Scripts\python scripts\log_to_trace.py run.log samples\traces\x.jsonl   # old CLI log -> replayable trace
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
| M4 | SQLite memory: recall + reflect + lessons + URL-level trusted sources + save_report | ✅ done (see below) |
| M5 | Streamlit UI (`app.py`): live plan checklist + per-event trace, report + download, replay of recorded runs, Memory tab (charts, lessons, sources, runs), memory on/off | ✅ done (tested with AppTest on replays; live path tested with a stubbed runner, **not yet with a real LLM run in the browser**) |
| M6 | Hardening: rate-limit retry/backoff, graceful stop with a partial report + trace, tool errors as observations, UI quota message → Replay | ✅ done |
| M7 | Deploy: Streamlit Community Cloud (HF blocked: Docker Spaces need PRO) + daily live-run cap | ✅ live at https://asad-research-agent.streamlit.app/ |
| M8 | README, samples, slides, demo video | README + `samples/outputs/` (3 reports from traces) + `docs/slides.md` + `docs/demo_script.md` + `docs/presentation.pptx/.pdf` (built by `docs/build_slides.js`; PDF via LibreOffice, installed Sep 26) done; **still todo: record the video, add its link to the README** |

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

## M4 memory: how it works and results
- **recall** (no LLM): full-text search for similar past tasks (≥ 2 shared content terms), the top 5 lessons, and trusted URLs
  from those runs → `state["memory"]`. The lessons and trusted sources go into the **planner** prompt; trusted URLs also go
  to the **executor**; all lessons go to the **writer** (the reflection's categories are unreliable).
- **reflect**: (1) URL-level source trust from the final citation check (verified / failed counts + verified facts),
  (2) one reflect-model call → 1-3 lessons + `source_urls` (stored as *suggested* only if `fetch_page` can read them),
  (3) recalled lessons are marked used / helpful (helpful = accepted with 0 revisions), (4) the run row and the report file.
  Lessons that are near-duplicates (word Jaccard ≥ 0.5) only raise `times_seen`.
- **Fair before/after on qwen** (Sep 26; all roles on qwen, critic on 120B, `LLM_FALLBACKS=false`, `TOKEN_SAVER=true`,
  fresh `data/agent_memory_qwen.db`). Traces are in `samples/traces/m4-qwen-*.jsonl` and replay in the UI:
  | Run | Task | Memory used | First critique | Final | Revisions | Tokens |
  |---|---|---|---|---|---|---|
  | #1 before | 10 GB (`--dev 2`) | none | 3/10 needs_research (third-party "$3.33", official page not used) | 9 accept | 1 | 28,411 |
  | #2 | 25 GB (`--dev 4`) | 2 lessons + URL | 6/10 needs_rewrite (derived "$41.75" cited to the page) | 9 accept | 1 | 18,223 |
  | #3 | 40 GB | 3 lessons + URL | 4/10 (directed-fetch focus missed $0.33 → third-party) | 8 (limit) | 1 | 38,509 |
  | **#4 after** | 25 GB (`--dev 4`) | 4 lessons + URL | **9/10 accept** | 9 accept | **0** | **13,604 (−52% vs #1)** |
  Fixes between runs: lessons go to the writer (after #2); verified facts are added to the focus of *any* fetch of a
  trusted URL, digit terms weigh 3x, and passages are picked by greedy term coverage (after #3).
- 20B (Sep 26): before run = 1 revision, 17,041 tokens (`samples/traces/m4-20b-before-10gb.jsonl`). The 20B after run
  was not possible: 20B hit its daily quota (the attempt silently fell back to 120B, which is why `LLM_FALLBACKS` exists).

## M5 UI notes
- `agent/runner.py:stream_run()` is the single entry point (CLI + UI): it yields `(node, delta)` with JSON-safe fields only
  and records `data/traces/*.jsonl` (gitignored). `samples/traces/` holds committed demo traces. **Replay mode doubles as a
  quota-proof demo fallback.**
- The sidebar memory DB selector sets `config.MEMORY_DB_PATH` for the process (fine for a single-user demo; revisit for HF).
- Tests: `tests/test_app.py` drives `app.py` with `streamlit.testing.v1.AppTest` (replay, memory tab, toggle → `use_memory`).

## M6 hardening
- `llm.with_rate_limit_retry` wraps every model in the chain. Short 429s (per-minute caps) are waited out on the same model:
  it uses the provider's wait time (Retry-After header, Groq "try again in 1m2.5s", Gemini `retryDelay`), else exponential
  backoff of 2 s × 2^n, up to `LLM_RATE_RETRIES=4`. Waits longer than `LLM_MAX_WAIT=65` s (daily quota) are re-raised at once,
  so the fallback chain moves on. SDK `max_retries=1` only covers connection errors.
- `runner._live` never raises. On failure it yields `("stopped", {stopped: {kind: quota|error, message, detail}, draft,
  report_path})`. The partial report is the last draft if there is one, else the finished step findings + "Not researched
  yet" + a Sources list; it is saved as `reports/<date>-<slug>-partial.md`, and the trace JSONL is kept. The CLI prints
  "RUN STOPPED" and exits with code 2. The UI shows the error and, for quota, points to **Replay mode**. Stopped runs are
  not written to memory (reflect never ran).
- The tools node wraps each tool call; any exception becomes an `Error from <tool>: ...` observation.
- Verified end to end with invalid keys for every provider (no quota used): partial report saved, exit code 2.

## M7 deploy
- **HF Spaces is blocked**: `create_repo(space_sdk="docker")` returns **402**: "hosting Gradio and Docker Spaces on free
  cpu-basic requires a PRO subscription" (Sep 26). The built-in Streamlit SDK is deprecated (HF says use Docker). Nothing
  was created on HF. `scripts/deploy_hf.py` + `Dockerfile` + `deploy/space_README.md` work as-is if the account gets PRO.
- **Streamlit Community Cloud** (the user chose it): deploys from the public GitHub repo, branch `main`, file `app.py`. There
  is no deploy API, so the user clicks through share.streamlit.io. Secrets: paste `deploy/streamlit_secrets.local.toml`
  (gitignored, generated from `.env` by `scripts/make_streamlit_secrets.py`; template: `deploy/streamlit_secrets.toml`).
  Root-level secrets become environment variables, which `agent/config.py` reads. Demo defaults are in the same TOML.
- `app.py:seed_memory()` copies `samples/seed_memory.db` (the qwen M4 memory: 4 runs, 5 lessons) to `MEMORY_DB_PATH` on
  a fresh deployment. `samples/traces/` provides the Replay runs.
- Public demo caveat: anyone can use the app's API quotas and memory (shared SQLite, resets when the app restarts).
- **Verified Sep 26** with headless Edge (Playwright, `channel="msedge"`; the Chromium download timed out) as an
  anonymous visitor: the app loads (the `/-/login` 303 is only Streamlit Cloud's cookie handshake, not a private app),
  the Memory tab shows the seed (4 runs, 5 lessons, 1 trusted source; DB at `/mount/src/<repo>/data/agent_memory.db`),
  and replaying `m4-qwen-run4-after-25gb` shows 9/10, 0 revisions, 19 events, the download button and 13,604 tokens.
  The sidebar confirmed the secrets: 20B executor, 120B critic, token saver on, fallbacks on.
- **Daily live-run cap** (`agent/usage.py`): `DAILY_RUN_CAP` (default 15, 0 = no limit; set in the Streamlit secrets)
  counts UI live runs per UTC day in `data/usage.sqlite3` (not `*.db`, so the memory-DB picker ignores it). Check and
  increment happen in one `BEGIN IMMEDIATE` transaction and are re-checked on click. At the cap, the Run button is
  disabled and a message points to Replay mode (with the time until the reset). The CLI is not capped. Counts reset
  when the app restarts (the disk is ephemeral), which is acceptable for a demo.

## Known behaviour
- gpt-oss-20b daily quota recovers slowly when it is exhausted: about 1.4k tokens per 10 min (Sep 26 morning).
- **Tool use:** gpt-oss-20b rarely calls `fetch_page`/`calculator` unless the task asks for them (broad task: 0 fetches).
  **gpt-oss-120b uses them readily** (broad task: 5 fetches incl. `focus`; narrow task: fetch + calculator).
  Consider the 120B model for the executor in the demo if quota allows.
- The graph: recall → planner → executor ⇄ tools → advance → (executor | writer) → verify → critic →
  (reflect → END | writer | planner). `build_graph(use_memory=False)` / `--no-memory` skips recall and reflect.
  Recursion limit 250 in cli.py.
- **Directed fetch** (executor, no LLM call): at the start of a step, if the goal contains a URL, or names a site that has a
  trusted page in memory, `fetch_page` is called on it first. Its focus comes from the task and goal terms plus that
  page's verified facts. This is needed because 20B ignores "fetch_page <URL>" in step goals and in prompts and searches again.
- `page_view(focus=...)` ranks passages by distinct focus terms, then by the number of `$` amounts. Before this, the first
  matches (page header) used up the 1200-char budget and $0.33 on pinecone.io/pricing was never shown.
- 20B reflection with strict json_schema returned `lessons=[]` when the prompt allowed "no lessons". The prompt now requires
  at least 1 (reflect only calls the LLM when the run had problems).
- Duplicate tool calls are blocked within a step only; the same page can be fetched again in later steps.
- When every provider is out of quota the run crashes and partial work is lost. Fix in M6 (graceful stop + partial report).
- The planner sometimes writes "as of 2024-2025" even though today's date is in its prompt.
