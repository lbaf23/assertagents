import subprocess


def download_py_dependencies(repo_path: str, install_cmd: str) -> bool:
    result = subprocess.run(
        install_cmd,
        shell=True,
        text=True,
        executable='/bin/bash',
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0
