import ast


def filter_test_functions(code_str: str) -> str:
    try:
        tree = ast.parse(code_str)
    except Exception:
        return code_str

    new_body = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.lower().startswith('test'):
                new_body.append(node)
        else:
            new_body.append(node)

    tree.body = new_body

    new_code = ast.unparse(tree)
    return new_code
