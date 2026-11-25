from esg.eval import gold


def item(key, seqs):
    return {"key": key, "company": "NTPC", "fiscal_year": 2024, "chunk_seq": 5, "char_start": 0,
            "char_end": 10, "sentence": "We planted 39 million trees.",
            "passages": [{"pid": f"E{i}", "chunk_seq": s} for i, s in enumerate(seqs, 1)]}


def test_latest_label_wins_and_pids_map_to_chunk_seqs(tmp_path):
    items, labels = tmp_path / "items.jsonl", tmp_path / "labels.jsonl"
    gold.write_jsonl(items, [item("a", [7, 9, 12]), item("b", [3]), item("c", [4])])
    gold.append_label({"key": "a", "is_claim": True, "verdict": "vague", "supporting": []}, labels)
    gold.append_label({"key": "a", "is_claim": True, "verdict": "substantiated",
                       "supporting": ["E1", "E3"]}, labels)
    gold.append_label({"key": "b", "is_claim": False, "verdict": None, "supporting": []}, labels)

    got = {g.key: g for g in gold.load_gold(items, labels)}
    assert set(got) == {"a", "b"}  # "c" is not labelled yet
    assert got["a"].verdict == "substantiated"
    assert got["a"].supporting_seqs == {7, 12}
    assert got["a"].judged_seqs == {7, 9, 12}
    assert got["b"].is_claim is False and got["b"].verdict is None


def test_split_is_stable_and_roughly_forty_sixty():
    keys = [gold.item_key("Wipro", 2024, i, i * 3) for i in range(1000)]
    splits = [gold.split_of(k) for k in keys]
    assert splits == [gold.split_of(k) for k in keys]
    assert 0.35 < splits.count("dev") / len(splits) < 0.45


def test_second_pass_covers_test_split_claims_and_overrides_first_pass(tmp_path, monkeypatch):
    items, first, second = tmp_path / "items.jsonl", tmp_path / "l1.jsonl", tmp_path / "l2.jsonl"
    keys = [f"k{i}" for i in range(40)]
    gold.write_jsonl(items, [item(k, [1, 2]) for k in keys])
    for k in keys:
        gold.append_label({"key": k, "is_claim": k != "k0", "verdict": "substantiated" if k != "k0" else None,
                           "supporting": ["E1"] if k != "k0" else []}, first)
    chosen = gold.second_pass_keys(items, first)
    assert chosen and all(gold.split_of(k) == "test" for k in chosen) and "k0" not in chosen

    gold.append_label({"key": chosen[0], "is_claim": True, "verdict": "unsupported", "supporting": []}, second)
    merged = {g.key: g for g in gold.load_gold(items, first, second)}
    assert merged[chosen[0]].verdict == "unsupported" and not merged[chosen[0]].supporting_seqs
    assert merged[chosen[1]].verdict == "substantiated"   # not re-labelled: first pass stands
