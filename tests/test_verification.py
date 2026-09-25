from agent.verification import check_citations, extract_claims, summarize_checks

PINECONE_OFFICIAL = {
    "id": 1, "title": "Pricing | Pinecone", "url": "https://www.pinecone.io/pricing/",
    "content": "Standard POPULAR For production applications at any scale. $50/month min. usage | Storage | Up to 2 GB",
}
WITHORB = {
    "id": 2, "title": "Pinecone pricing guide", "url": "https://www.withorb.com/blog/pinecone-pricing",
    "content": "Storage is billed at $0.33/GB per month on the Standard plan, with a $50 monthly minimum.",
}
WEAVIATE = {
    "id": 3, "title": "Weaviate Cloud pricing", "url": "https://weaviate.io/pricing",
    "content": "Serverless: $0.095 per 1M vector dimensions stored per month. Minimum $25/mo.",
}
SOURCES = [PINECONE_OFFICIAL, WITHORB, WEAVIATE]


def _by_number(checks):
    return {c["number"]: c for c in checks}


def test_misattributed_number_is_flagged_with_where_it_really_is():
    draft = "Pinecone storage costs $0.33/GB per month [1]. The minimum is $50/month [1]."
    checks = _by_number(check_citations(draft, SOURCES))
    assert checks["$0.33"]["status"] == "not_in_source"
    assert checks["$0.33"]["found_in"] == [2]
    assert checks["$50"]["status"] == "verified"


def test_unit_error_is_flagged():
    draft = "| Weaviate | $0.095 / GB-month | $25 | [3] |"
    checks = _by_number(check_citations(draft, SOURCES))
    assert checks["$0.095"]["status"] == "unit_mismatch"
    assert "GB" in checks["$0.095"]["detail"] and "dimensions" in checks["$0.095"]["detail"]
    assert checks["$25"]["status"] == "verified"


def test_correct_unit_passes():
    draft = "Weaviate charges $0.095 per 1M vector dimensions [3]."
    assert check_citations(draft, SOURCES)[0]["status"] == "verified"


def test_calculator_results_count_as_verified_and_task_numbers_are_skipped():
    draft = "10 GB costs $3.30 per month (10 x $0.33) [2]."
    checks = _by_number(
        check_citations(draft, SOURCES, calculations=[{"expression": "10 * 0.33", "result": 3.3}], task="cost of 10 GB")
    )
    assert checks["$3.30"]["status"] == "calculated"
    assert checks["$0.33"]["status"] == "verified"
    assert "10" not in checks


def test_uncalculated_derived_number_is_flagged():
    checks = _by_number(check_citations("10 GB costs $3.30 per month [2].", SOURCES, task="10 GB"))
    assert checks["$3.30"]["status"] == "not_in_source"


def test_adjacent_citations_merge_and_small_numbers_are_ignored():
    claims = extract_claims("Top 3 providers charge $50 [1][2]. Next: $0.33 [2], [3]\n## Sources\n1. x $99 [1]")
    assert [c["ids"] for c in claims] == [[1, 2], [2, 3]]
    checks = check_citations("Top 3 providers charge $50 [1][2].", SOURCES)
    assert [c["number"] for c in checks] == ["$50"]


def test_draft_without_citations_fails_and_uncited_numbers_are_warned():
    checks = check_citations("# Pricing 2026\nPinecone costs $0.33/GB and $50/month.\n| Qdrant | $25 |", SOURCES)
    statuses = [c["status"] for c in checks]
    assert statuses.count("uncited") == 3 and "no_citations" in statuses
    summary = summarize_checks(checks)
    assert "FAIL no_citations" in summary and "WARN 3 numbers without any citation" in summary


def test_uncited_summary_line_does_not_fail_a_cited_draft():
    checks = check_citations("Pinecone minimum is $50/month [1].\nOverall about $12.5 per month.", SOURCES)
    assert [c["status"] for c in checks] == ["verified", "uncited"]


def test_unknown_citation_and_summary():
    checks = check_citations("Costs $12.5 [42].", SOURCES)
    assert checks[0]["status"] == "unknown_citation"
    assert "FAIL unknown_citation" in summarize_checks(checks)
