import os
import zipfile

def unzip_file(file_path: str, unzip_path: str):
    os.makedirs(unzip_path, exist_ok=True)
    with zipfile.ZipFile(file_path, 'r') as zf:
        zf.extractall(unzip_path)
