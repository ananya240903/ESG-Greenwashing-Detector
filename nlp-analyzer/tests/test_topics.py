from esg.claims.topics import brsr_core, tag


def test_tags_brsr_core_topics():
    assert tag("We reduced Scope 1 and 2 emissions by 12% and aim for net zero by 2040.") == ["ghg"]
    assert tag("All plants now operate on zero liquid discharge, saving 2.1 kL per tonne.") == ["water"]
    assert tag("40% of our electricity now comes from solar and wind.") == ["energy"]
    assert tag("We recycled 95% of hazardous waste and cut plastic packaging.") == ["waste"]


def test_one_claim_can_cover_several_topics():
    keys = tag("Energy efficiency projects cut CO2 emissions and water use at our plants.")
    assert keys == ["ghg", "water", "energy"]
    assert brsr_core(keys) == ["GHG footprint", "Water footprint", "Energy footprint"]


def test_topics_outside_brsr_core_and_no_topic():
    assert tag("We have planted 39 million trees so far.") == ["biodiversity"]
    assert tag("94% sustainable sourcing of paper and board from suppliers.") == ["sourcing"]
    assert brsr_core(["biodiversity", "sourcing"]) == []
    assert tag("Our board met eleven times during the year.") == []


def test_waste_is_not_confused_with_wastewater():
    assert tag("Treated wastewater is reused for gardening.") == ["water", "waste"]  # "reused" is circularity
    assert "waste" not in tag("Wastewater is treated before discharge.")
