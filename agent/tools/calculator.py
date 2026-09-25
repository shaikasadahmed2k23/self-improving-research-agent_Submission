"""Safe arithmetic evaluator (AST whitelist, no eval())."""
import ast
import math
import operator
import re

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "exp": math.exp,
    "abs": abs, "round": round, "min": min, "max": max, "sum": lambda *a: sum(a),
}
_CONSTS = {"pi": math.pi, "e": math.e}
MAX_EXPONENT = 100


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError(f"Exponent too large (max {MAX_EXPONENT})")
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError(f"Unsupported expression element: {ast.dump(node)[:60]}")


def calculate(expression: str) -> float | int:
    """Evaluate an arithmetic expression, e.g. '10 * 0.33 + 50' or 'sqrt(2) * 3'."""
    expr = re.sub(r"(?<=\d),(?=\d{3}\b)", "", expression).replace("^", "**").strip()  # 1,000 -> 1000
    if len(expr) > 200:
        raise ValueError("Expression too long")
    result = _eval(ast.parse(expr, mode="eval"))
    if isinstance(result, float) and result.is_integer() and abs(result) < 1e15:
        return int(result)
    return round(result, 6) if isinstance(result, float) else result
