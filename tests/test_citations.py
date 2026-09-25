from agent.nodes.writer import cited_ids, finalize_citations, normalize_citations

SOURCES = [{"id": i, "title": f"Source {i}", "url": f"https://example.com/{i}"} for i in range(1, 21)]


def test_normalize_fullwidth_brackets():
    assert normalize_citations("a【18】 b【13, 14】") == "a[18] b[13, 14]"


def test_normalize_gpt_oss_dagger_citations():
    assert normalize_citations("$0.33/GB【21†L12-L20】 and $50【9†source】 [30†L3]") == "$0.33/GB[21] and $50[9] [30]"


def test_cited_ids_in_order_of_first_appearance():
    assert cited_ids("x [13] y [6, 13] z [8][6]") == [13, 6, 8]


def test_renumbers_sequentially_by_first_appearance():
    out = finalize_citations("Pinecone [13]. Qdrant [6][13]. Weaviate [8, 6].", SOURCES)
    body, sources = out.split("\n## Sources\n")
    assert body.strip() == "Pinecone [1]. Qdrant [2][1]. Weaviate [2, 3]."
    assert sources.strip().splitlines() == [
        "1. [Source 13](https://example.com/13)",
        "2. [Source 6](https://example.com/6)",
        "3. [Source 8](https://example.com/8)",
    ]


def test_drops_unknown_ids_and_llm_written_sources_section():
    out = finalize_citations("Fact [2][99].\n\n## References\n1. made-up link", SOURCES)
    assert "made-up" not in out
    assert "[99]" not in out
    assert out.startswith("Fact [1].")


def test_markdown_links_untouched():
    out = finalize_citations("See [docs](https://x.io) and [3].", SOURCES)
    assert "[docs](https://x.io)" in out and "[1]" in out
