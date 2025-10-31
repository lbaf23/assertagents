

class LSPClient:
    def start_server(self):
        raise NotImplementedError()

    def find_definition(self, rel_file_path: str, line: int, character: int):  # index of line and character starts from 0
        raise NotImplementedError()

    def stop_server(self):
        raise NotImplementedError()
