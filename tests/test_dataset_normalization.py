import pytest

from lattice.data.normalize import normalize_row, wiki_documents


def spec(name):
    return {
        "id": name,
        "family": name,
        "license": "MIT",
        "repository": "unit-test",
        "revision": "pinned",
        "configuration": "test",
    }


def test_numeric_arc_keys_are_remapped_not_guessed():
    row = {
        "id": "q",
        "question": "Which?",
        "choices": {"label": ["1", "2", "3"], "text": ["one", "two", "three"]},
        "answerKey": "2",
    }
    item = normalize_row(spec("arc_easy"), "test", 0, row)
    assert item.reference.value == "B"
    assert "B. two" in item.prompt
    row["answerKey"] = ""
    with pytest.raises(ValueError):
        normalize_row(spec("arc_easy"), "test", 0, row)


def test_boolean_types_and_passage_grouping():
    row = {"question": "q", "passage": "same passage", "answer": True}
    first = normalize_row(spec("boolq"), "train", 0, row)
    second = normalize_row(spec("boolq"), "validation", 1, {**row, "question": "other"})
    assert first.group_id == second.group_id
    with pytest.raises(ValueError):
        normalize_row(spec("boolq"), "train", 0, {**row, "answer": 1})


def test_squad_rejects_wrong_offsets_and_keeps_unanswerable():
    row = {
        "id": "q",
        "title": "article",
        "context": "A red fox.",
        "question": "What?",
        "answers": {"text": ["red"], "answer_start": [2]},
    }
    assert normalize_row(
        spec("squad_v2"), "validation", 0, row
    ).reference.alternatives == ["red"]
    row["answers"]["answer_start"] = [3]
    with pytest.raises(ValueError):
        normalize_row(spec("squad_v2"), "validation", 0, row)
    row["answers"] = {"text": [], "answer_start": []}
    assert not normalize_row(spec("squad_v2"), "validation", 0, row).metadata[
        "answerable"
    ]


def test_missing_gsm_final_answer_is_not_inferred():
    with pytest.raises(ValueError):
        normalize_row(spec("gsm8k"), "test", 0, {"question": "2+2?", "answer": "four"})


def test_wiki_groups_articles_not_lines():
    rows = [
        " = Alpha = \n",
        "first\n",
        "\n",
        " == Section ==\n",
        "more\n",
        " = Beta =\n",
        "last\n",
    ]
    docs = list(wiki_documents(spec("wikitext2"), "test", rows))
    assert len(docs) == 2
    assert "".join(r.prompt for r in docs) == "".join(rows)
    assert docs[0].metadata["unit"] == "article"
    assert docs[0].scorer == "language_model_loss_deferred"
