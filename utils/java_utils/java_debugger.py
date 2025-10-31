import os
import subprocess
import pexpect
import time
import psutil
import re
import socket


DEBUG_MARK = 'boolean __breakpoint__ = true;'


class JavaDebugger:
    def __init__(
            self,
            repo_path: str,
            sub_repo: str,
            test_class: str,
            test_target: str,
            lineno: int,
            debug_port: int
    ):
        self.debug_port = int(debug_port)
        self.repo_path = repo_path
        self.sub_repo = sub_repo
        self.test_class = test_class
        self.test_target = test_target
        self.lineno = lineno

        self.cmd_env = ''
        # patch this test
        if repo_path.__contains__('raml-loader') and test_target == 'guru.nidi.loader.basic.GithubTest#publicGithubNotModified':
            self.cmd_env = 'HOME=/Users/nidi'

        # self.prompt_pattern = re.compile(r'\r?\n[A-Za-z0-9\-\s_$.]+?\[\d+\]\s*$')
        self.prompt_pattern = re.compile(r'\r?\n[A-Za-z0-9-_]+\[\d+\]')

        self.started = False

        for i in range(3):
            try:
                self.start()
                self.started = True
                break
            except Exception:
                self.close()
                print('Retry start Java debugger...')
                time.sleep(0.2)

    def start(self):
        self.kill_all_process()

        cmd = f'''{self.cmd_env} mvn compiler:testCompile surefire:test -Dmaven.surefire.debug="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address={self.debug_port}" -o -Dtest="{self.test_target}"'''
        print(f'>>> run: {cmd}')
        self.mvn_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,
            cwd=os.path.join(self.repo_path, self.sub_repo),
        )
        print(f'>>> start mvn debugger at {self.debug_port}')

        assert self.wait_for_port_open()

        cmd = f'jdb -attach {self.debug_port}'
        print(f">>> run: {cmd}")
        self.jdb_process = pexpect.spawn(cmd, encoding='utf-8', timeout=60)
        self.jdb_process.expect(self.prompt_pattern)
        print(self.jdb_process.before)
        print('>>> jdb process is running')

        stop_line = f'''stop at {self.test_class}:{self.lineno}'''
        print(f'>>> run: {stop_line}')
        self.jdb_process.sendline(stop_line)
        self.jdb_process.expect(self.prompt_pattern)

        print('>>> run: run')
        self.jdb_process.sendline('run')
        self.jdb_process.expect(self.prompt_pattern)

        print('>>> ready')

    def wait_for_mvn_debugger(self, timeout: int = 30):
        start = time.time()
        for line in self.mvn_process.stdout:
            # print(line, end="")
            if "Listening for transport dt_socket" in line:
                print('>>> mvn debugger is running')
                break

    def wait_for_port_open(self, timeout: int = 60) -> bool:
        print('>>> waiting for mvn debugger port open.')
        start = time.time()
        while time.time() - start < timeout:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            try:
                s.connect(('localhost', self.debug_port))
                s.close()
                print('>>> mvn debugger port is available.')
                time.sleep(0.2)
                return True
            except (ConnectionRefusedError, OSError):
                time.sleep(0.2)
            finally:
                s.close()
        print(f'>>> timeout waiting for mvn debugger!')
        return False

    def print_locals(self) -> str:
        if self.started:
            self.jdb_process.sendline('locals')
            self.jdb_process.expect(self.prompt_pattern)
            return self.extract_output(self.jdb_process.before)
        else:
            return ''

    def print_var_or_expr(self, expr: str) -> str:
        if self.started:
            self.jdb_process.sendline(f'''print {expr}''')
            self.jdb_process.expect(self.prompt_pattern)
            return self.extract_output(self.jdb_process.before)
        else:
            return ''

    def extract_output(self, content) -> str:
        return '\n'.join(content.splitlines()[1:])

    def get_pids_by_port(self):
        pids = set()
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr and conn.laddr.port == self.debug_port and conn.pid:
                pids.add(conn.pid)
        return list(pids)

    def kill_all_process(self):
        while True:
            pids = self.get_pids_by_port()
            if not pids:
                break
            for pid in pids:
                try:
                    p = psutil.Process(pid)
                    print(f'Killing PID {pid} ({p.name()})')
                    p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            time.sleep(0.2)


    def close(self):
        if self.started:
            self.jdb_process.sendline('exit')
            self.jdb_process.wait()
            self.jdb_process.close()

        try:
            self.mvn_process.kill()
        except Exception:
            pass

        self.kill_all_process()
        self.started = False
