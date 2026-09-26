// Builds docs/presentation.pptx from the outline in docs/slides.md.
// Needs: npm install pptxgenjs. Run: node docs/build_slides.js  (then LibreOffice: soffice --headless --convert-to pdf docs/presentation.pptx)
// docs/architecture.png is rendered from docs/architecture.mmd with mermaid (dark theme, 3x scale).
const pptxgen = require("pptxgenjs");
const path = require("path");

const REPO = path.resolve(__dirname, "..");
const C = {
  bg: "0E1117", card: "161B26", card2: "1C2332", line: "2A3345",
  text: "E6EDF3", muted: "8B98A9", mint: "3DDC97", amber: "F5B83D", red: "FF6B6B", blue: "7AA2F7",
};
const HEAD = "Arial", BODY = "Calibri", MONO = "Courier New";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.title = "Self-Improving Research Agent";
pres.author = "shaikasadahmed2k23";

const W = 13.333, M = 0.6;

function base(kicker, title) {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  s.addText(kicker, { x: M, y: 0.35, w: W - 2 * M, h: 0.35, fontFace: BODY, fontSize: 13, color: C.mint, bold: true,
    charSpacing: 2, margin: 0, isTextBox: true });
  s.addText(title, { x: M, y: 0.7, w: W - 2 * M, h: 0.75, fontFace: HEAD, fontSize: 30, bold: true, color: C.text,
    margin: 0, valign: "top", isTextBox: true });
  return s;
}

function card(s, x, y, w, h, fill = C.card) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: C.line, width: 1 }, rectRadius: 0.12 });
}

function dot(s, x, y, color, label) {
  s.addShape(pres.shapes.OVAL, { x, y, w: 0.42, h: 0.42, fill: { color } });
  s.addText(label, { x, y, w: 0.42, h: 0.42, fontFace: HEAD, fontSize: 14, bold: true, color: C.bg, align: "center",
    valign: "middle", margin: 0, isTextBox: true });
}

function footer(s, n) {
  s.addText(`Self-Improving Research Agent  ·  ${n} / 5`, { x: M, y: 7.05, w: 6, h: 0.3, fontFace: BODY, fontSize: 10,
    color: C.muted, margin: 0, isTextBox: true });
}

// ---------- Slide 1: Problem ------------------------------------------------------------------------------------
{
  const s = base("SELF-IMPROVING RESEARCH AGENT  ·  TECHVRUK AI AGENTIC SYSTEM CHALLENGE 2026",
    "Confident reports, wrong details");
  s.addText("A research agent: ask a question, get a short report with citations. These are real failures from early runs of this project:",
    { x: M, y: 1.55, w: 6.2, h: 0.7, fontFace: BODY, fontSize: 16, color: C.muted, margin: 0, isTextBox: true });

  const fails = [
    ["Wrong source", "Price copied from a third-party blog when the task said \"official page\""],
    ["Mental arithmetic", "10 × $0.33 written as $3.33"],
    ["Misattributed citation", "A number cited to a source that does not contain it"],
    ["Unit mix-up", "\"$0.095 per 1M dimensions\" shown as \"per GB-month\""],
  ];
  fails.forEach(([t, d], i) => {
    const y = 2.4 + i * 1.0;
    card(s, M, y, 6.2, 0.85);
    dot(s, M + 0.22, y + 0.21, C.red, "✗");
    s.addText([
      { text: t, options: { bold: true, color: C.text, fontSize: 16, breakLine: true } },
      { text: d, options: { color: C.muted, fontSize: 13 } },
    ], { x: M + 0.85, y: y + 0.08, w: 5.2, h: 0.7, fontFace: BODY, valign: "middle", margin: 0, isTextBox: true });
  });

  // Right: the rejected first draft and what the check said
  const rx = 7.3, rw = W - M - rx;
  card(s, rx, 1.55, rw, 3.6, C.card2);
  s.addText("Run #1, first draft", { x: rx + 0.3, y: 1.72, w: rw - 0.6, h: 0.3, fontFace: BODY, fontSize: 12, bold: true,
    color: C.muted, margin: 0, isTextBox: true });
  s.addText([
    { text: "Calculation for 10 GB: 10 GB × $0.33/GB = ", options: { color: C.text } },
    { text: "$3.33 per month", options: { color: C.red, bold: true } },
    { text: " [1][2][3]", options: { color: C.blue } },
  ], { x: rx + 0.3, y: 2.1, w: rw - 0.6, h: 0.8, fontFace: BODY, fontSize: 17, margin: 0, isTextBox: true });
  s.addText("citation check", { x: rx + 0.3, y: 3.0, w: rw - 0.6, h: 0.3, fontFace: BODY, fontSize: 12, bold: true,
    color: C.amber, margin: 0, isTextBox: true });
  s.addText("FAIL not_in_source: $3.33 cited [1, 2, 3]\nnot found in any source (unsupported or computed without calculator)",
    { x: rx + 0.3, y: 3.32, w: rw - 0.6, h: 0.75, fontFace: MONO, fontSize: 11, color: C.amber, margin: 0, isTextBox: true });
  s.addText("critic (gpt-oss-120b)", { x: rx + 0.3, y: 4.15, w: rw - 0.6, h: 0.3, fontFace: BODY, fontSize: 12, bold: true,
    color: C.amber, margin: 0, isTextBox: true });
  s.addText("3/10 · needs_research: \"the task required the official pricing page\"",
    { x: rx + 0.3, y: 4.45, w: rw - 0.6, h: 0.55, fontFace: MONO, fontSize: 11, color: C.amber, margin: 0, isTextBox: true });

  card(s, rx, 5.4, rw, 1.35, "123A2E");
  s.addText([
    { text: "Goal", options: { bold: true, color: C.mint, fontSize: 14, breakLine: true } },
    { text: "An agent that checks its own work, and does not repeat a mistake.", options: { color: C.text, fontSize: 18, bold: true } },
  ], { x: rx + 0.3, y: 5.5, w: rw - 0.6, h: 1.15, fontFace: BODY, valign: "middle", margin: 0, isTextBox: true });
  footer(s, 1);
  s.addNotes("Writing a report is easy for an LLM. Getting every number right is not. These four errors are real, from my own development runs, and each one became a test case. So the design goal was verification and memory, not prettier text.");
}

// ---------- Slide 2: Architecture --------------------------------------------------------------------------------
{
  const s = base("ARCHITECTURE  ·  LANGGRAPH, ONE SHARED STATE", "Plan → research → write → review → learn");
  const imgW = 11.7, imgH = imgW * 633.375 / 1494.797; // keep the rendered aspect ratio
  s.addImage({ path: path.join(REPO, "docs/architecture.png"), x: (W - imgW) / 2, y: 1.5, w: imgW, h: imgH,
    altText: "Workflow: user task, then plan and research (recall, planner, executor with tools, advance), then write and review (writer, verify, critic with rewrite and research loops), then learn (reflect, SQLite memory, recalled next run)" });
  const pats = ["Plan-and-Execute", "ReAct", "Tool use", "Reflection / critic", "Long-term memory"];
  const pw = 2.3, gap = 0.12, px0 = (W - (pats.length * pw + (pats.length - 1) * gap)) / 2;
  pats.forEach((p, i) => {
    const x = px0 + i * (pw + gap);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 6.62, w: pw, h: 0.38, fill: { color: C.card2 }, line: { color: C.line, width: 1 }, rectRadius: 0.19 });
    s.addText(p, { x, y: 6.62, w: pw, h: 0.38, fontFace: BODY, fontSize: 13, color: C.text, align: "center", valign: "middle", margin: 0, isTextBox: true });
  });
  s.addNotes("LangGraph with one shared state. The planner splits the task; each step is a ReAct loop with real tools: web search (Tavily, DuckDuckGo fallback), fetch page (renders JavaScript, returns focused passages) and a calculator. Then two layers of review: a deterministic check that looks up every number in its cited source, and a 120B critic that also checks the task's constraints. The critic can send the report back to the writer or send the agent back to research with fix-up steps, at most two revisions. Reflect writes lessons and source trust to SQLite; recall reads them before the next plan.");
}

// ---------- Slide 3: Self-improvement proof ----------------------------------------------------------------------
{
  const s = base("SELF-IMPROVEMENT PROOF  ·  CONTROLLED COMPARISON", "The fourth run got it right the first time");

  const stats = [["3 → 9", "first critique score (of 10)"], ["1 → 0", "revisions needed"], ["−52%", "tokens (28,411 → 13,604)"]];
  const sw = 3.85, sg = 0.3;
  stats.forEach(([big, small], i) => {
    const x = M + i * (sw + sg);
    card(s, x, 1.6, sw, 1.45);
    s.addText(big, { x: x + 0.3, y: 1.68, w: sw - 0.6, h: 0.85, fontFace: HEAD, fontSize: 44, bold: true, color: C.mint, margin: 0, isTextBox: true });
    s.addText(small, { x: x + 0.3, y: 2.52, w: sw - 0.6, h: 0.4, fontFace: BODY, fontSize: 14, color: C.muted, margin: 0, isTextBox: true });
  });

  const hdr = (t) => ({ text: t, options: { bold: true, color: C.text, fill: { color: C.card2 } } });
  const cell = (t, o = {}) => ({ text: t, options: { color: C.text, fill: { color: C.card }, ...o } });
  s.addTable([
    [hdr(""), hdr("Run #1 · no memory"), hdr("Run #4 · 4 lessons + trusted URL")],
    [cell("First critique", { color: C.muted }), cell("3/10 needs_research", { color: C.red }), cell("9/10 accept", { color: C.mint, bold: true })],
    [cell("Revisions", { color: C.muted }), cell("1"), cell("0", { color: C.mint, bold: true })],
    [cell("Tokens", { color: C.muted }), cell("28,411"), cell("13,604", { color: C.mint, bold: true })],
    [cell("Plan step 1", { color: C.muted }), cell("web search"), cell("fetch the official pricing page")],
  ], { x: M, y: 3.35, w: 7.4, colW: [1.7, 2.45, 3.25], rowH: 0.42, fontFace: BODY, fontSize: 14,
    border: { type: "solid", pt: 0.75, color: C.line }, valign: "middle", margin: [0.03, 0.08, 0.03, 0.12] });

  s.addText([
    { text: "Controlled: ", options: { bold: true, color: C.text } },
    { text: "qwen3.8-27b for every role, critic gpt-oss-120b, fresh memory DB, model fallbacks off.", options: { color: C.muted, breakLine: true } },
    { text: "Honest note: ", options: { bold: true, color: C.amber } },
    { text: "run #3 dropped to 4/10; fixing how trusted pages are read came from that failure.", options: { color: C.muted } },
  ], { x: M, y: 5.6, w: 7.4, h: 1.2, fontFace: BODY, fontSize: 13, margin: 0, valign: "top", paraSpaceAfter: 6, isTextBox: true });

  const cx = 8.35, cw = W - M - cx;
  card(s, cx, 3.35, cw, 3.45);
  s.addChart(pres.charts.BAR, [{ name: "First critique", labels: ["#1", "#2", "#3", "#4"], values: [3, 6, 4, 9] }], {
    x: cx + 0.15, y: 3.45, w: cw - 0.3, h: 3.25, barDir: "col",
    showTitle: true, title: "First critique score per run", titleColor: C.text, titleFontFace: BODY, titleFontSize: 14,
    chartColors: [C.mint], showValue: true, dataLabelPosition: "outEnd", dataLabelColor: C.text, dataLabelFontSize: 12,
    valAxisMinVal: 0, valAxisMaxVal: 10, valAxisMajorUnit: 5, valAxisLabelColor: C.muted, catAxisLabelColor: C.muted,
    valAxisLabelFontSize: 11, catAxisLabelFontSize: 12, valGridLine: { color: C.line, size: 0.5 }, catGridLine: { style: "none" },
    catAxisLineShow: false, valAxisLineShow: false, showLegend: false, barGapWidthPct: 60,
  });
  footer(s, 3);
  s.addNotes("Four runs in a row on the same task family (Pinecone storage cost), with nothing changed but the memory and two code fixes to how memory is used. The first run needed a revision because it trusted blogs. By the fourth run, the recalled lesson changed the plan itself: step one fetched the official page, the first draft passed at 9/10, and it cost about half the tokens. Example lesson: 'When a task requires a vendor's official pricing page, fetch that page first and extract the exact per-unit rate and minimum commitment from it, never relying on third-party snippets for the calculation.' Run #3 is shown on purpose: it failed, and fixing it is part of the story.");
}

// ---------- Slide 4: Demo highlights -----------------------------------------------------------------------------
{
  const s = base("DEMO HIGHLIGHTS  ·  asad-research-agent.streamlit.app", "What you see in the app");
  const items = [
    [C.blue, "1", "Live plan checklist", "Each step ticks off as it finishes; steps the critic asked for are marked fix-up."],
    [C.blue, "2", "Per-event trace", "memory · plan · think · act · observe · verify · critique · learn, as they happen."],
    [C.amber, "3", "Critic score and report", "Score, revisions, the cited report with a download button, tokens per model."],
    [C.mint, "4", "Memory tab", "Runs chart, lessons with seen / used / helpful counts, trusted sources with verified facts."],
    [C.mint, "5", "Replay mode", "Any recorded run, step by step, with no API calls: a demo that survives quota limits."],
    [C.blue, "6", "Same story in the CLI", "The terminal prints the same events: PLAN, THINK, ACT, OBSERVE, VERIFY, CRITIQUE, LEARN."],
  ];
  const gx = M, gw = 3.75, gh = 1.55, gg = 0.3;
  items.forEach(([col, n, t, d], i) => {
    const x = gx + (i % 2) * (gw + gg), y = 1.65 + Math.floor(i / 2) * (gh + gg);
    card(s, x, y, gw, gh);
    dot(s, x + 0.25, y + 0.25, col, n);
    s.addText(t, { x: x + 0.85, y: y + 0.25, w: gw - 1.05, h: 0.42, fontFace: BODY, fontSize: 16, bold: true, color: C.text, valign: "middle", margin: 0, isTextBox: true });
    s.addText(d, { x: x + 0.25, y: y + 0.78, w: gw - 0.5, h: 0.7, fontFace: BODY, fontSize: 13, color: C.muted, valign: "top", margin: 0, isTextBox: true });
  });

  // Critic test suite panel
  const px = gx + 2 * (gw + gg), pw = W - M - px;
  card(s, px, 1.65, pw, 5.25, C.card2);
  s.addText("6/6", { x: px + 0.35, y: 1.8, w: 2.2, h: 1.0, fontFace: HEAD, fontSize: 54, bold: true, color: C.amber, margin: 0, isTextBox: true });
  s.addText("known failure cases caught by the check + critic", { x: px + 0.35, y: 2.8, w: pw - 0.7, h: 0.4, fontFace: BODY, fontSize: 14, color: C.muted, margin: 0, isTextBox: true });
  const cases = [
    ["Unit error", "per 1M dimensions shown as per GB"],
    ["Contradiction", "Qdrant \"$25 minimum\" vs \"no minimum\""],
    ["Contradiction", "Pinecone $16/M vs $0.00000025/RU"],
    ["Misattribution", "$0.33 cited to a source without it"],
    ["Missed constraint", "official page never fetched → fix-up step"],
    ["No false alarm", "calculator result $3.30 not flagged"],
  ];
  s.addText(cases.map(([a, b], i) => ({ text: `${a}: ${b}`, options: { bullet: { indent: 14 }, breakLine: i < cases.length - 1 } })),
    { x: px + 0.35, y: 3.3, w: pw - 0.7, h: 2.85, fontFace: BODY, fontSize: 12, color: C.text, margin: 0, valign: "top", paraSpaceAfter: 4, isTextBox: true });
  s.addText("+ clean control report accepted (8/10)", { x: px + 0.35, y: 6.3, w: pw - 0.7, h: 0.4, fontFace: BODY, fontSize: 13, italic: true, color: C.mint, margin: 0, isTextBox: true });
  footer(s, 4);
  s.addNotes("The UI is built from the same event stream as the CLI, so what you see is exactly what the agent did. Replay mode exists because free quotas run out; it plays back real recorded runs, including the before and after runs from the previous slide. The critic is tested separately on fixed inputs that reproduce each real failure, so the result doesn't depend on a live run happening to make the mistake again.");
}

// ---------- Slide 5: Tech and limits -----------------------------------------------------------------------------
{
  const s = base("TECH AND LIMITS", "Built entirely on free tiers, and what that costs");
  const colW = (W - 2 * M - 0.3) / 2;

  // Left: stack + resilience
  card(s, M, 1.6, colW, 4.35);
  s.addText("Stack", { x: M + 0.3, y: 1.75, w: colW - 0.6, h: 0.4, fontFace: BODY, fontSize: 18, bold: true, color: C.text, margin: 0, isTextBox: true });
  const chips = ["Python 3.11", "LangGraph", "Groq gpt-oss-20b / 120b", "qwen3.8-27b", "NVIDIA NIM", "Gemini 2.5 Flash", "Tavily", "SQLite + FTS5", "Streamlit Cloud"];
  let cx = M + 0.3, cy = 2.25;
  chips.forEach((c) => {
    const w = 0.28 + c.length * 0.095;
    if (cx + w > M + colW - 0.3) { cx = M + 0.3; cy += 0.48; }
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx, y: cy, w, h: 0.36, fill: { color: C.card2 }, line: { color: C.line, width: 1 }, rectRadius: 0.18 });
    s.addText(c, { x: cx, y: cy, w, h: 0.36, fontFace: BODY, fontSize: 12, color: C.text, align: "center", valign: "middle", margin: 0, isTextBox: true });
    cx += w + 0.12;
  });
  s.addText("Resilience", { x: M + 0.3, y: 3.75, w: colW - 0.6, h: 0.4, fontFace: BODY, fontSize: 18, bold: true, color: C.text, margin: 0, isTextBox: true });
  const res = ["5-model fallback chain across separate free quotas", "Rate-limit retry using the provider's wait time",
    "Graceful stop with a partial report, never a crash", "Public demo capped at 15 live runs a day · 81 unit tests"];
  s.addText(res.map((t, i) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: i < res.length - 1 } })),
    { x: M + 0.3, y: 4.2, w: colW - 0.6, h: 1.6, fontFace: BODY, fontSize: 14, color: C.muted, margin: 0, valign: "top", paraSpaceAfter: 4, isTextBox: true });

  // Right: limits
  const rx = M + colW + 0.3;
  card(s, rx, 1.6, colW, 4.35);
  s.addText("Limits", { x: rx + 0.3, y: 1.75, w: colW - 0.6, h: 0.4, fontFace: BODY, fontSize: 18, bold: true, color: C.amber, margin: 0, isTextBox: true });
  const lim = [
    ["Quotas: ", "Groq ≈ 200k tokens/day per model; a broad comparison costs 70-100k"],
    ["Small models: ", "gpt-oss-20b rarely fetches pages without memory"],
    ["Evidence: ", "one task family, four runs; a demonstration, not a benchmark"],
    ["Recall: ", "keyword-based (FTS5), not semantic"],
    ["Demo: ", "memory is shared by all visitors and resets on restart"],
  ];
  s.addText(lim.map(([a, b], i) => [
    { text: a, options: { bold: true, color: C.text, bullet: true } },
    { text: b, options: { color: C.muted, breakLine: i < lim.length - 1 } },
  ]).flat(), { x: rx + 0.3, y: 2.25, w: colW - 0.6, h: 2.6, fontFace: BODY, fontSize: 14, margin: 0, valign: "top", paraSpaceAfter: 6, isTextBox: true });
  s.addText([
    { text: "Next: ", options: { bold: true, color: C.mint } },
    { text: "semantic recall, pruning lessons by helpfulness, scheduled re-checks of trusted sources", options: { color: C.muted } },
  ], { x: rx + 0.3, y: 4.95, w: colW - 0.6, h: 0.85, fontFace: BODY, fontSize: 14, margin: 0, valign: "top", isTextBox: true });

  // Bottom: links + disclosure
  s.addText([
    { text: "Live  ", options: { bold: true, color: C.mint } },
    { text: "asad-research-agent.streamlit.app", options: { color: C.text, hyperlink: { url: "https://asad-research-agent.streamlit.app/" } } },
    { text: "      Code  ", options: { bold: true, color: C.mint } },
    { text: "github.com/shaikasadahmed2k23/self-improving-research-agent_Submission", options: { color: C.text, hyperlink: { url: "https://github.com/shaikasadahmed2k23/self-improving-research-agent_Submission" } } },
  ], { x: M, y: 6.15, w: W - 2 * M, h: 0.4, fontFace: BODY, fontSize: 14, margin: 0, isTextBox: true });
  s.addText("Built with Claude Code as a coding assistant. All APIs used on free tiers (Groq, Gemini, Tavily, NVIDIA NIM).",
    { x: M, y: 6.55, w: W - 2 * M, h: 0.35, fontFace: BODY, fontSize: 12, italic: true, color: C.muted, margin: 0, isTextBox: true });
  footer(s, 5);
  s.addNotes("Everything runs on free tiers, which shaped the design: the fallback chain, the token saver, the replay mode. I want to be clear about the limits: the improvement is shown on one task family. The mechanism is general; the proof is small.");
}

// footers for slide 2 (added last so it sits above the image)
footer(pres.slides[1], 2);

pres.writeFile({ fileName: path.join(REPO, "docs/presentation.pptx") }).then((f) => console.log("wrote", f));
