import subprocess
import os
import time
import re
import json
import threading
from typing import List, Dict, Optional

from utils.lsp_client import LSPClient
from pathlib import Path
from urllib.parse import urlparse, unquote


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


class JavaLSPClient(LSPClient):
    def __init__(self, jdtls_path: str, workspace_path: str, repo_path: str):
        self.jdtls_path = jdtls_path
        self.workspace_path = os.path.abspath(workspace_path)
        self.process = None
        self.msg_id = 0
        self.responses = {}
        self.notifications = []
        self.reader_thread = None
        self.running = False

        self.repo_path = os.path.abspath(repo_path)
        self.repo_uri = f'file://{self.repo_path}'

    def _get_next_id(self) -> int:
        self.msg_id += 1
        return self.msg_id

    def start_server(self):
        config_dir = os.path.join(self.workspace_path, '.jdt-config')
        os.makedirs(config_dir, exist_ok=True)

        # find launcher jar
        plugins_dir = os.path.join(self.jdtls_path, 'plugins')
        launcher_jar = None
        for file in os.listdir(plugins_dir):
            if file.startswith('org.eclipse.equinox.launcher_') and file.endswith('.jar'):
                launcher_jar = os.path.join(plugins_dir, file)
                break

        if not launcher_jar:
            raise FileNotFoundError('Could not find equinox launcher jar in plugins directory')

        # find config
        import platform
        system = platform.system().lower()
        if system == 'linux':
            config = 'config_linux'
        elif system == 'darwin':
            config = 'config_mac'
        elif system == 'windows':
            config = 'config_win'
        else:
            config = 'config_linux'

        config_path = os.path.join(self.jdtls_path, config)

        # start jdtls
        cmd = [
            'java',
            '-Declipse.application=org.eclipse.jdt.ls.core.id1',
            '-Dosgi.bundles.defaultStartLevel=4',
            '-Declipse.product=org.eclipse.jdt.ls.core.product',
            '-Dlog.level=ERROR',
            '-Dgradle.disabled=true',  # Use maven only
            '-Xmx1G',
            '-jar', launcher_jar,
            '-configuration', config_path,
            '-data', config_dir
        ]

        print(f'''Starting JDTLS with command: {' '.join(cmd)}''')

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

        time.sleep(1)

        self._initialize()
        self.wait_for_index_ready()

        time.sleep(1)

    def wait_for_index_ready(self, timeout: int = 360):
        print("Waiting for JDTLS to finish indexing...")
        start_time = time.time()
        ready = False

        while time.time() - start_time < timeout:
            while self.notifications:
                notif = self.notifications.pop(0)

                # JDTLS:
                # 1. window/logMessage: ("Building workspace" / "Finished building workspace")
                # 2. language/status: ("ready" or "error")
                if notif.get("method") == "window/logMessage":
                    msg = notif["params"]["message"]
                    if "Finished building workspace" in msg or "finished indexing" in msg:
                        print("JDTLS indexing complete")
                        ready = True
                        break
                    elif "Building workspace" in msg or "Starting indexing" in msg:
                        print(msg)

                elif notif.get("method") == "language/status":
                    msg = notif["params"].get("message", "")
                    if "ready" in msg.lower():
                        print("Language status: ready")
                        ready = True
                        break
                    elif "indexing" in msg.lower():
                        print("Language status:", msg)

            if ready:
                break
            time.sleep(1)

        if not ready:
            print("Erro: Timed out waiting for JDTLS index to finish")

    def wait_for_file_open_ready(self, uri: str, timeout: int = 120):
        print("Waiting for file open")
        start_time = time.time()
        ready = False

        while time.time() - start_time < timeout:
            while self.notifications:
                notif = self.notifications.pop(0)
                # print(f'Waiting for file open: {notif}')
                if notif.get("method") == "textDocument/publishDiagnostics":
                    diag_uri = notif["params"].get("uri", "")
                    if uri == diag_uri:
                        return

            time.sleep(1)

        if not ready:
            print("Erro: Timed out waiting file open")

    def _read_responses(self):
        while self.running:
            try:
                response = self._read_message()
                if response:
                    if 'id' in response:
                        # response for request
                        msg_id = response['id']
                        self.responses[msg_id] = response
                    else:
                        # notification
                        self.notifications.append(response)
            except Exception as e:
                if self.running:
                    print(f"Error reading response: {e}")
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
        header = f"Content-Length: {len(content)}\r\n\r\n"
        full_message = header + content
        self.process.stdin.write(full_message.encode('utf-8'))
        self.process.stdin.flush()

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
            }
        }

        response = self._send_request("initialize", params, timeout=360)
        self._send_notification("initialized", {})
        return response

    def open_document(self, file_path: str):
        abs_path = os.path.abspath(file_path)
        uri = f"file://{abs_path}"

        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()

        params = {
            "textDocument": {
                "uri": uri,
                "languageId": "java",
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
            assert result is not None and len(result) > 0
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
        for i in range(start_line, min(start_line + 20, len(lines))):
            line = lines[i].strip()
            if not line or line.startswith('//') or line.startswith('/*'):
                continue
            if function_name in lines[i] and '(' in lines[i]:
                char_pos = lines[i].index(function_name)
                return i, char_pos

        return -1, -1

    def _find_function_body_end(self, lines: List[str], start_line: int) -> int:
        brace_count = 0
        found_first_brace = False

        for i in range(start_line, len(lines)):
            line = lines[i]
            for char in line:
                if char == '{':
                    brace_count += 1
                    found_first_brace = True
                elif char == '}':
                    brace_count -= 1
                    if found_first_brace and brace_count == 0:
                        return i

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
        keywords = {'if', 'for', 'while', 'switch', 'catch', 'synchronized',
                    'return', 'new', 'super', 'this', 'assert', 'throw'}

        for line_num in range(start_line, end_line + 1):
            line = lines[line_num]

            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            matches = re.finditer(r'\b(\w+)\s*\(', line)
            for match in matches:
                call_name = match.group(1)
                if call_name in keywords:  # or call_name == function_name:
                    continue

                char_pos = match.start(1)
                defs = self.find_definition(rel_file_path, line_num, char_pos)
                # if defs and isinstance(defs, list):
                #     for d in defs:
                if defs is not None:
                    calls.append({
                        'function': call_name,
                        'file': defs['rel_file_path'],
                        'lineno': defs['start_line'] + 1,
                        'line': defs['start_line'],
                        'character': defs['start_character'],
                        'call_site': {
                            'file': rel_file_path,
                            'line': line_num,
                            'col': char_pos
                        }
                    })

        # remove duplicate
        seen = set()
        seen.add((function_name, os.path.relpath(abs_path, self.repo_path), start_line + 1))

        unique_calls = []
        for call in calls:
            key = (call["function"], call["file"], call["line"])
            if key not in seen:
                seen.add(key)
                unique_calls.append(call)

        for idx, c in enumerate(unique_calls):
            c['index'] = idx

        return unique_calls

    def analyze_function_calls(
            self,
            file_path: str,
            function_name: str,
            start_line: int,
            find_calls: bool,
            find_called_by: bool
    ) -> Optional[Dict]:
        rel_file_path = os.path.relpath(file_path, self.repo_path)
        abs_path = os.path.abspath(file_path)

        print(f"Opening document: {abs_path}")
        self.open_document(abs_path)

        with open(abs_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        start_line -= 1
        function_line, function_char = self._find_function_definition_line(lines, start_line, function_name)

        if function_line == -1:
            print(f"Function '{function_name}' not found starting from line {start_line} in {file_path}")
            return None

        print(f"Found function '{function_name}' at line {function_line}, char {function_char}")

        result = {
            "calls": [],
            "called_by": []
        }

        if find_called_by:
            # Find called by
            print(f'''Finding references for `{function_name}` ''')
            references = self.find_references(abs_path, function_line, function_char)
            if references:
                for ref in references:
                    if isinstance(ref, dict):
                        p = ref.get("uri", "").replace("file://", "")
                        ref_line = ref["range"]["start"]["line"]
                        ref_char = ref["range"]["start"]["character"]

                        result["called_by"].append({
                            'index': len(result['called_by']),
                            'file': os.path.relpath(p, self.repo_path),
                            'lineno': ref_line + 1,
                            'line': ref_line,
                            'character': ref_char
                        })
            print(f"Found {len(result['called_by'])} callers")

        if find_calls:
            print(f"Analyzing function body...")
            function_end = self._find_function_body_end(lines, function_line)
            print(f"Function body: lines {function_line} to {function_end}")

            result["calls"] = self._extract_function_calls_from_body(
                rel_file_path, lines, function_line, function_end, function_name
            )

            print(f'Found {len(result['calls'])} function calls')

        return result

    def stop_server(self):
        self.shutdown()

    def shutdown(self):
        self.running = False
        if self.process:
            try:
                self._send_request('shutdown', {}, timeout=5)
                self._send_notification('exit', {})
            except:
                pass

            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()

        if self.reader_thread:
            self.reader_thread.join(timeout=2)

        print("JDTLS shutdown complete")
