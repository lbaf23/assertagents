from typing import List, Tuple
import os


DEFAULT_SOURCE_ROOT = (
    'src/main/java',
    'src/test/java',
)


def path_to_pkg(file_path: str, source_root: List[str] = DEFAULT_SOURCE_ROOT) -> Tuple[str, str]:
    assert file_path.endswith('.java'), f'''Not a java file: {file_path}'''

    file_path = file_path[:-len('.java')]
    pkg = ''
    sub_repo = ''
    for sr in source_root:
        if sr in file_path:
            pkg = file_path[file_path.index(sr) + len(sr) : ].strip('/').replace('/', '.')
            sub_repo = file_path[ : file_path.index(sr)].strip('/')
            break
    return sub_repo, pkg


def pkg_to_path(
        repo_path: str,
        first_sub_repo: str,
        sub_repos: str,
        pkg: str,
        source_root: List[str] = DEFAULT_SOURCE_ROOT
) -> str:
    pkg = pkg.replace('.', '/') + '.java'
    path = ''
    for sr in source_root:
        p = os.path.join(repo_path, first_sub_repo, sr, pkg)
        if os.path.exists(p):
            path = p
            break

    if path == '':
        for sub_repo in sub_repos:
            if sub_repo == first_sub_repo:
                continue

            for sr in source_root:
                p = os.path.join(repo_path, sub_repo, sr, pkg)
                if os.path.exists(p):
                    path = p
                    break
    return path
