"""Small, self-authored exact-scored smoke suite. Not a public benchmark replacement."""

import ast
import json
import re


def score(task: dict, text: str) -> bool:
    """Evaluate declared static rubrics without executing generated code."""
    answer = text.strip()
    if task["scorer"] == "exact":
        return answer == task["expected"]
    if task["scorer"] == "json":
        try:
            return json.loads(answer) == task["expected"]
        except (json.JSONDecodeError, TypeError):
            return False
    if task["scorer"] == "python_add_ast":
        answer = re.sub(r"^```(?:python)?\s*|\s*```$", "", answer)
        try:
            tree = ast.parse(answer)
        except (SyntaxError, ValueError, RecursionError):
            return False
        # Structural rubric only; does not imply arbitrary coding task correctness.
        return any(
            isinstance(node, ast.FunctionDef)
            and node.name == "add"
            and len(node.args.args) == 2
            and len(node.body) == 1
            and isinstance(node.body[0], ast.Return)
            and isinstance(node.body[0].value, ast.BinOp)
            and isinstance(node.body[0].value.op, ast.Add)
            and isinstance(node.body[0].value.left, ast.Name)
            and isinstance(node.body[0].value.right, ast.Name)
            and [node.body[0].value.left.id, node.body[0].value.right.id]
            == [a.arg for a in node.args.args]
            for node in tree.body
        )
    raise ValueError("Unknown quality scorer")
