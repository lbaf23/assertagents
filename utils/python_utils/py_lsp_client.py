import subprocess
import os
import time
import re
import json
import threading
from typing import List, Dict, Optional
from urllib.parse import urlparse, unquote
from pathlib import Path

from utils.lsp_client import LSPClient


def is_subpath(path, base):
    try:
        Path(path).resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False


def uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Not a file URI: {uri}")
    path = unquote(parsed.path)
    # win
    if os.name == "nt" and path.startswith("/"):
        path = path[1:]
    return path


class PyLSPClient(LSPClient):
    def __init__(
            self,
            pyright_executable_path: Optional[str],
            repo_path: str,
            # python_path: str,
    ):
        self.pyright_executable = pyright_executable_path or 'pyright-langserver'
        self.repo_path = os.path.abspath(repo_path)
        self.repo_uri = Path(self.repo_path).as_uri()

        # self.python_path = os.path.abspath(python_path)

        self.process = None
        self.msg_id = 0
        self.responses: Dict[int, Dict] = {}
        self.notifications: List[Dict] = []
        self.reader_thread = None
        self.running = False

        self._analysis_in_progress = False

    def _get_next_id(self) -> int:
        self.msg_id += 1
        return self.msg_id

    def start_server(self):
        """
        Starts the pyright-langserver process.
        """
        cmd = [
            self.pyright_executable,
            "--stdio",
            "--project", self.repo_path
        ]

        print(f"Starting Pyright with command: {' '.join(cmd)}")

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )

        self.running = True
        self.reader_thread = threading.Thread(target=self._read_responses, daemon=True)
        self.reader_thread.start()

        time.sleep(1)  # Give the server a moment to start up

        self._initialize()
        self.wait_for_index_ready()  # Pyright calls it "analysis"

        time.sleep(1)

    def wait_for_index_ready(self, timeout: int = 30):
        """
        Waits for Pyright to finish its initial analysis of the workspace.
        """
        print("Waiting for Pyright to finish analysis...")
        start_time = time.time()

        # We wait until an analysis starts and then finishes.
        analysis_started = False
        analysis_finished = False

        while time.time() - start_time < timeout:
            while self.notifications:
                notif = self.notifications.pop(0)

                # Pyright uses the standard $/progress notification for analysis status
                if notif.get("method") == "$/progress":
                    value = notif.get("params", {}).get("value", {})
                    kind = value.get("kind")

                    if kind == "begin":
                        title = value.get("title", "")
                        if "Analyzing" in title:
                            print(f"Pyright analysis started: {value.get('message', '')}")
                            analysis_started = True
                    elif kind == "end":
                        # If we've seen a "begin" message, any "end" message signifies completion.
                        if analysis_started:
                            print("Pyright analysis complete.")
                            analysis_finished = True
                            break

            if analysis_finished:
                break

            # Fallback for very fast analysis where we might miss the notifications
            if analysis_started is False and time.time() - start_time > 5:
                print("No analysis start notification received, assuming it's complete.")
                break

            time.sleep(1)

        if not analysis_finished and analysis_started:
            print("Error: Timed out waiting for Pyright analysis to finish")

    def wait_for_file_open_ready(self, uri: str, timeout: int = 120):
        """
        Waits for diagnostics to be published for a newly opened file.
        """
        print(f"Waiting for diagnostics for {uri}")
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check notifications in a thread-safe way
            current_notifications = self.notifications[:]
            self.notifications = []

            for notif in current_notifications:
                if notif.get("method") == "textDocument/publishDiagnostics":
                    diag_uri = notif["params"].get("uri", "")
                    if uri == diag_uri:
                        print(f"Diagnostics received for {uri}. File is ready.")
                        return
                else:
                    # Put back unhandled notifications
                    self.notifications.append(notif)
            time.sleep(0.5)

        print(f"Error: Timed out waiting for {uri} to be ready.")

    def _read_responses(self):
        while self.running:
            try:
                response = self._read_message()
                if response:
                    # print(response)
                    if 'id' in response:
                        msg_id = response['id']
                        self.responses[msg_id] = response
                    else:
                        self.notifications.append(response)
            except Exception as e:
                if self.running:
                    print(f"Error reading response: {e}")
                    # Log stderr for debugging if process has exited
                    if self.process and self.process.poll() is not None:
                        stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore')
                        if stderr_output:
                            print(f"Pyright stderr:\n{stderr_output}")
                break

    def _send_request(self, method: str, params: Dict, timeout: int = 360) -> Dict:
        msg_id = self._get_next_id()
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params
        }

        self._write_message(request)

        start_time = time.time()
        while time.time() - start_time < timeout:
            if msg_id in self.responses:
                response = self.responses.pop(msg_id)
                if 'error' in response:
                    print(f"LSP Error: {response['error']}")
                return response
            time.sleep(0.1)

        raise TimeoutError(f"Request {method} timed out after {timeout} seconds")

    def _send_notification(self, method: str, params: Dict):
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        self._write_message(notification)

    def _write_message(self, message: Dict):
        content = json.dumps(message)
        header = f"Content-Length: {len(content.encode('utf-8'))}\r\n\r\n"
        full_message = header + content
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(full_message.encode('utf-8'))
                self.process.stdin.flush()
            except BrokenPipeError:
                print("Error: Cannot write to LSP server. The process may have terminated.")
                self.running = False

    def _read_message(self) -> Optional[Dict]:
        headers = {}
        # read headers
        while True:
            line = self.process.stdout.readline()
            if not line:
                return None
            line = line.decode('utf-8').strip()
            if not line:
                break
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip()] = value.strip()

        content_length = int(headers.get('Content-Length', 0))
        if content_length == 0:
            return None

        # read body
        content = bytearray()
        remaining = content_length
        while remaining > 0:
            chunk = self.process.stdout.read(remaining)
            if not chunk:
                break
            content.extend(chunk)
            remaining -= len(chunk)

        # JSON
        try:
            return json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            print("JSON decode error:", e)
            snippet = content[:500].decode('utf-8', errors='replace')
            print("Partial content sample:", snippet)
            return None

    def _initialize(self):
        params = {
            "processId": os.getpid(),
            "rootUri": self.repo_uri,
            "capabilities": {
                "textDocument": {
                    "references": {"dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True, "linkSupport": True}
                }
            },
            # "initializationOptions": {
            #     "python": {
            #         "pythonPath": self.python_path
            #     }
            # },
            # Pyright needs workspace folders to work correctly with multi-root workspaces
            "workspaceFolders": [{
                "uri": self.repo_uri,
                "name": os.path.basename(self.repo_path)
            }]
        }

        response = self._send_request("initialize", params, timeout=360)
        self._send_notification("initialized", {})
        return response

    def open_document(self, file_path: str):
        abs_path = os.path.abspath(file_path)
        uri = Path(abs_path).as_uri()

        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()

        params = {
            "textDocument": {
                "uri": uri,
                "languageId": "python",
                "version": 1,
                "text": content
            }
        }

        self._send_notification("textDocument/didOpen", params)
        self.wait_for_file_open_ready(uri=uri)

    def find_definition(self, rel_file_path: str, line: int, character: int) -> Optional[Dict]:
        abs_path = os.path.abspath(os.path.join(self.repo_path, rel_file_path))
        uri = Path(abs_path).as_uri()
        print(f'>>> Find def: {uri}, ({line}, {character})')
        params = {
            'textDocument': {'uri': uri},
            'position': {'line': line, 'character': character}
        }
        try:
            response = self._send_request('textDocument/definition', params, timeout=30)
            result = response.get('result')
            assert result is not None and len(result) > 0, 'no definition.'
            def_path = uri_to_path(result[0]['uri'])
            assert is_subpath(def_path, self.repo_path), 'not in the current repo.'
            return {
                # 'file_path': def_path,
                'rel_file_path': os.path.relpath(def_path, self.repo_path),
                'start_line': result[0]['range']['start']['line'],
                'start_character': result[0]['range']['start']['character'],
                'end_line': result[0]['range']['end']['line'],
                'end_character': result[0]['range']['end']['character']
            }
        except Exception as e:
            print(f"Error finding definition: {e}")
            return None

    def find_references(self, rel_file_path: str, line: int, character: int) -> List[Dict]:
        abs_path = os.path.abspath(os.path.join(self.repo_path, rel_file_path))
        uri = Path(abs_path).as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": False}
        }
        try:
            response = self._send_request('textDocument/references', params, timeout=360)
            result = response.get('result')
            assert result is not None, 'no references.'
            ret = []
            for res in result:
                ref_path = uri_to_path(res['uri'])
                ret.append({
                    'index': len(ret),
                    # 'file_path': ref_path,
                    'rel_file_path': os.path.relpath(ref_path, self.repo_path),
                    'lineno': res['range']['start']['line'] + 1,
                    'start_line': res['range']['start']['line'],
                    'start_character': res['range']['start']['character'],
                    'end_line': res['range']['end']['line'],
                    'end_character': res['range']['end']['character']
                })
            return ret
        except Exception as e:
            print(f"Error finding references: {e}")
            return []

    def _find_function_definition_line(self, lines: List[str], start_line: int, function_name: str) -> tuple:
        """Finds the line number and character position of a Python function definition."""
        # Pattern to match 'def function_name(...):'
        # pattern = re.compile(r'^\s*def\s+' + re.escape(function_name) + r'\s*\(')

        pattern = re.compile(r'^\s*(async\s+)?(def|class)\s+' + re.escape(function_name))  # + r'\s*\(')
        for i in range(start_line, len(lines)):
            line_content = lines[i]
            match = pattern.search(line_content)
            if match:
                # Find the character position of the function name itself
                char_pos = line_content.find(function_name, match.start())
                return i, char_pos
        return -1, -1

    def _find_function_body_end(self, lines: List[str], start_line: int) -> int:
        """Finds the end of a Python function body based on indentation."""
        if start_line >= len(lines):
            return start_line

        initial_indent_match = re.match(r'^(\s*)', lines[start_line])
        initial_indent = len(initial_indent_match.group(1)) if initial_indent_match else 0

        for i in range(start_line + 1, len(lines)):
            line = lines[i]
            if not line.strip():  # Skip empty lines
                continue

            line_indent_match = re.match(r'^(\s*)', line)
            line_indent = len(line_indent_match.group(1)) if line_indent_match else 0

            if line_indent <= initial_indent:
                return i - 1

        return len(lines) - 1

    def _extract_function_calls_from_body(
            self,
            rel_file_path: str,
            lines: List[str],
            start_line: int,
            end_line: int,
            function_name: str
    ) -> List[Dict]:
        calls = []
        # Python keywords that can look like function calls but aren't (or we want to ignore)
        keywords = {
            'if', 'for', 'while', 'switch', 'catch', 'synchronized', 'return',
            'class', 'def', 'print', 'yield', 'raise', 'with', 'assert', 'del',
            'super', 'self', 'cls'
        }

        # Also ignore built-in type constructors if needed
        builtins = {'int', 'str', 'list', 'dict', 'set', 'tuple', 'float', 'bool'}

        for line_num in range(start_line, end_line + 1):
            line = lines[line_num]

            # Simple check to ignore comments
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue

            # Find patterns like `word(...)`
            matches = re.finditer(r'\b([a-zA-Z_]\w*)\s*\(', line)
            for match in matches:
                call_name = match.group(1)

                # Skip keywords, builtins, and self-recursion
                if call_name in keywords or call_name in builtins or call_name == function_name:
                    continue

                char_pos = match.start(1)
                defs = self.find_definition(rel_file_path, line_num, char_pos)
                # if defs and is_subpath(defs['file_path'], self.repo_path):
                if defs is not None:
                    calls.append({
                        'function': call_name,
                        'file': defs['rel_file_path'],  # os.path.relpath(defs['file_path'], self.repo_path),
                        'lineno': defs['start_line'] + 1,
                        'line': defs['start_line'],
                        'character': defs['start_character'],
                        'call_site': {
                            'file': rel_file_path,
                            'line': line_num,
                            'character': char_pos
                        }
                    })

        # De-duplicate calls to the same function at the same location
        seen = set()
        unique_calls = []
        for call in calls:
            key = (call["function"], call["file"], call["line"])
            if key not in seen:
                seen.add(key)
                unique_calls.append(call)

        for idx, c in enumerate(unique_calls):
            c['index'] = idx

        return unique_calls

    # def analyze_function_calls(
    #         self,
    #         file_path: str,
    #         function_name: str,
    #         start_line: int,
    #         find_calls: bool,
    #         find_called_by: bool
    # ) -> Optional[Dict]:
    #     rel_file_path = os.path.relpath(file_path, self.repo_path)
    #     abs_path = os.path.abspath(file_path)
    # 
    #     print(f"Opening document: {abs_path}")
    #     self.open_document(abs_path)
    # 
    #     with open(abs_path, 'r', encoding='utf-8') as f:
    #         lines = f.readlines()
    # 
    #     start_line_0_indexed = start_line - 1
    #     function_line, function_char = self._find_function_definition_line(lines, start_line_0_indexed, function_name)
    # 
    #     if function_line == -1:
    #         print(f"Function '{function_name}' not found starting from line {start_line} in {file_path}")
    #         return None
    # 
    #     print(f"Found function '{function_name}' at line {function_line + 1}, char {function_char + 1}")
    # 
    #     result = {
    #         "calls": [],
    #         "called_by": []
    #     }
    # 
    #     if find_called_by:
    #         print(f"Finding references for '{function_name}'...")
    #         references = self.find_references(abs_path, function_line, function_char)
    #         if references:
    #             for ref in references:
    #                 if isinstance(ref, dict):
    #                     uri_path = ref.get("uri", "")
    #                     p = uri_to_path(uri_path)
    #                     ref_line = ref["range"]["start"]["line"]
    #                     ref_char = ref["range"]["start"]["character"]
    # 
    #                     result['called_by'].append({
    #                         'index': len(result['called_by']),
    #                         'file': os.path.relpath(p, self.repo_path),
    #                         'lineno': ref_line + 1,
    #                         'line': ref_line,
    #                         'character': ref_char
    #                     })
    #         print(f"Found {len(result['called_by'])} callers")
    # 
    #     if find_calls:
    #         print("Analyzing function body for outgoing calls...")
    #         function_end_line = self._find_function_body_end(lines, function_line)
    #         print(f"Function body spans lines {function_line + 1} to {function_end_line + 1}")
    # 
    #         result["calls"] = self._extract_function_calls_from_body(
    #             rel_file_path, lines, function_line, function_end_line, function_name
    #         )
    # 
    #         print(f"Found {len(result['calls'])} unique function calls")
    # 
    #     return result

    def stop_server(self):
        self.shutdown()

    def shutdown(self):
        print("Shutting down Pyright LSP Client...")
        self.running = False
        if self.process:
            try:
                self._send_request('shutdown', {}, timeout=5)
                self._send_notification('exit', {})
            except (TimeoutError, BrokenPipeError) as e:
                print(f"Could not shut down gracefully: {e}. Terminating process.")

            # Give it a moment, then terminate if it's still alive
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()

        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=2)

        print("Pyright shutdown complete.")
