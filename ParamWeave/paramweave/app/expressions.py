"""Safe arithmetic expressions for Expression nodes.

Expressions come from graph JSON, which is untrusted, so they are never passed
to ``eval()``. The text is parsed with ``ast`` and only a whitelist of node
kinds is interpreted: numbers, named variables, arithmetic/comparison
operators, conditional expressions and calls to the functions below.
Pure Python: no FreeCAD or Qt imports.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Dict, Mapping

MAX_LENGTH = 500
MAX_EXPONENT = 1000.0


class ExpressionError(ValueError):
    pass


FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "sin": lambda d: math.sin(math.radians(d)),
    "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
    "asin": lambda v: math.degrees(math.asin(v)),
    "acos": lambda v: math.degrees(math.acos(v)),
    "atan": lambda v: math.degrees(math.atan(v)),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    "hypot": math.hypot,
    "log": math.log,
    "exp": math.exp,
    "clamp": lambda v, lo, hi: max(lo, min(hi, v)),
}
CONSTANTS = {"pi": math.pi, "e": math.e}

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_COMPARE = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


def parse(text: str) -> ast.Expression:
    text = str(text or "").strip()
    if not text:
        raise ExpressionError("expression is empty")
    if len(text) > MAX_LENGTH:
        raise ExpressionError(f"expression is longer than {MAX_LENGTH} characters")
    try:
        return ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid expression: {exc.msg}") from None


def names_used(text: str) -> set:
    """Variable names an expression reads (excluding functions and constants)."""
    tree = parse(text)
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in called and n.id not in CONSTANTS
    }


def evaluate(text: str, variables: Mapping[str, float] = None) -> float:
    variables: Dict[str, float] = dict(variables or {})
    result = _eval(parse(text).body, variables)
    if isinstance(result, bool):
        result = float(result)
    if not isinstance(result, (int, float)) or not math.isfinite(result):
        raise ExpressionError(f"expression did not produce a finite number ({result!r})")
    return float(result)


def _eval(node, variables):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExpressionError(f"only numbers are allowed, not {node.value!r}")
        return node.value
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        known = ", ".join(sorted(variables)) or "none"
        raise ExpressionError(f"unknown name {node.id!r} (available: {known})")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _eval(node.left, variables), _eval(node.right, variables)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ExpressionError("exponent is too large")
        try:
            return _BINARY[type(node.op)](left, right)
        except (ZeroDivisionError, OverflowError, ValueError) as exc:
            raise ExpressionError(str(exc)) from None
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, variables))
    if isinstance(node, ast.Compare) and all(type(op) in _COMPARE for op in node.ops):
        left = _eval(node.left, variables)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, variables)
            if not _COMPARE[type(op)](left, right):
                return 0.0
            left = right
        return 1.0
    if isinstance(node, ast.IfExp):
        return _eval(node.body if _eval(node.test, variables) else node.orelse, variables)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        fn = FUNCTIONS.get(node.func.id)
        if fn is None:
            raise ExpressionError(f"unknown function {node.func.id!r} (available: {', '.join(sorted(FUNCTIONS))})")
        args = [_eval(a, variables) for a in node.args]
        try:
            return fn(*args)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ExpressionError(f"{node.func.id}(): {exc}") from None
    raise ExpressionError(f"unsupported syntax: {type(node).__name__}")
