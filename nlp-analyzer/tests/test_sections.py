from esg.parsing.sections import SectionState, advance


def run(lines):
    state = SectionState()
    for line in lines:
        state = advance(state, line)
    return state


def test_sections_and_principles_in_order():
    s = run([
        "SECTION A: GENERAL DISCLOSURES",
        "SECTION B: MANAGEMENT AND PROCESS DISCLOSURES",
        "SECTION C: PRINCIPLE WISE PERFORMANCE DISCLOSURE",
        "PRINCIPLE 6 Businesses should respect and make efforts to protect and restore the environment",
        "Essential Indicators",
    ])
    assert s == SectionState("C", 6, "Essential Indicators")


def test_heading_variants():
    assert advance(SectionState(), "Section - A : General Disclosures").section == "A"
    assert advance(SectionState(), "SECTION C – PRINCIPLE-WISE PERFORMANCE").section == "C"
    assert advance(SectionState("C"), "Principle 1: Businesses should conduct...").principle == 1


def test_never_moves_backwards():
    s = SectionState("C", 6)
    assert advance(s, "SECTION A: GENERAL DISCLOSURES") == s
    assert advance(s, "PRINCIPLE 2 Businesses should provide goods") == s


def test_principles_ignored_outside_section_c():
    assert advance(SectionState("B"), "Principle 6 policy covers the environment").principle is None


def test_new_principle_resets_indicator_heading():
    s = advance(SectionState("C", 1, "Leadership Indicators"), "PRINCIPLE 2 Businesses should")
    assert s == SectionState("C", 2, None)


def test_bare_principle_heading_is_not_mistaken_for_toc():
    # HUL prints "PRINCIPLE 1" alone on its line; the "1" is not a page number.
    assert advance(SectionState("C"), "PRINCIPLE 1").principle == 1
    assert advance(SectionState("C"), "Principle 6 Businesses should protect the environment 45") == SectionState("C")


def test_ignores_toc_lines_and_prose():
    s = SectionState()
    assert advance(s, "Section A: General Disclosures ........ 4") == s
    assert advance(s, "Section C: Principle wise performance 12") == s
    assert advance(s, "As described in Section A of this report, the company...") == s
