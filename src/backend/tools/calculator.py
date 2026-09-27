"""Calculator tool providing safe arithmetic evaluation."""

import ast
import operator
import re
from typing import Any

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float | int:
    """Recursively evaluate an AST expression using only safe arithmetic operations."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero")
        if op_type == ast.Pow and (abs(right) > 1000 or (isinstance(left, (int, float)) and abs(left) > 1e10)):
            raise ValueError("Exponentiation values too large")
        return _OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _safe_eval(node.operand)
        return _OPERATORS[op_type](operand)

    raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def extract_math_expression(query: str) -> str:
    """Extract arithmetic expression candidate from natural language query."""
    cleaned = query.strip()
    # Strip common leading query prefixes
    prefixes = [
        r"^(?:calculate|compute|evaluate|what\s+is|what's|how\s+much\s+is)\s+",
        r"^(?:please\s+calculate|solve)\s+",
    ]
    for prefix in prefixes:
        cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE).strip()

    # Remove trailing question marks or punctuation
    cleaned = cleaned.rstrip("?!= \t\n")
    return cleaned


class CalculatorTool:
    """Tool for evaluating arithmetic expressions safely."""

    name: str = "calculator"

    def evaluate(self, expression: str) -> dict[str, Any]:
        """Evaluate an arithmetic expression string."""
        expr = expression.strip()
        if not expr:
            return {
                "success": False,
                "expression": expression,
                "error": "Empty arithmetic expression",
            }

        try:
            parsed = ast.parse(expr, mode="eval")
            result = _safe_eval(parsed)
            # Normalize float results that are whole numbers
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            return {
                "success": True,
                "expression": expr,
                "result": result,
            }
        except ZeroDivisionError:
            return {
                "success": False,
                "expression": expr,
                "error": "Division by zero",
            }
        except (ValueError, SyntaxError) as err:
            return {
                "success": False,
                "expression": expr,
                "error": f"Invalid or unsafe arithmetic expression: {err}",
            }
        except Exception as err:
            return {
                "success": False,
                "expression": expr,
                "error": f"Calculation error: {err}",
            }

    def run(self, query: str) -> dict[str, Any]:
        """Parse natural language query and compute result."""
        expr = extract_math_expression(query)
        return self.evaluate(expr)
