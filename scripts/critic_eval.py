"""Evaluate the verify + critic nodes on the known failure cases (see CLAUDE.md) plus a clean control.

Each case is a fixed draft/sources/tool-log snapshot reproducing an error seen in real runs, so the
result doesn't depend on whether a live run happens to make that mistake again. Calls the real critic LLM.

Usage:  python scripts/critic_eval.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent import config  # noqa: E402
from agent.nodes.critic import critic  # noqa: E402
from agent.nodes.planner import replan  # noqa: E402
from agent.nodes.verify import verify  # noqa: E402
from agent.nodes.writer import finalize_citations  # noqa: E402

COMPARE_TASK = "Compare the pricing of the top 3 managed vector databases"
OFFICIAL_TASK = (
    "Using Pinecone's official pricing page, what would 10 GB of storage cost per month on the Standard plan, "
    "and how does that compare to the plan's monthly minimum?"
)


def src(i, url, title, content, provider="tavily"):
    return {"id": i, "url": url, "title": title, "content": content, "provider": provider}


PINECONE_BLOG = src(1, "https://pecollective.com/tools/pinecone-pricing", "Pinecone Pricing in 2026",
                    "Standard plan: $50/month minimum. Storage $0.33/GB/month. Read units $16 per million, write units $4 per million.")
PINECONE_RU = src(2, "https://ranksquire.com/2026/04/02/pinecone-pricing-2026", "Pinecone Pricing 2026",
                  "Serverless reads are billed at $0.00000025 per read unit and writes at $0.0000004 per write unit.")
WEAVIATE = src(3, "https://weaviate.io/pricing", "Weaviate Cloud pricing",
               "Serverless Cloud: $0.095 per 1M vector dimensions stored per month. Minimum $25/mo. Free sandbox for 14 days.")
QDRANT_A = src(4, "https://ranksquire.com/2026/04/19/qdrant-cloud-pricing-2026", "Qdrant Cloud Pricing 2026",
               "Qdrant Cloud paid clusters start with a $25 minimum monthly fee. Free tier: 1 GB cluster forever.")
QDRANT_B = src(5, "https://checkthat.ai/brands/qdrant/pricing", "Qdrant Pricing 2026",
               "Qdrant Cloud has no minimum plan; you pay only for the resources you use. Free tier: 1 GB cluster.")
QDRANT_FULL = src(4, "https://qdrant.tech/pricing", "Qdrant Cloud pricing",
                  "Managed cloud: $25 minimum monthly fee for paid clusters. Smallest paid cluster (0.5 vCPU, 1 GB RAM) "
                  "costs $0.014 per cluster-hour. Free tier: 1 GB cluster forever.", provider="fetch")
PINECONE_OFFICIAL_SNIPPET = src(6, "https://www.pinecone.io/pricing/", "Pricing | Pinecone",
                                "Standard: For production applications at any scale. $50/month minimum usage.")
WITHORB = src(7, "https://www.withorb.com/blog/pinecone-pricing", "Pinecone pricing explained",
              "On the Standard plan, storage is billed at $0.33/GB per month, with a $50 monthly minimum.")

SEARCH_ONLY_LOG = [{"step": 1, "tool": "web_search", "args": {"query": "Pinecone pricing"}, "error": False}]
GOOD_COMPARE_LOG = SEARCH_ONLY_LOG + [
    {"step": 2, "tool": "fetch_page", "args": {"url": "https://weaviate.io/pricing"}, "error": False},
]

CASES = [
    {
        "name": "1. Unit error (Weaviate per-1M-dims shown as per GB)",
        "task": COMPARE_TASK, "sources": [PINECONE_BLOG, WEAVIATE, QDRANT_A], "tool_log": GOOD_COMPARE_LOG,
        "draft": (
            "# Vector DB pricing\n\n| Provider | Minimum | Storage | Source |\n|---|---|---|---|\n"
            "| Pinecone | $50/month | $0.33 / GB-month | [1] |\n"
            "| Weaviate | $25/month | $0.095 / GB-month | [3] |\n"
            "| Qdrant | $25/month | n/a | [4] |\n"
        ),
        "expect": lambda r: r["check"]("$0.095", "unit_mismatch") and r["verdict"] != "accept",
    },
    {
        "name": "2a. Contradiction (Qdrant $25 minimum vs no minimum)",
        "task": COMPARE_TASK, "sources": [PINECONE_BLOG, WEAVIATE, QDRANT_A, QDRANT_B], "tool_log": GOOD_COMPARE_LOG,
        "draft": (
            "# Vector DB pricing\n\n## Pinecone\nStandard has a $50/month minimum and storage at $0.33/GB/month [1].\n\n"
            "## Weaviate\nServerless costs $0.095 per 1M vector dimensions per month with a $25/mo minimum [3].\n\n"
            "## Qdrant\nPaid clusters have a $25 minimum monthly fee [4]. Qdrant Cloud has no minimum plan; "
            "you pay only for the resources you use [5].\n"
        ),
        "expect": lambda r: r["verdict"] != "accept" and r["mentions"]("qdrant") and r["mentions"]("minimum"),
    },
    {
        "name": "2b. Contradiction (Pinecone reads $16/M vs $0.00000025/RU)",
        "task": COMPARE_TASK, "sources": [PINECONE_BLOG, PINECONE_RU, WEAVIATE, QDRANT_A], "tool_log": GOOD_COMPARE_LOG,
        "draft": (
            "# Vector DB pricing\n\n## Pinecone\n- Standard: $50/month minimum, storage $0.33/GB/month [1].\n"
            "- Read units cost $16 per million [1].\n- Reads are billed at $0.00000025 per read unit [2].\n\n"
            "## Weaviate\n$0.095 per 1M vector dimensions per month, $25/mo minimum [3].\n\n"
            "## Qdrant\n$25 minimum monthly fee [4].\n"
        ),
        "expect": lambda r: r["verdict"] != "accept" and r["mentions"]("read"),
    },
    {
        "name": "3. Misattributed citation ($0.33 cited to pinecone.io)",
        "task": COMPARE_TASK, "sources": [PINECONE_OFFICIAL_SNIPPET, WITHORB, WEAVIATE, QDRANT_A],
        "tool_log": GOOD_COMPARE_LOG,
        "renumber": {6: 1, 7: 2},
        "draft": (
            "# Vector DB pricing\n\n## Pinecone\nStandard storage costs $0.33/GB per month with a $50/month minimum [6].\n\n"
            "## Weaviate\n$0.095 per 1M vector dimensions per month, $25/mo minimum [3].\n\n"
            "## Qdrant\n$25 minimum monthly fee [4].\n"
        ),
        "expect": lambda r: r["check"]("$0.33", "not_in_source") and r["verdict"] != "accept",
    },
    {
        "name": "4. Task constraint: 'official pricing page' never fetched (+ calculator $3.30)",
        "task": OFFICIAL_TASK, "sources": [PINECONE_OFFICIAL_SNIPPET, WITHORB], "tool_log": SEARCH_ONLY_LOG + [
            {"step": 1, "tool": "calculator", "args": {"expression": "10 * 0.33"}, "error": False}],
        "calculations": [{"expression": "10 * 0.33", "result": 3.3}],
        "draft": (
            "# Pinecone Standard: 10 GB storage cost\n\n10 GB of storage costs $3.30 per month "
            "(10 GB x $0.33/GB) [7]. The Standard plan has a $50/month minimum [6], so you would pay the $50 minimum.\n"
        ),
        "expect": lambda r: r["verdict"] == "needs_research" and r["critique"]["constraint_violations"]
        and r["check"]("$3.30", "calculated") and r["fixup_fetches_official"],
    },
    {
        "name": "Control: clean, consistent report (should be accepted)",
        "task": COMPARE_TASK, "sources": [PINECONE_BLOG, WEAVIATE, QDRANT_FULL], "tool_log": GOOD_COMPARE_LOG,
        "draft": (
            "# Pricing of Pinecone, Weaviate and Qdrant\n\n## Summary\nAll three offer managed plans with monthly minimums "
            "from $25 to $50 [1][3][4]. They bill in different units (GB, vector dimensions, cluster hours), so the "
            "cheapest option depends on workload size.\n\n| Provider | Minimum | Usage price | Free tier | Source |\n"
            "|---|---|---|---|---|\n| Pinecone Standard | $50/month | $0.33 per GB-month storage; reads $16 per million, writes $4 per million | - | [1] |\n"
            "| Weaviate Serverless | $25/month | $0.095 per 1M vector dimensions stored per month | 14-day sandbox | [3] |\n"
            "| Qdrant Cloud | $25/month | $0.014 per cluster-hour for the smallest paid cluster (0.5 vCPU, 1 GB RAM) | 1 GB cluster forever | [4] |\n\n"
            "## How to compare\nUnits are not directly comparable: Pinecone charges per GB and per operation, Weaviate per "
            "stored vector dimension, and Qdrant per provisioned cluster-hour. For small workloads the $25-$50 minimums "
            "dominate the bill [1][3][4].\n\n"
            "## Limitations\nPrices are list prices from the cited pages; enterprise discounts and egress fees are not covered.\n"
        ),
        "expect": lambda r: r["verdict"] == "accept",
    },
]


def run_case(case: dict) -> dict:
    state = {
        "task": case["task"], "sources": case["sources"], "tool_log": case["tool_log"],
        "calculations": case.get("calculations", []), "draft_raw": case["draft"],
        "draft": finalize_citations(case["draft"], case["sources"]), "revision": 0,
        "plan": [{"id": 1, "goal": case["task"], "search_query": "", "status": "done", "result": case["draft"], "origin": "initial"}],
    }
    state.update(verify(state))
    out = critic(state)
    c = out["critique"]
    text = " ".join(c["issues"] + c["constraint_violations"] + c["missing_info"]).lower()
    checks = state["checks"]
    result = {
        "critique": c, "verdict": c["verdict"], "checks": checks,
        "check": lambda num, status: any(x["number"] == num and x["status"] == status for x in checks),
        "mentions": lambda word: word in text,
        "fixup_fetches_official": False, "fixups": [],
    }
    if c["verdict"] == "needs_research":
        state.update(out)
        new_steps = replan(state)["plan"][len(state["plan"]):]
        result["fixups"] = [s["goal"] for s in new_steps]
        joined = " ".join(result["fixups"]).lower()
        result["fixup_fetches_official"] = "pinecone.io" in joined and ("fetch" in joined or "official" in joined)
    return result


def main() -> int:
    print(f"Critic model: {config.groq_model_for('critic')}\n")
    caught = 0
    for case in CASES:
        r = run_case(case)
        ok = bool(case["expect"](r))
        caught += ok
        c = r["critique"]
        failed = [x for x in r["checks"] if x["status"] not in ("verified",)]
        print(f"{'PASS' if ok else 'MISS'}  {case['name']}")
        print(f"      critic: score {c['score']}/10, verdict {c['verdict']}")
        for x in failed:
            print(f"      check:  {x['number']} cited {x['cited']} -> {x['status']} ({x['detail'][:110]})")
        for label, key in (("violation", "constraint_violations"), ("issue", "issues"), ("missing", "missing_info")):
            for item in c[key][:4]:
                print(f"      {label}: {item[:150]}")
        for goal in r["fixups"]:
            print(f"      fix-up step: {goal[:150]}")
        print()
    print(f"{caught}/{len(CASES)} cases behaved as expected")
    return 0 if caught == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
