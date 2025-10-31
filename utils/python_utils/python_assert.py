from typing import List, Tuple
import ast


def extract_python_asserts(content: str) -> List[str]:
    results = []
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith('assert') or line.startswith('self.assert'):
            results.append(line)
    return results

class AssertNormalizerPython:
    def normalize_assert(self, stmt: str, mask_str: bool = False) -> str:
        try:
            tree = ast.parse(stmt)
        except SyntaxError:
            return stmt

        if not tree.body or not isinstance(tree.body[0], (ast.Assert, ast.Expr)):
            return stmt

        node = tree.body[0]

        cps = []
        # assert ... ===
        if isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Compare):
                left = self._expr_to_str(node.test.left, mask_str)
                comps = [self._expr_to_str(comp, mask_str) for comp in node.test.comparators]
                ops = node.test.ops
                length = min(len(comps), len(ops))
                for i in range(length):
                    cps.append({'left': left, 'op': ops[i], 'right': comps[i]})
                    left = comps[i]

            elif type(node.test) == ast.UnaryOp:
                if type(node.test.op) == ast.Not:
                    test_str = self._expr_to_str(node.test.operand, mask_str)
                    cps.append({'left': test_str, 'op': ast.Not(), 'right': ''})
                else:
                    test_str = self._expr_to_str(node.test, mask_str)
                    cps.append({'left': test_str, 'op': '', 'right': ''})
            elif type(node.test) == ast.BoolOp:
                left = self._expr_to_str(node.test.values[0], mask_str)
                right = self._expr_to_str(node.test.values[1], mask_str)
                cps.append({'left': left, 'op': node.test.op, 'right': right})
            else:
                test_str = self._expr_to_str(node.test, mask_str)
                cps.append({'left': test_str, 'op': '', 'right': ''})

        # unittest
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            method = self._get_method_name(call.func)
            if not method:
                return stmt

            args = [self._expr_to_str(a, mask_str) for a in call.args]

            # === assertTrue / assertFalse / assertIsNone / assertIsNotNone ===
            if method in ["assertTrue", "assertFalse", "assertIsNone", "assertIsNotNone"]:
                target = args[-1] if len(args) > 0 else "?"
                if method == "assertTrue":
                    cps.append({'left': target, 'op': ast.Is(), 'right': 'True'})
                elif method == "assertFalse":
                    cps.append({'left': target, 'op': ast.IsNot(), 'right': 'True'})
                elif method == "assertIsNone":
                    cps.append({'left': target, 'op': ast.Is(), 'right': 'None'})
                elif method == "assertIsNotNone":
                    cps.append({'left': target, 'op': ast.IsNot(), 'right': 'None'})

            # === assertEqual / assertNotEqual ===
            elif method == 'assertEqual':
                cps.append({'left': args[0], 'op': ast.Eq(), 'right': args[1]})
            elif method == 'assertNotEqual':
                cps.append({'left': args[0], 'op': ast.NotEq(), 'right': args[1]})

            # === assertIs / assertIsNot ===
            elif method == 'assertIs':
                cps.append({'left': args[0], 'op': ast.Is(), 'right': args[1]})

            elif method == 'assertIsNot':
                cps.append({'left': args[0], 'op': ast.IsNot(), 'right': args[1]})

            # === assertIn / assertNotIn ===
            elif method == 'assertIn':
                cps.append({'left': args[0], 'op': ast.In(), 'right': args[1]})

            elif method == 'assertNotIn':
                cps.append({'left': args[0], 'op': ast.In(), 'right': args[1]})

            # === assertAlmostEqual ===
            elif method == 'assertAlmostEqual':
                cps.append({'left': args[0], 'op': ast.Eq(), 'right': args[1]})


        # Final result
        str_cps = []
        for cp in cps:
            left, op, right = cp['left'], cp['op'], cp['right']
            if left == 'False':
                left = 'True'
                op = self._not_op(op)

            if right == 'False':
                right = 'True'
                op = self._not_op(op)

            if left > right:
                rv, rvop = self._reverse_op(op)
                if rv:
                    str_cps.append(f'{right} {rvop} {left}')
                else:
                    str_cps.append(f"{left} {self._op_to_str(op)} {right}")
            else:
                str_cps.append(f"{left} {self._op_to_str(op)} {right}")

        str_cps = sorted(str_cps)
        return ' && '.join(str_cps)

    def _get_method_name(self, func):
        if isinstance(func, ast.Attribute):
            return func.attr
        elif isinstance(func, ast.Name):
            return func.id
        else:
            return None

    def _expr_to_str(self, expr, mask_str: bool):
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, str):
                return '"STR"' if mask_str else repr(expr.value)
            return repr(expr.value)
        elif isinstance(expr, ast.Name):
            return expr.id
        elif isinstance(expr, ast.Attribute):
            return f"{self._expr_to_str(expr.value, mask_str)}.{expr.attr}"
        elif isinstance(expr, ast.Call):
            func_str = self._expr_to_str(expr.func, mask_str)
            args_str = ",".join(self._expr_to_str(a, mask_str) for a in expr.args)
            return f"{func_str}({args_str})"
        elif isinstance(expr, ast.Compare):
            left = self._expr_to_str(expr.left, mask_str)
            ops = " ".join(self._op_to_str(op) for op in expr.ops)
            rights = " ".join(self._expr_to_str(c, mask_str) for c in expr.comparators)
            return f"{left} {ops} {rights}"
        elif isinstance(expr, ast.BinOp):
            left = self._expr_to_str(expr.left, mask_str)
            right = self._expr_to_str(expr.right, mask_str)
            op = self._op_to_str(expr.op)
            return f"{left} {op} {right}"
        elif isinstance(expr, ast.UnaryOp):
            op = self._op_to_str(expr.op)
            operand = self._expr_to_str(expr.operand, mask_str)
            return f"{op}{operand}"
        else:
            return ast.unparse(expr) if hasattr(ast, "unparse") else str(expr)

    def _op_to_str(self, op):
        return {
            ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%",
            ast.Eq: "==", ast.NotEq: "!=", ast.Gt: ">", ast.GtE: ">=", ast.Lt: "<", ast.LtE: "<=",
            ast.Is: "is", ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in",
            ast.And: "and", ast.Or: "or", ast.Not: "not ", ast.USub: "-", ast.UAdd: "+",
        }.get(type(op), str(op))

    def _not_op(self, op):
        if type(op) is ast.NotEq:
            return ast.Eq()
        elif type(op) is ast.Eq:
            return ast.NotEq()
        elif type(op) is ast.Is:
            return ast.IsNot()
        elif type(op) is ast.IsNot:
            return ast.Is()
        else:
            return op

    def _reverse_op(self, op) -> Tuple:
        if type(op) in {ast.Eq, ast.NotEq, ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Is, ast.IsNot, ast.And, ast.Or}:
            return True, {
                ast.Eq: "==", ast.NotEq: "!=", ast.Gt: "<", ast.GtE: "<=", ast.Lt: ">", ast.LtE: ">=",
                ast.Is: "is", ast.IsNot: "is not",
                ast.And: "and", ast.Or: "or"
            }.get(type(op), "?")
        return False, self._op_to_str(op)

    def _normalize_symmetric(self, a, b, op):
        terms = sorted([a.strip(), b.strip()])
        return f"{terms[0]} {op} {terms[1]}"

    def _is_logical_expr(self, expr):
        return isinstance(expr, (ast.Compare, ast.BoolOp, ast.UnaryOp, ast.BinOp, ast.Call))


def check_assert_code(assert_code: str, test_prefix: str, test_prefix_start_lineno: int, placeholder: str) -> Tuple[bool, str]:
    # 1. check syntax
    try:
        _ = ast.parse(assert_code.strip())
    except Exception:
        # parse error
        return False, f'Static check failed. The generated assert statement has a syntax error.'

    # 2. check duplicate
    lines = test_prefix.splitlines()
    linenos = [i + test_prefix_start_lineno for i in range(len(lines))]

    ph_i = -1
    for i, line in enumerate(lines):
        line = line.strip()
        if line == placeholder:
            ph_i = i
            break

    """
    ...
    assert ... # check duplicate

    assert ... # current assert

    assert ... # check duplicate
    ...
    """
    if ph_i >= 0:
        assert_lines = []
        assert_linenos = []
        for i in range(ph_i - 1, 0):
            line = lines[i].strip()
            if line == '':
                pass
            elif line.startswith('assert') or line.startswith('self.assert'):
                assert_lines.append(line)
                assert_linenos.append(linenos[i])
                break
            else:
                break

        for i in range(ph_i + 1, len(lines)):
            line = lines[i].strip()
            if line == '':
                pass
            elif line.startswith('assert') or line.startswith('self.assert'):
                assert_lines.append(line)
                assert_linenos.append(linenos[i])
                break
            else:
                break

        if assert_lines.__contains__(assert_code):
            lno = assert_linenos[assert_lines.index(assert_code)]
            return False, f'Static check failed. The generated assert statement is a duplicate check with the assert statement on line {lno}.'

    return True, 'The generated assert statement passes the static check.'


def is_python_assert_same(assert_stmt1: str, assert_stmt2: str, mask_str: bool) -> bool:
    try:
        norm_a = AssertNormalizerPython().normalize_assert(assert_stmt1, mask_str)
        norm_b = AssertNormalizerPython().normalize_assert(assert_stmt2, mask_str)
    except Exception:
        return False
    return norm_a == norm_b
