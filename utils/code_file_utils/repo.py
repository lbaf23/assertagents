# from typing import Tuple, Dict
#
# from .java_utils import run_java_repo_test, download_java_dependencies, compile_java_repo_test, extract_java_dependencies
# from .python_utils import run_python_repo_test, download_python_dependencies
#
#
# def extract_dependencies(repo_path: str, lang: str) -> bool:
#     if lang.lower() == 'java':
#         return extract_java_dependencies(repo_path)
#     else:
#         raise ValueError(f'Unknown language: {lang}')
#
#
# def download_dependencies(repo_path: str, lang: str) -> bool:
#     if lang.lower() == 'java':
#         return download_java_dependencies(repo_path)
#     elif lang.lower() == 'python':
#         return download_python_dependencies(repo_path)
#     else:
#         raise ValueError(f'Unknown language: {lang}')
#
#
# def compile_repo_test(repo_path: str, test_file_path: str, lang: str) -> Tuple[Dict, str]:
#     if lang.lower() == 'java':
#         return compile_java_repo_test(repo_path, test_file_path)
#     else:
#         raise ValueError(f'Unknown language: {lang}')
#
#
# def run_repo_test(repo_path: str, test_package_path: str, test_target: str, lang: str) -> Tuple[Dict, str]:
#     if lang.lower() == 'java':
#         return run_java_repo_test(repo_path, test_package_path, test_target)
#     elif lang.lower() == 'python':
#         return run_python_repo_test(repo_path, test_package_path, test_target)
#     else:
#         raise ValueError(f'Unknown language: {lang}')
