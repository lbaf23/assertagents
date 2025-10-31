import os
import pexpect
import time
import subprocess
import ast


DEBUG_MARK = '__breakpoint__ = True'
DEBUG_BREAKPOINT = 'breakpoint()'


class TryAwareLineAnalyzer(ast.NodeVisitor):
    def __init__(self, target_line: int):
        self.target_line = target_line
        self.parents = []
        self.result = None

    def visit(self, node):
        self.parents.append(node)
        super().visit(node)
        self.parents.pop()

    def generic_visit(self, node):
        if hasattr(node, "lineno") and node.lineno == self.target_line and self.result is None:
            in_except = any(type(p) in {ast.ExceptHandler, ast.Try} for p in self.parents)
            if in_except:
                try_nodes = [p for p in self.parents if isinstance(p, ast.Try)]
                if try_nodes:
                    try_lineno = try_nodes[-1].lineno
                    self.result = max(try_lineno - 1, 1)
                else:
                    self.result = 1
            else:
                self.result = self.target_line
        super().generic_visit(node)


def find_breakpoint_insertion_line(source: str, line_no: int) -> int:
    tree = ast.parse(source)
    analyzer = TryAwareLineAnalyzer(line_no)
    analyzer.visit(tree)
    return analyzer.result if analyzer.result is not None else line_no


def insert_breakpoint(code: str, lineno: int) -> str:
    lines = code.splitlines()
    lsps = min([len(l) - len(l.lstrip()) for l in lines if l.strip() != ''])
    lines = [l[lsps:] for l in lines]
    code = '\n'.join(lines)
    ilineno = find_breakpoint_insertion_line(code, lineno)
    if ilineno == lineno:
        sps = lines[lineno - 1][ : len(lines[lineno - 1]) - len(lines[lineno - 1].lstrip())]
        ret_lines = lines[ : lineno - 1] + [sps + DEBUG_BREAKPOINT] + lines[lineno : ]
    else:
        assert ilineno < lineno
        sps1 = lines[ilineno - 1][ : len(lines[ilineno - 1]) - len(lines[ilineno - 1].lstrip())]
        # sps2 = lines[lineno - 1][ : len(lines[lineno - 1]) - len(lines[lineno - 1].lstrip())]
        ret_lines = lines[ : ilineno] + [sps1 + DEBUG_BREAKPOINT] + lines[ilineno : ]

    ret_lines = [lsps * ' ' + l for l in ret_lines]
    return '\n'.join(ret_lines)




"""

source .venv/bin/activate

python -m pdb \
-c "b tests/test_messages.py:255" \
-c "c" \
-m pytest tests/test_messages.py::test_streaming_chunk_full_message_id -s


pytest --pdb -c 'b tests/animations/test_disabling_animations.py:158' -c 'c' -m pytest -n0 tests/animations/test_disabling_animations.py::test_style_animations_via_transition_are_disabled_on_none -s


pytest --trace -s --capture=no --pdbcls=IPython.terminal.debugger:TerminalPdb \
tests/animations/test_disabling_animations.py::test_style_animations_via_transition_are_disabled_on_none


pytest --trace -s tests/animations/test_disabling_animations.py::test_style_animations_via_transition_are_disabled_on_none
b tests/animations/test_disabling_animations.py:158


b test_messages.py:250
"""

class PythonDebugger:
    def __init__(
            self,
            repo_path: str,
            debug_repo_path: str,
            test_file_path: str,

            test_target: str,
            lineno: int,
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.debug_repo_path = os.path.abspath(debug_repo_path)

        self.test_file_path = test_file_path
        self.test_target = test_target
        self.lineno = lineno

        self.started = False

        for i in range(1):
            try:
                self.start()
                self.started = True
                break
            except Exception:
                self.close()
                print('Retry start Python debugger...')
                time.sleep(0.2)

    def _check_xdist_support(self) -> str:
        cmd = '''\
source .venv/bin/activate
if python -c "import xdist" &>/dev/null; then
    echo "-n0"
else
    echo ""
fi
'''
        res = subprocess.Popen(
            cmd,
            shell=True,
            text=True,
            cwd=self.repo_path,
            executable='/bin/bash',
            stdout=subprocess.PIPE
        )
        return res.stdout.read().strip()

    def start(self):
        # cmd = (
        #     "source .venv/bin/activate && "
        #     f"cd {self.debug_repo_path} && "
        #     "python -m pdb "
        #     f"-c 'b {self.test_file_path}:{self.lineno}' "
        #     "-c 'c' "
        #     f"-m pytest {self._check_xdist_support()} {self.test_target} -s"
        # )
        xd_arg = self._check_xdist_support()
        # cmd = (
        #     "source .venv/bin/activate && "
        #     f"cd {self.debug_repo_path} && "
        #     "export IPY_TEST_SIMPLE_PROMPT=1 && "
        #     f"pytest --capture=no --trace -s {xd_arg} --pdbcls=IPython.terminal.debugger:TerminalPdb {self.test_target}"
        # )
        cmd = (
            "source .venv/bin/activate && "
            f"cd {self.debug_repo_path} && "
            "export IPY_TEST_SIMPLE_PROMPT=1 && "
            f"PYTHONUNBUFFERED=1 pytest --capture=no -s {xd_arg} --pdbcls=IPython.terminal.debugger:TerminalPdb {self.test_target}"
        )
        print(f'>>> run: {cmd}')
        print(f'>>> start python debugger')
        self.prompt_pattern = 'ipdb>'
        self.pdb_process = pexpect.spawn(
            f'bash -c "{cmd}"',
            encoding='utf-8',
            cwd=self.repo_path,
            timeout=60,
        )
        self.pdb_process.expect(self.prompt_pattern)
        print(self.pdb_process.before)

        # file_name = self.test_file_path.split('/')[-1]
        # cmd = f'b {file_name}:{self.lineno}'
        # print(f'>>> run: {cmd}')
        # self.pdb_process.sendline(cmd)
        # self.pdb_process.expect(self.prompt_pattern)
        #
        # print(self.pdb_process.before)
        #
        # print(f'>>> run: c')
        # self.pdb_process.sendline('c')
        # self.pdb_process.expect(self.prompt_pattern)
        #
        # print(self.pdb_process.before)

        print('>>> ready')

    def print_locals(self) -> str:
        if self.started:
            self.pdb_process.sendline('locals()')
            self.pdb_process.expect(self.prompt_pattern)
            return self.extract_output(self.pdb_process.before)
        else:
            return ''

    def print_var_or_expr(self, expr: str) -> str:
        if self.started:
            self.pdb_process.sendline(f'''p {expr}''')
            self.pdb_process.expect(self.prompt_pattern)
            return self.extract_output(self.pdb_process.before)
        else:
            return ''

    def extract_output(self, content) -> str:
        return '\n'.join(content.splitlines()[1:])

    def close(self):
        if self.started:
            try:
                self.pdb_process.sendline('q')
                self.pdb_process.close()
            except Exception:
                pass

        self.started = False
