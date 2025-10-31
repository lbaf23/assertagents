from typing import List, Tuple
import javalang


def is_java_code_valid(code: str) -> bool:
    try:
        _ = javalang.parse.parse(code)
        return True
    except Exception:
        # parse error
        return False


def extract_java_asserts(content: str) -> List[str]:
    # common_asserts = ['assertEquals\(', 'assertNotEquals\(', 'assertSame\(', 'assertNotSame\(', 'assertArrayEquals\(', 'assertTrue\(', 'assertFalse\(', 'assertNull\(', 'assertNotNull\(']
    results = []
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith('assert') or line.startswith('Assert.') or line.startswith('org.junit.Assert.'):
            results.append(line)
    return results


default_str = '"STR"'


class AssertNormalizer:
    def normalize_assert(self, stmt: str, mask_str: bool) -> str:
        stmt = stmt.replace('org.junit.Assert.', '')
        stmt = stmt.replace('Assert.', '')

        try:
            java_code = f"class Example {{\nvoid test() {{\n{stmt}\n}}\n}}"
            tree = javalang.parse.parse(java_code)
        except Exception:
            # parse error
            return stmt

        method_invocation = None
        for _, node in tree:
            if isinstance(node, javalang.tree.MethodInvocation):
                method_invocation = node
                break

        if not method_invocation:
            return stmt

        method = method_invocation.member
        args = [self._expr_to_str(a, mask_str) for a in method_invocation.arguments]

        # === assertTrue / assertFalse / assertNull / assertNotNull ===
        if method in ["assertTrue", "assertFalse", "assertNull", "assertNotNull"]:
            if len(args) == 1:
                target = args[0]
            elif len(args) == 2 and args[0].startswith('"') and args[0].endswith('"'):
                target = args[1]  # 有 message
            else:
                target = args[-1] if len(args) > 0 else ''  # fallback

            if method == "assertTrue":
                return f"{target} == true"
            if method == "assertFalse":
                return f"{target} == false"
            if method == "assertNull":
                return f"{target} == null"
            if method == "assertNotNull":
                return f"{target} != null"

        # === assertEquals / assertNotEquals ===
        if method in ["assertEquals", "assertNotEquals"]:
            op = "==" if method == "assertEquals" else "!="
            if len(args) == 2:
                # (expected, actual)
                expected, actual = args
            elif len(args) == 3:
                if args[0].startswith('"') and args[0].endswith('"') and not self._is_number_literal(args[1]):
                    # (message, expected, actual)
                    expected, actual = args[1], args[2]
                else:
                    # (expected, actual, delta), ignore delta
                    expected, actual = args[0], args[1]
            elif len(args) == 4:
                # (message, expected, actual, delta), ignore delta
                expected, actual = args[1], args[2]
            else:
                return stmt
            return self._normalize_symmetric(expected, actual, op)

        # === assertSame / assertNotSame ===
        if method in ["assertSame", "assertNotSame"]:
            op = "===" if method == "assertSame" else "!=="
            if len(args) == 2:
                # (expected, actual)
                return self._normalize_symmetric(args[0], args[1], op)
            elif len(args) == 3 and args[0].startswith('"') and args[0].endswith('"'):
                # (message, expected, actual)
                return self._normalize_symmetric(args[1], args[2], op)

        # === assertArrayEquals ===
        if method == "assertArrayEquals":
            if len(args) >= 2:
                return self._normalize_symmetric(f"Arrays.equals({args[0]}, {args[1]})", "true", "==")

        return stmt

    def _add_prefix(self, expr, indent: str):
        if expr.prefix_operators is not None and len(expr.prefix_operators) > 0:
            indent += ''.join(expr.prefix_operators)
        return indent

    def _add_postfix(self, expr, indent: str):
        if expr.postfix_operators is not None and len(expr.postfix_operators) > 0:
            indent += ''.join(expr.postfix_operators)
        return indent

    def _add_qualifier(self, expr, indent: str):
        if expr.qualifier is not None:
            indent += expr.qualifier + '.'
        return indent

    def _add_selectors(self, expr, indent: str, mask_str: bool):
        if expr.selectors is not None and len(expr.selectors) > 0:
            indent += '.' + '.'.join([self._expr_to_str(s, mask_str) for s in expr.selectors])
        return indent

    def _expr_to_str(self, expr, mask_str: bool):
        if isinstance(expr, javalang.tree.Literal):
            indent = self._add_prefix(expr, '')
            indent = self._add_qualifier(expr, indent)

            # check mask str
            if mask_str and expr.value.startswith('"') and expr.value.endswith('"'):
                indent += default_str
            else:
                indent += expr.value

            indent = self._add_postfix(expr, indent)
            indent = self._add_selectors(expr, indent, mask_str)
            return indent.strip('.')

        elif isinstance(expr, javalang.tree.MemberReference):
            if expr.qualifier == 'Boolean' and expr.member == 'TRUE':
                return 'true'
            if expr.qualifier == 'Boolean' and expr.member == 'FALSE':
                return 'false'

            indent = self._add_prefix(expr, '')
            indent = self._add_qualifier(expr, indent)
            indent += expr.member
            indent = self._add_postfix(expr, indent)
            indent = self._add_selectors(expr, indent, mask_str)
            return indent.strip('.')

        elif isinstance(expr, javalang.tree.MethodInvocation):
            indent = self._add_prefix(expr, '')
            indent = self._add_qualifier(expr, indent)
            indent += expr.member

            args = ','.join(self._expr_to_str(a, mask_str) for a in expr.arguments)
            indent += f'({args})'

            indent = self._add_postfix(expr, indent)
            indent = self._add_selectors(expr, indent, mask_str)
            return indent.strip('.')

        elif isinstance(expr, javalang.tree.BinaryOperation):
            indent = ''
            if expr.operandl is not None:
                indent += self._expr_to_str(expr.operandl, mask_str)
            indent += expr.operator
            if expr.operandr is not None:
                indent += self._expr_to_str(expr.operandr, mask_str)

            return indent.strip('.')

        else:
            return str(expr)

    def _normalize_symmetric(self, a, b, op):
        terms = sorted([a.strip(), b.strip()])
        return f"{terms[0]} {op} {terms[1]}"

    def _is_number_literal(self, s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False


def is_java_assert_same(assert_stmt1: str, assert_stmt2: str, mask_str) -> bool:
    normalizer = AssertNormalizer()
    assert_stmt1 = normalizer.normalize_assert(assert_stmt1, mask_str)
    assert_stmt2 = normalizer.normalize_assert(assert_stmt2, mask_str)
    return assert_stmt1 == assert_stmt2


def check_assert_code(assert_code: str, test_prefix: str, test_prefix_start_lineno: int, placeholder: str) -> Tuple[bool, str]:
    # 1. check syntax
    acode = assert_code.replace('Assert.', '').replace('org.junit.Assert.', '')

    try:
        java_code = f"class Example {{\nvoid test() {{\n{acode}\n}}\n}}"
        _ = javalang.parse.parse(java_code)
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
    assert ... // check duplicate
    
    assert ... // current assert

    assert ... // check duplicate
    ...
    """
    if ph_i >= 0:
        assert_lines = []
        assert_linenos = []
        for i in range(ph_i - 1, 0):
            line = lines[i].strip()
            if line == '':
                pass
            elif line.startswith('assert') or line.startswith('Assert.') or line.startswith('org.junit.Assert.'):
                line = line.replace('Assert.', '').replace('org.junit.Assert.', '')
                assert_lines.append(line)
                assert_linenos.append(linenos[i])
                break
            else:
                break

        for i in range(ph_i + 1, len(lines)):
            line = lines[i].strip()
            if line == '':
                pass
            elif line.startswith('assert') or line.startswith('Assert.') or line.startswith('org.junit.Assert.'):
                line = line.replace('Assert.', '').replace('org.junit.Assert.', '')
                assert_lines.append(line)
                assert_linenos.append(linenos[i])
                break
            else:
                break

        if assert_lines.__contains__(acode):
            lno = assert_linenos[assert_lines.index(acode)]
            return False, f'Static check failed. The generated assert statement is a duplicate check with the assert statement on line {lno}.'

    return True, 'The generated assert statement passes the static check.'
