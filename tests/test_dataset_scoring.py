from fractions import Fraction

import pytest

from lattice.data.schema import DataRecord, Reference
from lattice.data.scoring import number, parse_json, score_record, span_metrics


def record(scorer, kind, value=None, **kwargs):
    reference = kwargs.pop("reference", Reference(kind=kind, value=value))
    return DataRecord(
        id="test",
        dataset="test",
        family="test",
        source_split="test",
        partition="evaluation",
        group_id="group",
        prompt="question",
        reference=reference,
        scorer=scorer,
        license="Apache-2.0",
        source={},
        **kwargs,
    )


@pytest.mark.parametrize(
    "literal,expected",
    [("1,234", 1234), ("-2.5", Fraction(-5, 2)), ("2/4", Fraction(1, 2)), ("1e2", 100)],
)
def test_exact_bounded_numbers(literal, expected):
    assert number(literal) == expected


@pytest.mark.parametrize(
    "literal",
    ["NaN", "Infinity", "1e99999", "1,2", "1/0", '__import__("os")', "9" * 129],
)
def test_invalid_numbers(literal):
    with pytest.raises((ValueError, ZeroDivisionError)):
        number(literal)


def test_number_correctness_separate_from_compliance():
    item = record("number_v1", "number", "4")
    assert score_record(item, "4").strict_correct
    score = score_record(item, "I computed 2 + 2. #### 4")
    assert score.answer_correct and not score.strict_correct
    assert not score_record(item, "5").answer_correct
    assert score_record(item, "4.0").answer_correct
    assert not score_record(item, "4.0").strict_correct


def test_choice_anchors_and_ambiguity():
    item = record(
        "choice_v1", "choice", "B", metadata={"choice_labels": ["A", "B", "C"]}
    )
    assert score_record(item, "B").strict_correct
    assert score_record(item, "Answer: B").answer_correct
    assert not score_record(item, "A guess would be B in prose").answer_correct
    assert not score_record(item, "Answer: B\nAnswer: C").answer_correct


def test_boolean_does_not_search_arbitrary_text():
    item = record("boolean_v1", "boolean", True)
    assert score_record(item, "Yes, that is correct.").answer_correct
    assert not score_record(item, "Yes, that is correct.").strict_correct
    assert not score_record(item, "Yesterday").answer_correct
    assert not score_record(item, "I think yes").answer_correct
    with pytest.raises(ValueError):
        record("boolean_v1", "boolean", 1)


@pytest.mark.parametrize("text", ['{"a":1,"a":1}', '{"a":NaN}', '{"a":Infinity}'])
def test_json_rejects_invalid_types_and_duplicate_keys(text):
    with pytest.raises(ValueError):
        parse_json(text)


def test_json_types_fences_and_array_order():
    item = record("json_v1", "json", {"enabled": True, "values": [1, 2]})
    assert score_record(item, '{"values":[1,2],"enabled":true}').strict_correct
    assert not score_record(item, '{"values":[1,2],"enabled":1}').answer_correct
    assert not score_record(item, '{"values":[2,1],"enabled":true}').answer_correct
    score = score_record(item, '```json\n{"values":[1,2],"enabled":true}\n```')
    assert score.answer_correct and not score.strict_correct


def test_span_alternatives_and_abstention():
    item = record(
        "span_v1",
        "span",
        reference=Reference(kind="span", alternatives=["The red fox", "red fox"]),
    )
    assert score_record(item, "red fox").answer_correct
    assert span_metrics("red", ["red fox"])["token_f1"] == pytest.approx(2 / 3)
    empty = record("span_v1", "span", reference=Reference(kind="span"))
    assert score_record(empty, "UNANSWERABLE").strict_correct
    assert not score_record(empty, "I do not know").answer_correct


@pytest.mark.parametrize(
    "scorer,kind,metadata",
    [
        ("code_execution_deferred", "program", {"execution_required": True}),
        ("ifeval_official_deferred", "constraints", {}),
    ],
)
def test_deferred_has_no_accuracy_denominator(scorer, kind, metadata):
    ref = Reference(kind=kind, checks=[{"official": True}])
    score = score_record(
        record(scorer, kind, reference=ref, metadata=metadata), "anything"
    )
    assert score.status == "unsupported"
    assert score.answer_correct is None and score.strict_correct is None
