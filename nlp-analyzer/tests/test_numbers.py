from esg.verdict.numbers import check, figures


def keys(text):
    return [f.key for f in figures(text)]


def test_extracts_percentages_scales_and_indian_grouping():
    assert keys("94% of paper and 81 per cent of tomatoes") == ["94%", "81%"]
    assert keys("planted 39 million trees and 3,80,000 saplings") == ["39m", "380000"]
    assert keys("avoided ~2,928.07 tCO2e") == ["2928.07"]
    assert keys("Rs. 1,200 crore invested") == ["1200cr"]


def test_ignores_years_fiscal_years_and_small_counts():
    assert keys("Net zero by 2040, in FY 2023-24, across Scope 1 and 2 with a 4-step plan") == []
    assert keys("47 sites and 12.5 MW of solar") == ["47", "12.5"]


def test_finds_figures_in_other_passages():
    claim = "We have achieved sustainable sourcing for 94% of paper and 81% of tomatoes."
    got = check(claim, [(10, "a", "Tea: 79%."), (11, "b", "| Paper and board | 94 % |"), (12, "c", "Tomatoes 81 per cent")])
    assert got.figures == ("94%", "81%") and got.found_in == (11, 12) and got.found_labels == ("b", "c") and got.all_found


def test_reports_figures_that_appear_nowhere_else():
    got = check("This avoided ~2,928.07 tCO2e of emissions.", [(1, "a", "Emissions fell 12%.")])
    assert got.has_figures and got.none_found and not got.all_found
    assert not check("We care about the planet.", [(1, "a", "94%")]).has_figures
