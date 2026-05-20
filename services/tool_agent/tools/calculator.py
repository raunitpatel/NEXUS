"""
Calculator tool for the NEXUS Tool Agent.

Evaluates arithmetic expressions safely using ast.literal_eval-inspired
node visitor. Never uses eval() — prevents code injection.

Supports: +, -, *, /, //, %, ** and parentheses.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    """
    Recursively evaluate an AST node as an arithmetic expression.

    Args:
        node: AST node from ast.parse().

    Returns:
        Numeric result.

    Raises:
        ValueError: If the expression contains unsupported operations.
    """
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp):
        op_func = _OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return op_func(left, right)
    if isinstance(node, ast.UnaryOp):
        op_func = _OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_func(_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


class CalculatorTool:
    """
    Safe arithmetic expression evaluator for the Tool Agent.

    Uses Python's ast module to parse and evaluate expressions without
    calling eval() — prevents any code injection via tool input.
    """

    async def run(self, expression: str) -> dict[str, Any]:
        """
        Evaluate an arithmetic expression and return the numeric result.

        Args:
            expression: Arithmetic expression string (e.g. "137 * 42").

        Returns:
            Dict with 'result' (float) and 'expression' (str).
            On error, returns dict with 'error' key.
        """
        logger.debug("calculator.run", expression=expression)
        try:
            tree = ast.parse(expression.strip(), mode="eval")
            result = _safe_eval(tree)
            # Return int if result is whole number
            display = int(result) if result == int(result) else result
            return {"result": display, "expression": expression}
        except ZeroDivisionError:
            return {"error": "Division by zero", "expression": expression}
        except (ValueError, SyntaxError) as exc:
            return {"error": f"Invalid expression: {exc}", "expression": expression}