from typing import Optional, Dict
from tree_sitter import Parser, Language, Node
import tree_sitter_python

from ..file_utils import read_file


def _get_byte_offset_from_lsp_position_py(source_code: str, line: int, character: int) -> Optional[int]:
    lines = source_code.splitlines(keepends=True)
    if 0 <= line < len(lines):
        offset = sum(len(line_content.encode('utf-8')) for line_content in lines[:line])
        offset += len(lines[line][:character].encode('utf-8'))
        return offset
    return None


def _find_node_at_byte_offset_py(node, target_byte_offset):
    if node.start_byte <= target_byte_offset < node.end_byte:
        for child in node.children:
            found_child = _find_node_at_byte_offset_py(child, target_byte_offset)
            if found_child:
                return found_child
        return node
    return None


def _get_node_line_range_py(node):
    start_line = node.start_point[0]
    end_line = node.end_point[0]
    return start_line, end_line


def _find_decorator_start_line_ast_py(source_code: str, root_node, current_start_line_0b, decorator_type):
    lines = source_code.splitlines(keepends=True)
    element_start_byte_offset = sum(len(line_content.encode('utf-8')) for line_content in lines[:current_start_line_0b])

    def traverse_tree_for_decorators(node, found_decorators):
        if node.type == decorator_type:
            if node.end_byte <= element_start_byte_offset:
                decorator_start_line = node.start_point[0]
                if decorator_start_line < current_start_line_0b:
                    found_decorators.append(decorator_start_line)

        for child in node.children:
            traverse_tree_for_decorators(child, found_decorators)

    all_found_decorator_lines = []
    traverse_tree_for_decorators(root_node, all_found_decorator_lines)

    if not all_found_decorator_lines:
        return current_start_line_0b

    highest_relevant_decorator_line = max(all_found_decorator_lines)

    decorator_lines_set = set(all_found_decorator_lines)
    current_line = highest_relevant_decorator_line

    while current_line > 0 and current_line - 1 in decorator_lines_set:
        current_line -= 1

    decorator_start_line = current_line

    return decorator_start_line


def _extract_name_from_node_py(node, parent_type):
    for child in node.children:
        if child.type == 'identifier':
            name_text = node.text[child.start_byte - node.start_byte: child.end_byte - node.start_byte].decode('utf-8')
            return name_text
    return ""


def get_python_function_source(file_path: str, line: int, character: int) -> Optional[Dict]:
    file_content = read_file(file_path)
    file_lines = file_content.splitlines()
    parser = Parser(Language(tree_sitter_python.language()))
    tree = parser.parse(bytes(file_content, "utf-8"))
    root_node = tree.root_node

    target_position_bytes = _get_byte_offset_from_lsp_position_py(file_content, line, character)
    if target_position_bytes is None:
        return None

    target_node = _find_node_at_byte_offset_py(root_node, target_position_bytes)

    if not target_node:
        return None

    result = None
    current_node = target_node

    while current_node and current_node != root_node:
        if current_node.type == 'function_definition':
            start_line, end_line = _get_node_line_range_py(current_node)
            decorator_start_line = _find_decorator_start_line_ast_py(file_content, root_node, start_line, 'decorator')
            name = _extract_name_from_node_py(current_node, 'function_definition')

            start_lineno = min(decorator_start_line + 1, start_line + 1)
            end_lineno = end_line + 1
            result = {
                'type': 'function',
                'name': name,
                'body': '\n'.join(file_lines[start_lineno - 1 : end_lineno]),
                'start_lineno': start_lineno,
                'end_lineno': end_lineno
            }
            break

        elif current_node.type == 'class_definition':
            start_line, end_line = _get_node_line_range_py(current_node)
            decorator_start_line = _find_decorator_start_line_ast_py(file_content, root_node, start_line, 'decorator')
            name = _extract_name_from_node_py(current_node, 'class_definition')

            start_lineno = min(decorator_start_line + 1, start_line + 1)
            end_lineno = end_line + 1
            result = {
                'type': 'class',
                'name': name,
                'body': '\n'.join(file_lines[start_lineno - 1 : end_lineno]),
                'start_lineno': start_lineno,
                'end_lineno': end_lineno
            }
            break

        current_node = current_node.parent

    return result


from typing import List, Any
def find_python_function_calls(code: str, start_lineno: int) -> List[Dict[str, Any]]:
    parser = Parser(language=Language(tree_sitter_python.language()))
    tree = parser.parse(bytes(code, "utf8"))
    calls = []
    def find_function_calls(node: Node):
        for node in node.children:
            if node.type == "call":
                function_node = node.child_by_field_name("function")
                if function_node:
                    if function_node.type == "attribute":
                        fc = function_node.children[-1]
                        name = code[fc.start_byte : fc.end_byte]
                    else:
                        fc = function_node
                        name = code[function_node.start_byte:function_node.end_byte]

                    line, character = fc.start_point
                    end_line, end_character = fc.end_point
                    line = line + start_lineno - 1
                    end_line = end_line + start_lineno - 1

                    calls.append({
                        'type': 'method',
                        'name': name,
                        'line': line,
                        'character': character,
                        'end_line': end_line,
                        'end_character': end_character
                    })

            find_function_calls(node)

    find_function_calls(tree.root_node)
    return calls


def analyze_python_function_calls(code: str, start_lineno: int) -> List[Dict[str, Any]]:
    code = '\n'.join(' ' * 4 + line for line in code.splitlines())
    wrapped_code = f'''\
def wrapper():
{code}
'''

    parser = Parser(language=Language(tree_sitter_python.language()))
    tree = parser.parse(bytes(wrapped_code, "utf8"))
    root_node = tree.root_node

    calls = []

    def traverse(node: Node):
        if node.type == "call":
            function_node = node.child_by_field_name("function")
            if function_node:
                func_name_code = wrapped_code[function_node.start_byte:function_node.end_byte]

                if function_node.type == "attribute":
                    call_type = "method"
                else:
                    # call_type = "function"
                    call_type = "method"

                start_line, start_col = function_node.start_point
                actual_line = start_line - 1 + start_lineno - 1
                actual_col = start_col - 4

                calls.append({
                    "type": call_type,
                    "name": func_name_code,
                    "line": actual_line,
                    "character": actual_col if actual_col >= 0 else 0
                })

        for child in node.children:
            traverse(child)

    for child in root_node.children:
        if child.type == "function_definition":
            for func_child in child.children:
                if func_child.type == "block":
                    for statement in func_child.children:
                        if statement.type != "expression_statement" or len(statement.children) > 0:
                            traverse(statement)

    return calls
