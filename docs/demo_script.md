# Demo video script (3:30 to 4:00)

**Goal:** show the agent working end to end, and show it learning from its own mistake.
**Recording:** 1920×1080, browser zoom 90%, screen recorder with microphone. Speak slowly; about 130 words a minute.

## Before recording

1. Open https://asad-research-agent.streamlit.app/ in **two browser tabs** (A and B). Wait for both to load (the
   first load after a sleep can take ~30 s).
2. In tab A, check the sidebar caption **"Live runs today: N/15"**. If N is 15, skip Part 2 (Replay covers the demo).
3. **Record Part 2 first, as its own clip.** A live run takes 1-3 minutes; you will speed it up in editing. If it
   stops on a quota error, keep the clip: it shows the graceful stop.
4. Have the GitHub README open in a third tab, scrolled to the **Results: self-improvement** table.
5. Close other tabs and notifications.

---

## Part 1: Intro (0:00-0:20)

**Screen:** tab A, the app's home page (sidebar visible, Research tab open).

**Say:**
> "This is my self-improving research agent. You give it a question, it plans the research, searches and reads
> pages with real tools, writes a report with citations, checks every number against its sources, has a critic
> review it, and stores what it learned for the next run. It's built with LangGraph, on free-tier models."

## Part 2: A live run (0:20-1:05)

**Clicks:**
1. Sidebar: **Mode → Live run**; **Memory on (recall + reflect)** stays on.
2. **Example task** dropdown → *"What is the monthly minimum spend on Pinecone's Standard plan?"*
3. Click **▶️ Run research**.
4. While it runs, hover over the left column **Plan** checklist, then over the **Trace** on the right.
5. When done, scroll to **Final report**; point at the **Critic score** metric and the **Tokens** line.

**Edit:** speed up the waiting part 4×; keep normal speed for the first plan and the final report.

**Say:**
> "I'll start a live run. First, recall looks up the memory for similar past tasks and their lessons. The planner breaks the task into steps. Each step is a ReAct loop: the model thinks, calls a
> tool, like web search or fetch page, reads the observation, and decides what to do next. When the plan is done,
> the writer produces a cited report, the verify step checks every number, and the critic gives a score and a
> verdict. Here it's accepted, and I can download the report as markdown."

*(If the run stopped on a quota error:)*
> "The free quota is used up for today, so the agent stops cleanly with a partial report instead of crashing. That's
> why there's a replay mode, which I'll use now."

## Part 3: The mistake (1:05-2:05)

**Clicks:**
1. Switch to tab B. Sidebar: **Mode → Replay a recorded run**.
2. **Recorded run** → `m4-qwen-run1-before-10gb`. Set **Replay speed** to **0.05**.
3. Click **▶️ Replay**.
4. Pause the talking at the **🧠 MEMORY** event (empty), then at the **🔎 VERIFY** event, then at **⚖️ CRITIQUE**.
   Point at the left column: **Critic score 3/10**, then the new steps marked ***fix-up***.
5. Let it finish; point at **Critic score 9/10** and **Revisions 1**, then at the **🎓 LEARN** event.

**Say:**
> "This is a recorded real run with an empty memory. The task says: use Pinecone's official pricing page. The agent
> searched, but the page it fetched didn't show the price, so it used blogs, and it wrote 3 dollars 33, which is
> wrong: 10 times 33 cents is 3.30. The citation check catches it: that number is not in any source, and it wasn't
> computed with the calculator. The critic gives it 3 out of 10 and flags a constraint violation: the official page
> wasn't used. So it doesn't just rewrite: the planner adds fix-up steps. The agent fetches the official page again,
> uses the calculator, and the new report passes with 9 out of 10. Then reflect saves two lessons: fetch the
> official page first, and apply the plan's minimum charge."

## Part 4: The improvement (2:05-2:50)

**Clicks:**
1. Still in tab B, **Recorded run** → `m4-qwen-run4-after-25gb`. Click **▶️ Replay**.
2. Pause at the **🧠 MEMORY** event: show the recalled lessons and the trusted URL.
3. Point at the **Plan**: step 1 is "Fetch https://www.pinecone.io/pricing ...".
4. When it finishes: **Critic score 9/10**, **Revisions 0**, and the **Tokens: 13,604** caption under the report.

**Say:**
> "This is the fourth run on the same kind of question, same model, same settings. Now recall finds four lessons
> and a trusted source. Look at the plan: step one is to fetch the official page, the lesson changed the plan
> itself. The first draft passes with 9 out of 10, no revision, and it used about half the tokens: 13.6 thousand
> instead of 28 thousand."

## Part 5: Memory and evidence (2:50-3:30)

**Clicks:**
1. Click the **Memory** tab.
2. Point at the **Critic score and revisions per run** chart, then the **Lessons** table (columns
   `times_used`, `times_helpful`), then **Trusted sources** (`pinecone.io/pricing`, verified count, facts).
3. Switch to the GitHub tab: the **Results: self-improvement** table, then scroll to **Results: critic test cases**.

**Say:**
> "The Memory tab shows what it learned: the lessons, how often each one was used and helped, and which sources were
> verified, down to the individual facts. In the README, this is the controlled comparison: fresh database,
> fallbacks off, so the model couldn't change. First critique went from 3 to 9, revisions from 1 to 0. And I also
> show run three, where memory didn't help, and what I fixed. The critic is tested separately on six real failure
> cases, like unit errors and contradictions between sources, and it catches all six."

## Part 6: Close (3:30-3:50)

**Screen:** the GitHub README, **Limitations** and **Disclosure** sections, then back to the app.

**Say:**
> "Everything runs on free tiers: Groq, Gemini and Tavily, so quotas are the main limit, and the evidence is one task
> family, not a benchmark. The code, samples and recorded runs are all in the repo, and you can replay these runs
> yourself on the live site. Thanks for watching."

---

## Checklist after recording
- Length between 3:30 and 4:30 after editing (limit is 5:00).
- The numbers said out loud match the screen: 3/10 → 9/10, 1 → 0 revisions, 28,411 → 13,604 tokens.
- No API keys or `.env` visible anywhere (the sidebar only shows model names).
- Upload (unlisted YouTube or Google Drive, "anyone with the link"), then add the link to the README and the
  submission form.
