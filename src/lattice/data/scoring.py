"""Objective generated-answer scorers, with strict compliance reported separately.

These are versioned Lattice prompting/scoring protocols, not official leaderboard
scores. Code and official IFEval tasks remain explicitly unscored here.
"""

import json
import re
import string
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Literal

from .schema import DataRecord


@dataclass(frozen=True)
class Score:
    status: Literal["scored", "unsupported", "invalid_reference"]
    answer_correct: bool | None
    strict_correct: bool | None
    metrics: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)


_NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?(?:/\d+)?"


def number(value: str) -> Fraction:
    value = value.strip()
    if len(value) > 128 or not re.fullmatch(_NUMBER, value):
        raise ValueError("Not a bounded finite numeric literal")
    value = value.replace(",", "")
    if "/" in value:
        left, right = value.split("/", 1)
        return number(left) / number(right)
    try:
        result = Decimal(value)
        if not result.is_finite() or abs(result.adjusted()) > 100:
            raise ValueError("Numeric exponent outside scoring bounds")
        return Fraction(result)
    except InvalidOperation as exc:
        raise ValueError("Invalid numeric literal") from exc


def parse_json(text: str):
    def object_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Non-finite JSON constant")

    return json.loads(
        text,
        object_pairs_hook=object_pairs,
        parse_float=Decimal,
        parse_constant=invalid_constant,
    )


def json_equal(left, right) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if left is None or right is None:
        return left is right
    if isinstance(left, (int, float, Decimal)) and isinstance(
        right, (int, float, Decimal)
    ):
        return Decimal(str(left)) == Decimal(str(right))
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            json_equal(left[k], right[k]) for k in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            json_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def span_normalize(text: str) -> str:
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def span_metrics(prediction: str, answers: list[str]) -> dict:
    choices = answers or [""]
    prediction = span_normalize(prediction)
    best_em = 0.0
    best_f1 = 0.0
    for reference in choices:
        reference = span_normalize(reference)
        gold = reference.split()
        pred = prediction.split()
        em = float(prediction == reference)
        if not pred or not gold:
            f1 = float(pred == gold)
        else:
            overlap = sum((Counter(pred) & Counter(gold)).values())
            precision = overlap / len(pred)
            recall = overlap / len(gold)
            f1 = 2 * precision * recall / (precision + recall) if overlap else 0.0
        best_em = max(best_em, em)
        best_f1 = max(best_f1, f1)
    return {"exact_match": best_em, "token_f1": best_f1}


def constraint(check: dict, text: str) -> bool:
    kind = check["type"]
    if kind == "exact_text":
        return text.strip() == check["value"]
    if kind == "word_count":
        count = len(re.findall(r"\S+", text))
        return check["minimum"] <= count <= check["maximum"]
    if kind == "line_count":
        lines = [line for line in text.splitlines() if line.strip()]
        return len(lines) == check["count"]
    if kind == "starts_with":
        return text.startswith(check["value"])
    if kind == "ends_with":
        return text.rstrip().endswith(check["value"])
    if kind == "lowercase":
        return text == text.lower()
    if kind == "uppercase":
        return text == text.upper()
    if kind in ("required_keywords", "forbidden_keywords"):
        haystack = text if check.get("case_sensitive", False) else text.casefold()
        found = []
        for word in check["values"]:
            needle = word if check.get("case_sensitive", False) else word.casefold()
            if check.get("whole_words", False):
                found.append(
                    bool(
                        re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack)
                    )
                )
            else:
                found.append(needle in haystack)
        return all(found) if kind == "required_keywords" else not any(found)
    if kind == "keyword_frequency":
        value = (
            check["value"]
            if check.get("case_sensitive", False)
            else check["value"].casefold()
        )
        haystack = text if check.get("case_sensitive", False) else text.casefold()
        return (
            len(re.findall(r"(?<!\w)" + re.escape(value) + r"(?!\w)", haystack))
            == check["count"]
        )
    if kind == "json_value":
        try:
            return json_equal(parse_json(text), check["value"])
        except (ValueError, TypeError, RecursionError):
            return False
    raise ValueError("Unsupported constraint type: " + str(kind))


def score_record(record: DataRecord, text: str) -> Score:
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise ValueError("Response must be bounded text")
    output = text.strip()
    reference = record.reference
    if record.scorer in (
        "code_execution_deferred",
        "ifeval_official_deferred",
        "language_model_loss_deferred",
    ):
        return Score(
            "unsupported",
            None,
            None,
            details={"reason": record.scorer, "no_accuracy_denominator": True},
        )
    if record.scorer == "number_v1":
        try:
            gold = number(reference.value)
        except (ValueError, ZeroDivisionError):
            return Score("invalid_reference", None, None)
        strict = False
        method = "none"
        prediction = None
        try:
            prediction = number(output)
            strict = output == reference.value
            method = "entire_numeric_response"
        except (ValueError, ZeroDivisionError):
            final = re.findall(r"####\s*(" + _NUMBER + r")", output)
            if final:
                method = "explicit_final_marker"
            else:
                final = re.findall(_NUMBER, output)
                method = "heuristic_last_numeric_literal" if final else "none"
            if final:
                try:
                    prediction = number(final[-1])
                except (ValueError, ZeroDivisionError):
                    pass
        return Score(
            "scored",
            prediction == gold,
            strict,
            details={
                "extraction": method,
                "prediction": str(prediction) if prediction is not None else None,
            },
        )
    if record.scorer == "choice_v1":
        labels = record.metadata["choice_labels"]
        options = "".join(re.escape(c) for c in labels)
        found = None
        patterns = [
            rf"^\(?([{options}])\)?[.]?$",
            rf"(?im)^(?:final answer|answer|choice|option)\s*:\s*\(?([{options}])\)?[.]?\s*$",
            rf"^([{options}])[.)]\s+\S",
            rf"^\(([{options}])\)\s+\S",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, output)
            if matches:
                unique = set(matches)
                if len(unique) == 1:
                    found = matches[-1]
                break
        return Score(
            "scored",
            found == reference.value,
            output == reference.value,
            details={"prediction": found, "protocol": "anchored generated label"},
        )
    if record.scorer == "boolean_v1":
        literal = output.casefold().rstrip(".")
        exact = {"yes": True, "no": False, "true": True, "false": False}
        match = re.match(r"^(yes|no|true|false)(?=[.,:!\s]|$)", output, re.IGNORECASE)
        prediction = exact[match[1].casefold()] if match else None
        desired = "yes" if reference.value else "no"
        return Score(
            "scored",
            prediction is reference.value,
            output == desired,
            details={"prediction": prediction, "literal_recognized": literal in exact},
        )
    if record.scorer == "span_v1":
        prediction = "" if output.casefold() == "unanswerable" else output
        metrics = span_metrics(prediction, reference.alternatives)
        strict = (
            output in reference.alternatives
            if reference.alternatives
            else output == "UNANSWERABLE"
        )
        return Score(
            "scored",
            bool(metrics["exact_match"]),
            strict,
            metrics,
            {
                "answerable": bool(reference.alternatives),
                "predicted_answerable": bool(prediction),
            },
        )
    if record.scorer == "json_v1":
        strict_parse = True
        candidate = output
        fence = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", output, re.DOTALL)
        if fence:
            candidate = fence[1]
            strict_parse = False
        try:
            parsed = parse_json(candidate)
            correct = json_equal(parsed, reference.value)
        except (ValueError, TypeError, RecursionError):
            return Score("scored", False, False, {"json_valid": 0.0})
        return Score(
            "scored",
            correct,
            strict_parse and correct,
            {"json_valid": float(strict_parse)},
        )
    if record.scorer == "constraints_v1":
        checks = [constraint(item, text) for item in reference.checks]
        passed = all(checks)
        return Score(
            "scored",
            passed,
            passed,
            {"constraints_passed": sum(checks), "constraints_total": len(checks)},
        )
    if record.scorer == "text_v1":
        passed = output == reference.value
        return Score("scored", passed, passed)
    raise ValueError("Unknown scorer; no implicit pass/fail: " + record.scorer)
