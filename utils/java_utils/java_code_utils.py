from typing import Optional, Tuple
from tree_sitter import Language, Parser
import tree_sitter_java


def get_java_method_name_pos(method_code: str, start_lineno: int) -> Optional[Tuple]:
    java_lang = Language(tree_sitter_java.language())
    parser = Parser()
    parser.language = java_lang
    code_bytes = bytes(method_code, 'utf-8')
    tree = parser.parse(code_bytes)
    for node in tree.root_node.children:
        if node.type == 'method_declaration':
            for child in node.children:
                if child.type == 'identifier':
                    line = child.start_point[0]
                    character = child.start_point[1]
                    return (line + start_lineno - 1, character)
    return None
