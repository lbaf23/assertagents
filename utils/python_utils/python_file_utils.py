from typing import List, Tuple, Dict, Optional
import ast
import tree_sitter_python
from tree_sitter import Language, Parser

from utils.code_file_utils.code_file_utils import single_file_rag

PY_ASSERT_PLACEHOLDER = '<AssertPlaceHolder>'
PY_COM_ASSERT_PLACEHOLDER = '... # <AssertPlaceHolder>'


def get_python_method_name(method_code: str) -> str:
    # remove spaces
    lines = method_code.splitlines()
    sps = 1e6
    for line in lines:
        if line.strip() != '':
            sps = min(sps, len(line) - len(line.lstrip()))
    for i in range(len(lines)):
        lines[i] = lines[i][sps:]
    method_code = '\n'.join(lines)

    try:
        tree = ast.parse(method_code)
    except SyntaxError as e:
        print(e)
        return ''

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name

        elif isinstance(node, ast.AsyncFunctionDef):
            return node.name

        elif isinstance(node, ast.ClassDef):
            return node.name

    return ''


def get_python_function_ranges(code: str):
    parser = Parser(language=Language(tree_sitter_python.language()))
    code_bytes = bytes(code, 'utf-8')
    tree = parser.parse(code_bytes)
    root_node = tree.root_node

    results = []

    def find_preceding_comment(func_node):
        comment_start_lineno = None

        parent = func_node.parent
        if not parent:
            return None

        siblings = parent.children
        idx = siblings.index(func_node)

        i = idx - 1
        while i >= 0:
            node = siblings[i]
            if node.type in {'comment', 'block_comment', 'line_comment', 'decorator'}:
                node_start_line, node_end_line = node.start_point[0], node.end_point[0]
                has_code_on_same_line = False
                for other_node in siblings:
                    if other_node != node \
                            and other_node.type not in {'comment', 'block_comment', 'line_comment', 'decorator'}:
                        other_start_line, other_end_line = other_node.start_point[0], other_node.end_point[0]
                        if (
                                other_start_line <= node_start_line <= other_end_line
                                or other_start_line <= node_end_line <= other_end_line
                                or node_start_line <= other_start_line <= node_end_line
                                or node_start_line <= other_end_line <= node_end_line
                        ) and (
                                other_start_line == node_start_line or other_end_line == node_start_line
                        ):
                                has_code_on_same_line = True
                                break

                if not has_code_on_same_line and node.end_point[0] < func_node.start_point[0]:
                    comment_start_lineno = node.start_point[0] + 1
            elif node.type not in {'empty_statement'}:
                break
            i -= 1
        return comment_start_lineno

    type_map = {
        'class_definition': 'class',
        'function_definition': 'method',
    }

    def traverse(node, parent):
        curr = None
        if node.type in {'class_definition', 'function_definition'}:
            name = None
            start_lineno = node.start_point[0] + 1
            end_lineno = node.end_point[0] + 1

            body_start_lineno = end_lineno
            body_end_lineno = end_lineno
            for child in node.children:
                if child.type == 'identifier':
                    name = code_bytes[child.start_byte:child.end_byte].decode('utf-8')
                elif child.type == 'block':
                    body_start_lineno = child.start_point[0] + 1
                    body_end_lineno = child.end_point[0] + 1

            if name is not None:
                comment_start_lineno = find_preceding_comment(node)

                if comment_start_lineno is not None:
                    start_lineno = min(comment_start_lineno, start_lineno)

                curr = {
                    'type': type_map[node.type],
                    'name': name,
                    'start_lineno': start_lineno,
                    'end_lineno': end_lineno,
                    'class_name': '',
                    'body_start_lineno': body_start_lineno,
                    'body_end_lineno': body_end_lineno,
                    'parent': [],
                    'children': [],
                }

        if parent is not None and curr is not None:
            parent['children'].append(curr['start_lineno'])
            curr['parent'].append(parent['start_lineno'])
            curr['class_name'] = parent['name']

        if curr is not None:
            results.append(curr)

        if node.type not in {'function_definition'}:  # ignore functions in another function
            for child in node.children:
                traverse(child, curr if curr is not None else parent)

    traverse(root_node, None)
    return results


def remove_python_preview_comments(code: str, preview_with_lineno: bool = True):
    lines = code.splitlines()
    j = 0
    while j < len(lines):
        if preview_with_lineno:
            line = lines[j][lines[j].index(']') + 1 : ].lstrip()
        else:
            line = lines[j].lstrip()

        if line.startswith('"""'):
            while True:
                if preview_with_lineno:
                    line = lines[j][lines[j].index(']') + 1:].lstrip()
                else:
                    line = lines[j].lstrip()
                if line.endswith('"""'):
                    j += 1
                    break
                j += 1
            break
        elif line == '':
            j += 1
        else:
            break
    if j > 0:
        lines = lines[j : ]
    return '\n'.join(lines)


def remove_python_preview_imports(code: str, preview_with_lineno: bool = True) -> str:
    lines = code.splitlines()
    j = 0
    while j < len(lines):
        if preview_with_lineno:
            line = lines[j][lines[j].index(']') + 1 : ].lstrip()
        else:
            line = lines[j].lstrip()

        if line.startswith('from') or line.startswith('import'):
            while True:
                if preview_with_lineno:
                    line = lines[j][lines[j].index(']') + 1:].lstrip()
                else:
                    line = lines[j].lstrip()

                if line.startswith('from') or line.startswith('import') or line.strip() == '':
                    j += 1
                else:
                    break
            break
        elif line == '':
            j += 1
        else:
            break
    if j > 0:
        lines = lines[j : ]
    return '\n'.join(lines)



def get_python_function_body_inline(code: str, lineno: int, show_parent_class: bool, preview_add_lineno: bool) -> Optional[Dict]:
    """
    Return a function code that contains lineno
    Args:
        code:
        lineno:
        add_lineno

    Returns:

    """

    functions = get_python_function_ranges(code)
    lines = code.splitlines()
    linenos = [(i + 1) for i in range(len(lines))]

    target = None
    for function in functions:
        if function['start_lineno'] <= lineno <= function['end_lineno'] \
                and (target is None or function['start_lineno'] > target['start_lineno']):
            target = function

    if target is None:
        return None

    if target['type'] == 'class' or show_parent_class:
        if not preview_add_lineno and target['end_lineno'] - target['start_lineno'] + 1 <= 100:
            result_lines = lines[target['start_lineno'] - 1: target['end_lineno']]
            preview = '\n'.join(result_lines)
        else:
            preview = get_python_file_content_preview(code, [target['start_lineno']], preview_add_lineno)
            preview = remove_python_preview_comments(preview, preview_with_lineno=preview_add_lineno)
            preview = remove_python_preview_imports(preview, preview_with_lineno=preview_add_lineno)
    elif target['type'] == 'method' and target['name'] == '__init__':
        preview = get_python_file_content_preview(code, [target['start_lineno']], preview_add_lineno)
        preview = remove_python_preview_comments(preview, preview_with_lineno=preview_add_lineno)
        preview = remove_python_preview_imports(preview, preview_with_lineno=preview_add_lineno)
    else:
        result_lines = lines[target['start_lineno'] - 1 : target['end_lineno']]
        result_linenos = linenos[target['start_lineno'] - 1: target['end_lineno']]
        if preview_add_lineno:
            for i in range(len(result_lines)):
                result_lines[i] = f'[{result_linenos[i]}] ' + result_lines[i]
        preview = '\n'.join(result_lines)
    return {
        'preview': preview,
        'type': target['type'],
        'start_lineno': target['start_lineno'],
        'end_lineno': target['end_lineno'],
        'body_start_lineno': target['body_start_lineno'],
        'body_end_lineno': target['body_end_lineno'],
    }


def get_lineno(code: str, stmt: str, start_lineno: int) -> int:
    lineno = start_lineno
    lines = code.splitlines()
    for line in lines:
        if line.strip() == stmt:
            return lineno
        lineno += 1
    return -1


def add_lineno(code: str, start_lineno: int) -> str:
    lines = code.splitlines()
    lineno = start_lineno
    for i in range(len(lines)):
        lines[i] = f'[{lineno}] ' + lines[i]
        lineno += 1
    return '\n'.join(lines)


def include_target(code_start_lineno: int, code_end_lineno: int, target_start_lineno: int, target_end_lineno: int) -> bool:
    return code_start_lineno <= target_start_lineno and code_end_lineno >= target_end_lineno


def contains_idx(lst1, lst2) -> bool:
    for l1 in lst1:
        if l1 in lst2:
            return True
    return False

def contains_range(l1, l2, nos) -> bool:
    for no in nos:
        if l1 <= no <= l2:
            return True
    return False

def get_python_file_content_preview(code: str, show_target_start_linenos: List[int], preview_add_lineno: bool = True) -> str:
    targets = get_python_function_ranges(code)
    lines = code.splitlines()
    linenos = [i + 1 for i in range(len(lines))]

    result_lines = []
    result_linenos = []
    start_index = 0
    targets = sorted(targets, key=lambda t: t['start_lineno'])

    show_target = set()
    for target in targets:
        if target['start_lineno'] in show_target_start_linenos:
            show_target.add(target['start_lineno'])
        elif target['children'] == [] and contains_range(target['start_lineno'], target['end_lineno'], show_target_start_linenos):
            show_target.add(target['start_lineno'])

    has_split = False
    for target in targets:
        if not show_target.__contains__(target['start_lineno']):
            if contains_idx(target['children'], show_target):
                has_split = False
            elif contains_idx(target['parent'], show_target):
                # show method definition
                lines[target['body_start_lineno'] - 1] += ' ... # Folded'
                result_lines += lines[start_index : target['body_start_lineno']]
                result_linenos += linenos[start_index : target['body_start_lineno']]
                start_index = target['end_lineno']
                has_split = False
            else:
                result_lines += lines[start_index : target['start_lineno'] - 1]
                result_linenos += linenos[start_index : target['start_lineno'] - 1]
                start_index = target['end_lineno']

                if not has_split:
                    result_lines.append('...')
                    result_linenos.append('...')
                    has_split = True
        else:
            has_split = False

    result_lines += lines[start_index:]
    result_linenos += linenos[start_index:]

    skip_spaces = set()
    space_start = False
    for i in range(len(result_lines)):
        if result_lines[i].strip() == '':
            if space_start:
                skip_spaces.add(i)
            else:
                space_start = True
        else:
            space_start = False

    preview = ''
    for i in range(len(result_lines)):
        if i not in skip_spaces:
            if preview_add_lineno:
                preview += f'[{result_linenos[i]}] ' + result_lines[i] + '\n'
            else:
                preview += result_lines[i] + '\n'

    return preview.rstrip()


def remove_sps(code: str) -> str:
    lines = code.splitlines()
    sps = min([len(l) - len(l.lstrip()) for l in lines if l.strip() != ''])
    lines = [l[sps: ] for l in lines]
    return '\n'.join(lines)

def get_python_test_file_assert_preview(code: str, test_prefix: str, test_prefix_start_lineno: int, max_test_functions: int = 10) -> str:
    target_ranges = get_python_function_ranges(code)
    lines = code.splitlines()

    functions = []
    for target in target_ranges:
        if target['type'] in {'method'}: # and target[''] != '':
            # if target.__contains__('class_name') and target['class_name'] == class_name:
            function_body = '\n'.join(lines[target['start_lineno'] - 1 : target['end_lineno']])
            if function_body.__contains__('assert'):
                target['body'] = function_body
                functions.append(target)
    if len(functions) > 0:
        selected_idx = single_file_rag(
            functions=functions,
            query_func=test_prefix.replace(PY_COM_ASSERT_PLACEHOLDER, ''),
            top_k=max_test_functions,
        )
        selected_functions = [remove_sps(functions[i]['body']) for i in selected_idx]
        return '\n\n\n'.join(selected_functions)
    else:
        return remove_sps(test_prefix)





# def fold_python_function(code: str, exclude_functions_range: List[Tuple] = []) -> str:
#     """
#     Return a python file skeleton, remove all functions except exclude_functions_key
#     Args:
#         code:
#         exclude_functions_key: function_name:start_lineno
#
#     Returns:
#
#     """
#     functions = get_python_function_ranges(code)
#     lines = code.splitlines()
#     linenos = [(i + 1) for i in range(len(lines))]
#
#     results = []
#     results_linenos = []
#     start_index = 0
#     folded = False
#     for function in functions:
#         if function['type'] == 'class':
#
#
#         else:
#
#         if function['function_start_lineno'] <=
#         # if f'''{function['function_name']}:{function['function_start_lineno']}''' not in exclude_functions_key:
#             start_lineno = function['function_start_lineno']
#             # if function['comment_start_lineno'] != -1:
#             #     start_lineno = function['comment_start_lineno']
#
#             if not folded:
#                 results += lines[start_index: start_lineno - 1]
#                 results_linenos += linenos[start_index: start_lineno - 1]
#
#                 results.append('...')
#                 results_linenos.append('')
#             folded = True
#             start_index = function['function_end_lineno']
#         else:
#             folded = False
#
#     results += lines[start_index:]
#     results_linenos += linenos[start_index:]
#
#     res = ''
#     add_split = False
#     for i in range(len(results)):
#         if results_linenos[i] == '':
#             if add_split:
#                 continue
#             else:
#                 res += '...' + '\n'
#                 add_split = True
#         else:
#             add_split = False
#             res += f'[{results_linenos[i]}] ' + results[i] + '\n'
#
#     return res

#
# def fold_python_function_body(code: str, start_lineno: int = 1, exclude_functions_key: List[str] = [], add_lineno: bool = True) -> str:
#     """
#     Return a Python class skeleton, fold all functions' body except exclude_functions_key(function_name:lineno)
#
#     Args:
#         code:
#         exclude_functions_key:
#
#     Returns:
#
#     """
#     functions = get_python_function_ranges(code)
#     lines = code.splitlines()
#     linenos = [(i + 1) + (start_lineno - 1) for i in range(len(lines))]
#
#     results = []
#     results_linenos = []
#     start_index = 0
#     for function in functions:
#         if f'''{function['function_name']}:{function['function_start_lineno']}''' not in exclude_functions_key:
#             lines[function['body_start_lineno'] - 1] += ' # ... Folded'
#             results += lines[start_index : function['body_start_lineno']]
#             results_linenos += linenos[start_index : function['body_start_lineno']]
#             start_index = function['body_end_lineno']
#     results += lines[start_index:]
#     results_linenos += linenos[start_index:]
#
#     if add_lineno:
#         for i in range(len(results)):
#             results[i] = f'[{results_linenos[i]}] ' + results[i]
#     return '\n'.join(results)
#
