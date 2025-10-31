import shutil
from typing import Annotated, Dict, List, Tuple, Optional
from datetime import datetime

from autogen_core.tools import FunctionTool
import re
import os

from utils import read_file, write_file
from utils.code_file_utils.code_file_utils import replace_code_lines
from utils.java_utils.java_file_utils import get_lineno
from utils.java_utils.java_debugger import JavaDebugger, DEBUG_MARK
from utils.java_utils.java_tester import run_java_repo_test
from utils.java_utils.java_assert import check_assert_code

from .project_tools import ProjectTools


class JavaProjectTools(ProjectTools):
    def __init__(
            self,
            data: Dict,
            debug_port: int,
            debug_cache_dir: str
    ) -> None:
        """

        Args:
            data (Dict[str, Any]):
                keys:
                    repo_path: repo path in file system, include sub repo
                    sub_repo:

                    test_class: pkg
                    test_method:

                    focal_method:
                    focal_method_start_lineno:
                    focal_method_end_lineno:
                    focal_method_pkg:
                    focal_method_path:

                    test_setup_list:
                        test_setup:
                        start_lineno:
                        end_lineno:

                    test_setup:
                    test_setup_pkg:
                    test_setup_path:

                    test_prefix:
                    test_prefix_start_lineno:
                    test_prefix_end_lineno:
                    test_prefix_pkg:
                    test_prefix_path:

                    placeholder:
                    lang:

                    resource_file:
                    gen_id: n
        """
        self.data = data
        self.check_cache: Dict[str, Tuple] = {}
        self.run_test_cache: Dict[str, Tuple] = {}
        self.debug_value_cache: Dict[str, str] = {}

        self.original_test_prefix_file_content = read_file(self.data['test_prefix_path'])
        self.original_test_prefix_file_content = self.clean_content(self.original_test_prefix_file_content)

        self.masked_test_prefix_file_content = replace_code_lines(
            self.original_test_prefix_file_content,
            code=self.data['test_prefix'],
            start_lineno=self.data['test_prefix_start_lineno'],
            end_lineno=self.data['test_prefix_end_lineno'],
        )
        write_file(self.data['test_prefix_path'], self.masked_test_prefix_file_content)

        self.debug_port = debug_port
        self.debug_cache_dir = debug_cache_dir

        self.java_debugger: Optional[JavaDebugger] = None
        self.debugger_started = False

        self.local_vars = None

        print('=== All Started ===')

    def clean_content(self, content: str):
        return re.sub(r'[\u2028\u2029]', '', content)

    def start_debugger(self):
        if not self.debugger_started:
            # copy to tmp dir
            os.makedirs(self.debug_cache_dir, exist_ok=True)
            self.debug_repo_path = os.path.join(self.debug_cache_dir, self.data['repo_name'])
            if os.path.exists(self.debug_repo_path):
                shutil.rmtree(self.debug_repo_path, ignore_errors=True)
            shutil.copytree(self.data['repo_path'], self.debug_repo_path, dirs_exist_ok=True)

            self.debug_test_prefix_file_content = self.masked_test_prefix_file_content.replace(self.data['placeholder'], DEBUG_MARK)
            write_file(
                os.path.join(self.debug_repo_path, self.data['test_prefix_file_path']),
                self.debug_test_prefix_file_content
            )

            breakpoint_lineno = get_lineno(self.data['test_prefix'], self.data['placeholder'], self.data['test_prefix_start_lineno'])
            self.java_debugger = JavaDebugger(
                repo_path=self.debug_repo_path,
                sub_repo=self.data['test_prefix_sub_repo'],
                test_class=self.data['test_class'],
                test_target=self.data['test_target'],
                lineno=breakpoint_lineno,
                debug_port=self.debug_port,
            )
            self.debugger_started = True

    def close_debugger(self):
        if self.debugger_started:
            self.java_debugger.close()
            self.debugger_started = False
            self.java_debugger = None
            shutil.rmtree(self.debug_repo_path, ignore_errors=True)

    def handle_test_prefix_file(self, file_path: str, file_content: str) -> str:
        if file_path == self.data['test_prefix_path']:
            return file_content.replace(DEBUG_MARK, self.data['placeholder'])
        return file_content


    ### Tools Started ###
    async def get_locals(self) -> str:
        if self.local_vars is None:
            self.local_vars = self.java_debugger.print_locals()
        return self.local_vars

    async def get_debug_value(
            self,
            var_or_expr: Annotated[str, "The variable name or an expression."],
    ) -> str:
        if not self.debug_value_cache.__contains__(var_or_expr):
            v = self.java_debugger.print_var_or_expr(var_or_expr)
            self.debug_value_cache[var_or_expr] = v
        return self.debug_value_cache[var_or_expr]

    async def get_debug_values(
            self,
            var_or_expr_list: Annotated[str, "The list variable names or expressions seperated by comma, for example: var1, var2 ..."],
    ) -> str:
        var_or_expr_list = var_or_expr_list.split(',')
        var_or_expr_list = [v.strip() for v in var_or_expr_list if v.strip() != '']
        res = []
        for var_or_expr in var_or_expr_list:
            if not self.debug_value_cache.__contains__(var_or_expr):
                v = self.java_debugger.print_var_or_expr(var_or_expr)
                self.debug_value_cache[var_or_expr] = v

            r = self.java_debugger.print_var_or_expr(self.debug_value_cache[var_or_expr])
            res.append(r)
        return '\n'.join(res)

    # async def get_file_content(
    #         self,
    #         file_path: Annotated[str, "The path of the file in the current repository."]
    # ) -> str:
    #     file_real_path = os.path.join(self.data['repo_root_path'], file_path)
    #     if not os.path.exists(file_real_path):
    #         return f'''File "{file_path}" not found in the current repository.'''
    #     return read_file(file_real_path)

    # async def get_file_skeleton(
    #         self,
    #         file_path: Annotated[str, "The path of the file in the current repository."]
    # ) -> str:
    #     file_path = file_path.replace('"', '').replace("'", '').replace('`', '')
    #     file_real_path = os.path.join(self.data['repo_root_path'], file_path)
    #     if not os.path.exists(file_real_path):
    #         return f'''File "{file_path}" not found in the current repository.'''
    #     file_content = read_file(file_real_path)
    #     file_skeleton = fold_java_function_body(file_content)
    #     return f'''File path: "{file_path}"\nSkeleton:\n{file_skeleton}'''
    #
    # async def get_function_body(
    #         self,
    #         file_path: Annotated[str, "The path of the file containing the function in the current repository."],
    #         function_name: Annotated[str, "The name of the function."],
    # ) -> str:
    #     file_path = file_path.replace('"', '').replace("'", '').replace('`', '')
    #     file_real_path = os.path.join(self.data['repo_root_path'], file_path)
    #     if not os.path.exists(file_real_path):
    #         return f'''File "{file_path}" not found in the current repository.'''
    #     file_content = read_file(file_real_path)
    #     function_body = get_java_function_body(file_content, function_name)
    #     return f'''File path: "{file_path}"\nFunction body:\n...\n{function_body}\n...\n'''

    # async def find_dependency_source(
    #         self,
    #         file_path: Annotated[str, "The path of the file containing the type in the current repository."],
    #         type_name: Annotated[str, "The type name you want to find."],
    # ) -> str:
    #     # TODO
    #     file_path = file_path.replace('"', '').replace("'", '').replace('`', '')
    #     file_real_path = os.path.join(self.data['repo_root_path'], file_path)
    #     if not os.path.exists(file_real_path):
    #         return f'''File "{file_path}" not found in the current repository.'''
    #     file_content = read_file(file_real_path)
    #     if type_name.__contains__('.'):
    #         type_name = type_name.split('.')[-1]
    #
    #     source_root = self.data['source_root']
    #     try:
    #         tree = javalang.parse.parse(file_content)
    #     except Exception:
    #         return f'''Java file parse failed.'''
    #
    #     # === package ===#
    #     current_package = ''
    #     if hasattr(tree, 'package'):
    #         current_package = tree.package.name
    #
    #     # === import ===#
    #     imports = []
    #     if hasattr(tree, 'imports'):
    #         for imp in tree.imports:
    #             imports.append({
    #                 'path': imp.path,
    #                 'static': imp.static,
    #                 'wildcard': imp.wildcard
    #             })
    #
    #     # === Step 2: check java.lang ===
    #     builtin_types = {"String", "Object", "Integer", "Boolean", "Character", "Double", "Float", "Long", "Short",
    #                      "Byte", "Math"}
    #     if type_name in builtin_types:
    #         return f'''Builtin type: java.lang.{type_name}'''
    #
    #     # === Step 3: check import ===
    #     matched_import_list = []
    #     for imp in imports:
    #         if not imp['wildcard']:
    #             simple_name = imp['path'].split('.')[-1]
    #             if simple_name == type_name:
    #                 matched_import_list = [imp['path']]
    #                 break
    #         else:
    #             # import com.example.*;
    #             base = imp['path'].rstrip('.*')
    #             candidate = f'{base}.{type_name}'
    #             matched_import_list.append(candidate)
    #
    #     # === maybe current package ===#
    #     if len(matched_import_list) == 0 and current_package != '':
    #         matched_import_list = [current_package + '.' + type_name]
    #
    #     # === import ===
    #     if len(matched_import_list) > 0:
    #         for matched_import in matched_import_list:
    #             rel_path = matched_import.replace('.', os.sep) + '.java'
    #             for base in source_root:
    #                 import_path = os.path.join(base, rel_path)
    #                 import_real_path = os.path.join(self.data['repo_path'], self.data['sub_repo'], import_path)
    #                 if os.path.exists(import_real_path):
    #                     file_content = read_file(import_real_path)
    #                     dep = fold_java_function(file_content)
    #                     return f'''File path: {import_path}\nSkeleton:\n{file_skeleton}'''
    #         return f'''Type `{type_name}` not found in the current repo.'''
    #
    #     return f'''Type `{type_name}` not found in the current repo.'''


    async def static_check_assert(
            self,
            assert_code: Annotated[str, "The generated assert statement."]
    ) -> Tuple:
        if not self.check_cache.__contains__(assert_code):
            passed, check_result = check_assert_code(
                assert_code=assert_code,
                test_prefix=self.data['test_prefix'],
                test_prefix_start_lineno=self.data['test_prefix_start_lineno'],
                placeholder=self.data['placeholder'],
            )
            self.check_cache[assert_code] = (passed, check_result)
        return self.check_cache[assert_code]

    async def run_test(
            self,
            assert_code: Annotated[str, "The generated assert statement."]
    ) -> Tuple:
        """
        Tool: run_test
        Args:
            assert_code:

        Returns:

        """
        if self.run_test_cache.__contains__(assert_code):
            return self.run_test_cache[assert_code]

        self.run_test_prefix_file_content = self.masked_test_prefix_file_content.replace(self.data['placeholder'], assert_code)
        write_file(self.data['test_prefix_path'], self.run_test_prefix_file_content)

        start_t = datetime.now()
        res, test_run_result = run_java_repo_test(
            repo_path=self.data['repo_path'],
            sub_repo=self.data['test_prefix_sub_repo'],
            test_class=self.data['test_prefix_pkg'],
            test_target=self.data['test_target'],
        )
        passed = res['score'] == 1.0
        end_t = datetime.now()
        seconds = (end_t - start_t).total_seconds()

        write_file(self.data['test_prefix_path'], self.masked_test_prefix_file_content)

        self.run_test_cache[assert_code] = (passed, test_run_result, 0)
        return passed, test_run_result, seconds

    ### Tools Ended ###
    def close(self):
        self.close_debugger()
        write_file(self.data['test_prefix_path'], self.original_test_prefix_file_content)


def get_java_project_tools(
        data: Dict,
        debug_port: int,
        debug_cache_dir: str,
) -> Tuple[JavaProjectTools, Dict[str, FunctionTool]]:
    java_project_tools = JavaProjectTools(
        data=data,
        debug_port=debug_port,
        debug_cache_dir=debug_cache_dir
    )
    return java_project_tools, {
        'run_test': FunctionTool(
            java_project_tools.run_test,
            description=(
                'Put the generated assert statement into the unit test and run it. '
                'It may take some time, but can provide accurate running results.'
            )
        ),
        # 'get_file_skeleton': FunctionTool(
        #     java_project_tools.get_file_skeleton,
        #     description=(
        #         '''Get the preview of a file's content, includes the imports, class definitions and all function definitions.'''
        #     )
        # ),
        # 'get_function_body': FunctionTool(
        #     java_project_tools.get_function_body,
        #     description=(
        #         'Returns the function body in a file. '
        #         'You should first call `get_file_skeleton` to see which functions are in this file, and then get the content of the function body.'
        #     )
        # ),
        # 'get_file_content': FunctionTool(
        #     java_project_tools.get_file_content,
        #     description=(
        #         'Returns the entire content of a file.'
        #     )
        # ),
        # 'find_dependency_source': FunctionTool(
        #     java_project_tools.find_dependency_source,
        #     description=(
        #         'Returns the definition source of a certain type used in the file.'
        #     )
        # ),
        'get_locals': FunctionTool(
            java_project_tools.get_locals,
            description=(
                'Started a debugger that paused at the current line, and returned a snapshot of all current local variables.'
            )
        ),
        'get_debug_value': FunctionTool(
            java_project_tools.get_debug_value,
            description=(
                'A startup debugger pauses at the line where the assert statement needs to be generated, '
                'and this tool can query the value of a variable or an expression within the test function at that time.'
            )
        ),
        'get_debug_values': FunctionTool(
            java_project_tools.get_debug_values,
            description=(
                'A startup debugger pauses at the line where the assert statement needs to be generated, '
                'and this tool can query the values of variables or expressions only within the test function at that time.'
            )
        )
    }
