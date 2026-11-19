from esg.parsing.chunker import MAX_WORDS, chunk, join_lines, split_long, table_slices
from esg.parsing.types import Element


def text(page, *lines):
    return Element("text", page, 0.0, lines=list(lines))


def table(page, *rows):
    return Element("table", page, 0.0, rows=[list(r) for r in rows])


def test_join_lines_mends_hyphenation():
    assert join_lines(["We cut envi-", "ronmental impact", "by 10%."]) == "We cut environmental impact by 10%."


def test_chunks_never_cross_a_principle():
    chunks = chunk([
        text(1, "SECTION C: PRINCIPLE WISE PERFORMANCE DISCLOSURE"),
        text(1, "PRINCIPLE 5 Businesses should respect human rights", "Some text on rights."),
        text(2, "PRINCIPLE 6 Businesses should protect the environment", "Emissions fell 12%."),
    ])
    p5 = [c for c in chunks if c.principle == 5]
    p6 = [c for c in chunks if c.principle == 6]
    assert p5 and p6
    assert all("Emissions" not in c.text for c in p5)
    assert p6[0].text.startswith("PRINCIPLE 6")  # heading kept as context
    assert p6[0].page_start == 2


def test_text_before_brsr_has_no_section():
    chunks = chunk([text(1, "Chairman's message."), text(2, "SECTION A: GENERAL DISCLOSURES", "CIN: L123")])
    assert chunks[0].section is None
    assert chunks[1].section == "A"


def test_long_paragraphs_are_split():
    sentence = "Our renewable share rose to forty percent this year. "
    chunks = chunk([text(1, sentence * 100)])
    assert len(chunks) > 1
    assert all(c.word_count <= MAX_WORDS for c in chunks)


def test_split_long_hard_wraps_a_runaway_sentence():
    pieces = split_long("word " * 450, limit=200)
    assert [len(p.split()) for p in pieces] == [200, 200, 50]


def test_table_becomes_its_own_chunk_and_keeps_section():
    chunks = chunk([
        text(1, "SECTION A: GENERAL DISCLOSURES", "Intro."),
        table(1, ("Parameter", "FY24", "FY23"), ("Scope 1 (tCO2e)", "1,200", "1,350")),
        text(2, "More prose."),
    ])
    kinds = [c.kind for c in chunks]
    assert kinds == ["text", "table", "text"]
    assert chunks[1].section == "A"
    assert chunks[1].text.splitlines()[1] == "| Scope 1 (tCO2e) | 1,200 | 1,350 |"


def test_long_tables_split_with_header_repeated():
    header = ["Metric", "Value"]
    rows = [header] + [[f"row {i} " + "word " * 20, str(i)] for i in range(40)]
    slices = table_slices(rows, limit=100)
    assert len(slices) > 1
    assert all(s[0] == header for s in slices)
    assert sum(len(s) - 1 for s in slices) == 40


def test_principle_banner_drawn_as_table_row():
    chunks = chunk([
        text(1, "SECTION C: PRINCIPLE WISE PERFORMANCE DISCLOSURE"),
        table(1, ("PRINCIPLE 6: Businesses should protect the environment", ""),
              ("Parameter", "FY24"), ("Energy (GJ)", "500")),
    ])
    tables = [c for c in chunks if c.kind == "table"]
    assert tables[0].principle == 6
    assert tables[0].text.startswith("| Parameter")
