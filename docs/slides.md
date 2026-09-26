# Slide deck outline (5 slides)

Self-Improving Research Agent · Techvruk AI Agentic System Challenge 2026

Each slide: title, on-slide content (keep it to what fits), a visual, and speaker notes (about 30-45 s each).

---

## Slide 1: The problem

**Title:** Research agents write confidently, and are wrong in the details

**On the slide**
- Task: a research agent. Give it a question, get a short cited report.
- The failures seen in early runs of this project:
  - price from a third-party blog when the task said *official page*
  - arithmetic in the head: 10 × $0.33 written as **$3.33**
  - a number cited to a source that does not contain it
  - "$0.095 per 1M dimensions" shown as "per GB-month"
- Goal: an agent that **checks its own work** and **does not repeat a mistake**

**Visual:** the rejected first draft of run #1 with "$3.33" highlighted next to the check output
`FAIL not_in_source: $3.33 ... computed without calculator`.

**Speaker notes:** Writing a report is easy for an LLM. Getting every number right is not. These four errors are
real, from my own development runs, and each one became a test case. So the design goal was verification and
memory, not prettier text.

---

## Slide 2: Architecture

**Title:** Plan → ReAct research → cited report → verify → critic → reflect

**On the slide**
- Mermaid workflow diagram from the README (recall → planner → executor ⇄ tools → advance → writer → verify →
  critic → routing → reflect → memory)
- Three routing outcomes from the critic: **accept** → reflect · **needs_rewrite** → writer · **needs_research** →
  planner adds fix-up steps (max 2 revisions)
- Patterns: Plan-and-Execute · ReAct · Tool use · Reflection · Long-term memory
- Tools: web_search (Tavily / DuckDuckGo), fetch_page (JS-rendering extract, focused passages), calculator

**Visual:** the diagram, with the two loops (ReAct loop, critic loop) and the memory arrow in colour.

**Speaker notes:** LangGraph with one shared state. The planner splits the task; each step is a ReAct loop with real
tools. Then two layers of review: a deterministic check that looks up every number in its cited source, and a
120B critic that also checks the task's constraints. The critic can send the report back to the writer or send the
agent back to research. Reflect writes lessons to SQLite; recall reads them before the next plan.

---

## Slide 3: Self-improvement proof

**Title:** Same model, fresh memory: 3/10 → 9/10, 1 → 0 revisions, −52% tokens

**On the slide**

| | Run #1 (no memory) | Run #4 (4 lessons + trusted URL) |
|---|---|---|
| First critique | 3/10 needs_research | **9/10 accept** |
| Revisions | 1 | **0** |
| Tokens | 28,411 | **13,604** |
| Plan step 1 | web search | fetch the official page directly |

- Controlled: same model (qwen3.8-27b, critic gpt-oss-120b), fresh DB, fallbacks off
- Example lesson learned: *"When a task requires a vendor's official pricing page, fetch that page first ... never
  relying on third-party snippets for the calculation."*
- Honest note: run #3 got worse (4/10); that led to a fix in how trusted pages are read

**Visual:** the Memory tab chart (critic score and revisions per run #1-#4) from the live app.

**Speaker notes:** Four runs in a row on the same task family, nothing changed but memory and two code fixes to how
memory is used. The first run needed a revision because it trusted blogs. By the fourth run the plan itself started
with the official page, the first draft passed, and it cost half the tokens. I show run #3 too, because it failed,
and fixing it is part of the story.

---

## Slide 4: Demo highlights

**Title:** What you see in the app

**On the slide**
- Live plan checklist; fix-up steps are marked *fix-up*
- Per-event trace: 🧠 memory · 🗺️ plan · 💭 think · 🔧 act · 👁️ observe · 🔎 verify · ⚖️ critique · 🎓 learn
- Critic score and revisions as metrics; report with a download button; tokens per model
- **Memory tab**: runs, lessons with seen / used / helpful counts, trusted sources with verified facts
- **Replay mode**: any recorded run, step by step, no API calls (quota-proof demo)
- Critic test suite: **6/6** known failure cases caught (unit error, 2 contradictions, misattribution, missed
  official page, calculator result not falsely flagged) + clean control accepted

**Visual:** two screenshots: run #1 trace at the CRITIQUE 3/10 event, and run #4 final report with 9/10.

**Speaker notes:** Point out that the UI is built from the same event stream as the CLI, so what you see is exactly
what the agent did. Replay mode exists because free quotas run out; it plays back real recorded runs.

---

## Slide 5: Tech and limits

**Title:** Built on free tiers, and what that costs

**On the slide**
- **Stack:** Python 3.11 · LangGraph · Groq gpt-oss-20b / gpt-oss-120b / qwen3.8-27b · NVIDIA NIM · Gemini 2.5 Flash ·
  Tavily · SQLite + FTS5 · Streamlit Community Cloud
- **Resilience:** 5-model fallback chain, rate-limit retry using provider wait times, graceful stop with a partial
  report, 15 live runs/day cap on the public demo, 81 unit tests
- **Limits:**
  - Groq ≈ 200k tokens/day per model; a broad comparison costs 70-100k
  - smaller models use tools less (20B rarely fetches pages without memory)
  - evidence is one task family and four runs, not a benchmark
  - recall is keyword-based, not semantic; public demo memory is shared and resets on restart
- **Next:** semantic recall, lesson pruning by helpfulness, scheduled re-research of trusted sources
- Live: https://asad-research-agent.streamlit.app/ · Code: github.com/shaikasadahmed2k23/self-improving-research-agent_Submission
- Built with Claude Code as a coding assistant; all APIs free tier

**Visual:** small logo row of the stack; the live URL as a QR code.

**Speaker notes:** Everything runs on free tiers, which shaped the design: the fallback chain, the token saver, the
replay mode. I want to be clear about the limits: the improvement is shown on one task family. The mechanism is
general; the proof is small.
