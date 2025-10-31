import shutil
from typing import Annotated, Dict, List, Tuple, Optional
from datetime import datetime

from autogen_core.tools import FunctionTool
import os

from utils import read_file, write_file
from utils.code_file_utils.code_file_utils import replace_code_lines
from utils.python_utils.python_debugger import PythonDebugger, insert_breakpoint
from utils.python_utils.python_tester import run_py_repo_test
from utils.python_utils.python_assert import check_assert_code

from .project_tools import ProjectTools


def ignore_dirs(dir, files):
    ignore_list = []
    for f in files:
        if f in {'.venv'}:
            ignore_list.append(f)
    return ignore_list


class PythonProjectTools(ProjectTools):
    def __init__(
            self,
            data: Dict,
            debug_cache_dir: str
    ) -> None:
        """

        Args:
            data (Dict[str, Any]):
                keys:
                    repo_path: repo path in file system

                    focal_method:
                    focal_method_start_lineno:
                    focal_method_end_lineno:
                    focal_method_path:


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

        self.test_file_cache = []

        self.original_test_prefix_file_content = read_file(self.data['test_prefix_path'])

        self.masked_test_prefix_file_content = replace_code_lines(
            self.original_test_prefix_file_content,
            code=self.data['test_prefix'],
            start_lineno=self.data['test_prefix_start_lineno'],
            end_lineno=self.data['test_prefix_end_lineno'],
        )
        write_file(self.data['test_prefix_path'], self.masked_test_prefix_file_content)

        self.debug_cache_dir = debug_cache_dir

        self.python_debugger: Optional[PythonDebugger] = None
        self.debugger_started = False

        self.local_vars = None

        print('=== All Started ===')

    def start_debugger(self):
        if not self.debugger_started:
            # copy to tmp dir
            os.makedirs(self.debug_cache_dir, exist_ok=True)
            self.debug_repo_path = os.path.join(self.debug_cache_dir, self.data['repo_name'])
            if os.path.exists(self.debug_repo_path):
                shutil.rmtree(self.debug_repo_path, ignore_errors=True)
            shutil.copytree(self.data['repo_path'], self.debug_repo_path, dirs_exist_ok=True, ignore=ignore_dirs)

            debug_test_prefix = insert_breakpoint(
                self.data['test_prefix'],
                self.data['ground_truth_oracle_lineno'] - self.data['test_prefix_start_lineno'] + 1,
            )
            self.debug_test_prefix_file_content = replace_code_lines(
                self.original_test_prefix_file_content,
                code=debug_test_prefix,
                start_lineno=self.data['test_prefix_start_lineno'],
                end_lineno=self.data['test_prefix_end_lineno'],
            )
            write_file(
                os.path.join(self.debug_repo_path, self.data['test_prefix_file_path']),
                self.debug_test_prefix_file_content
            )

            self.python_debugger = PythonDebugger(
                repo_path=self.data['repo_path'],
                debug_repo_path=self.debug_repo_path,
                test_file_path=self.data['test_prefix_file_path'],
                test_target=self.data['test_target'],
                lineno=self.data['ground_truth_oracle_lineno'],
            )
            self.debugger_started = True

    def close_debugger(self):
        if self.debugger_started:
            self.python_debugger.close()
            self.debugger_started = False
            self.python_debugger = None
            shutil.rmtree(self.debug_repo_path, ignore_errors=True)

    def handle_test_prefix_file(self, file_path: str, file_content: str) -> str:
        if file_path == self.data['test_prefix_path']:
            return file_content.replace(DEBUG_MARK, self.data['placeholder'])
        return file_content


    ### Tools Started ###
    async def get_locals(self) -> str:
        if self.local_vars is None:
            v = self.python_debugger.print_locals()
            if len(v) > 1024:
                v = v[:1024] + '...'
            self.local_vars = v
        return self.local_vars

    async def get_debug_value(
            self,
            var_or_expr: Annotated[str, "The variable name or an expression."],
    ) -> str:
        value = self.python_debugger.print_var_or_expr(var_or_expr)
        if len(value) > 1024:
            value = value[:1024] + '...'
        return value

    async def get_debug_values(
            self,
            var_or_expr_list: Annotated[str, "The list variable names or expressions seperated by comma, for example: var1, var2 ..."],
    ) -> str:
        var_or_expr_list = var_or_expr_list.split(',')
        var_or_expr_list = [v.strip() for v in var_or_expr_list if v.strip() != '']
        res = []
        for v in var_or_expr_list:
            if len(v) > 1024:
                v = v[:1024] + '...'
            r = self.python_debugger.print_var_or_expr(v)
            res.append(r)
        return '\n'.join(res)

    async def static_check_assert(
            self,
            assert_code: Annotated[str, "The generated assert statement."]
    ) -> Tuple:
        if self.check_cache.__contains__(assert_code):
            return self.check_cache[assert_code]
        passed, check_result = check_assert_code(
            assert_code=assert_code,
            test_prefix=self.data['test_prefix'],
            test_prefix_start_lineno=self.data['test_prefix_start_lineno'],
            placeholder=self.data['placeholder'],
        )
        self.check_cache[assert_code] = (passed, check_result)
        return passed, check_result

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
        res, test_run_result = run_py_repo_test(
            repo_path=self.data['repo_path'],
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


def get_python_project_tools(
        data: Dict,
        debug_cache_dir: str,
) -> Tuple[PythonProjectTools, Dict[str, FunctionTool]]:
    python_project_tools = PythonProjectTools(
        data=data,
        debug_cache_dir=debug_cache_dir
    )
    return python_project_tools, {
        'run_test': FunctionTool(
            python_project_tools.run_test,
            description=(
                'Put the generated assert statement into the unit test and run it. '
                'It may take some time, but can provide accurate running results.'
            )
        ),
        'get_locals': FunctionTool(
            python_project_tools.get_locals,
            description=(
                'Started a debugger that paused at the current line, and returned a snapshot of all current local variables.'
            )
        ),
        'get_debug_value': FunctionTool(
            python_project_tools.get_debug_value,
            description=(
                'A startup debugger pauses at the line where the assert statement needs to be generated, '
                'and this tool can query the value of a variable or an expression within the test function at that time.'
            )
        ),
        'get_debug_values': FunctionTool(
            python_project_tools.get_debug_values,
            description=(
                'A startup debugger pauses at the line where the assert statement needs to be generated, '
                'and this tool can query the values of variables or expressions only within the test function at that time.'
            )
        )
    }
