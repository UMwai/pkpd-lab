"""Small arithmetic interpreter with dimensional checking; never executes Python."""

import ast
import math
import operator
from dataclasses import dataclass

Dimension = tuple[float, float, float, float]  # mg, L, h, response
ONE: Dimension = (0, 0, 0, 0)
MASS: Dimension = (1, 0, 0, 0)
TIME: Dimension = (0, 0, 1, 0)
CONCENTRATION: Dimension = (1, -1, 0, 0)
RATE: Dimension = (1, 0, -1, 0)
FUNCTIONS = {"exp": math.exp, "log": math.log, "sin": math.sin, "cos": math.cos}


def combine(a, b, sign=1):
    return tuple(x + sign * y for x, y in zip(a, b, strict=True))


def scale(a, power):
    return tuple(x * power for x in a)


def _tree(text):
    if not text.strip() or len(text) > 512:
        raise ValueError("Expression must contain 1–512 characters")
    try:
        tree = ast.parse(text.replace("^", "**"), mode="eval").body
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("Invalid arithmetic expression") from exc
    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError("Expression is too complex (maximum 100 syntax nodes)")
    return tree


def _constant(node):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        if abs(node.value) <= 1e100 and math.isfinite(node.value):
            return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _constant(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
    raise ValueError("Expected a finite numeric constant")


def _dimension(node, symbols, *, units=False):
    if isinstance(node, ast.Constant):
        value = _constant(node)
        if units and value != 1:
            raise ValueError("Units use base symbols, not conversion factors")
        return ONE
    if isinstance(node, ast.Name):
        if node.id not in symbols:
            raise ValueError(f"Unknown symbol: {node.id}")
        return symbols[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)) and not units:
        return _dimension(node.operand, symbols)
    if isinstance(node, ast.BinOp):
        left = _dimension(node.left, symbols, units=units)
        if isinstance(node.op, ast.Pow):
            power = _constant(node.right)
            if not power.is_integer() or abs(power) > 8:
                raise ValueError("Powers must be integer constants between -8 and 8")
            return scale(left, power)
        right = _dimension(node.right, symbols, units=units)
        if isinstance(node.op, (ast.Add, ast.Sub)) and not units:
            if left != right:
                raise ValueError("Addition/subtraction requires matching units")
            return left
        if isinstance(node.op, ast.Mult):
            return combine(left, right)
        if isinstance(node.op, ast.Div):
            return combine(left, right, -1)
    if isinstance(node, ast.Call) and not units:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in FUNCTIONS
            and len(node.args) == 1
            and not node.keywords
        ):
            if _dimension(node.args[0], symbols) != ONE:
                raise ValueError(f"{node.func.id} requires a dimensionless argument")
            return ONE
    raise ValueError("Only numbers, named variables, + - * / ^, and exp/log/sin/cos are allowed")


def unit_dimension(text: str) -> Dimension:
    return _dimension(
        _tree(text),
        {"mg": MASS, "L": (0, 1, 0, 0), "h": TIME, "response": (0, 0, 0, 1)},
        units=True,
    )


def _value(node, values):
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.UnaryOp):
        return _value(node.operand, values) * (-1 if isinstance(node.op, ast.USub) else 1)
    if isinstance(node, ast.BinOp):
        op = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
        }[type(node.op)]
        return op(_value(node.left, values), _value(node.right, values))
    return FUNCTIONS[node.func.id](_value(node.args[0], values))


@dataclass(frozen=True)
class Expression:
    source: str
    tree: ast.AST
    references: frozenset[str]

    @classmethod
    def compile(cls, source, symbols, expected):
        tree = _tree(source)
        dimension = _dimension(tree, symbols)
        zero = (
            isinstance(tree, ast.Constant) and type(tree.value) in (int, float) and tree.value == 0
        )
        if dimension != expected and not zero:
            raise ValueError(f"Equation units do not match its derivative order: {source}")
        refs = frozenset(
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in FUNCTIONS
        )
        return cls(source, tree, refs)

    def evaluate(self, values):
        try:
            value = float(_value(self.tree, values))
        except (ArithmeticError, ValueError, TypeError) as exc:
            raise ValueError(f"Expression failed: {self.source} ({exc})") from exc
        if not math.isfinite(value):
            raise ValueError(f"Expression returned a nonfinite value: {self.source}")
        return value
