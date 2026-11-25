from esg.claims.sentences import split_sentences


def texts(text):
    return [s.text for s in split_sentences(text)]


def test_splits_sentences_and_keeps_offsets():
    text = ("We reduced Scope 1 emissions by 12% in FY 2023-24. Our plants now run on 40% "
            "renewable power across all sites.")
    got = split_sentences(text)
    assert [s.text for s in got] == [
        "We reduced Scope 1 emissions by 12% in FY 2023-24.",
        "Our plants now run on 40% renewable power across all sites.",
    ]
    for s in got:
        assert text[s.start:s.end] == s.text


def test_offsets_hold_across_lines_and_bullets():
    text = "Leadership Indicators\n• We aim to be water positive by 2030 at all our factories.\nOver 3,80,000"
    (s,) = split_sentences(text)
    assert s.text == "We aim to be water positive by 2030 at all our factories."
    assert text[s.start:s.end] == s.text


def test_does_not_split_on_abbreviations_or_initials():
    text = "The plant, run by Tata Steel Ltd. in Jamshedpur, uses less water, i.e. 2.1 kL per tonne of steel."
    assert texts(text) == [text]
    assert texts("Mr. A. K. Sharma, Director, oversees our climate strategy for the group.") == [
        "Mr. A. K. Sharma, Director, oversees our climate strategy for the group."
    ]


def test_drops_brsr_questions_headings_and_fragments():
    text = "\n".join([
        "EI-6. Please provide details of air emissions (other than GHG emissions) by the entity",
        "LI- 2. Details of the business, in the following format for the entity:",
        "SECTION C: PRINCIPLE WISE PERFORMANCE DISCLOSURE AND OTHER MATTERS",
        "Patients treated through Sanjeevani Camps",
        "Total 1,234 5,678 9,012 3,456 7,890 1,234",
        "Does the entity have a policy on waste management in place for all units?",
        "We have committed to net zero emissions across our operations by 2040.",
    ])
    assert texts(text) == ["We have committed to net zero emissions across our operations by 2040."]


def test_drops_the_brsr_principle_statements():
    text = ("Businesses should respect and make efforts to protect and restore the environment.\n"
            "PRINCIPLE 2 Businesses should provide goods and services in a manner that is sustainable and safe.\n"
            "Our businesses should be water positive by 2030, so we are investing in recharge projects.")
    assert texts(text) == ["Our businesses should be water positive by 2030, so we are investing in recharge projects."]
