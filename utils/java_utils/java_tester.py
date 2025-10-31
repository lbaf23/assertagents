from typing import Tuple, Dict, List
import subprocess
import os
import shutil
import xml.etree.ElementTree as ET


def compile_java_repo_test(repo_path: str, sub_repo: str, test_file_path: str, timeout: float = 60.0) -> Tuple[Dict, str]:
    test_cmd = f'javac -Xlint:unchecked -nowarn -cp "$(cat cp.txt):target/classes:target/test-classes" -d "/tmp" "{test_file_path}"'
    passed = False
    test_output = ''
    try:
        result = subprocess.run(
            test_cmd,
            shell=True,
            text=True,
            cwd=os.path.join(repo_path, sub_repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        passed = result.returncode == 0

        if not passed:
            output = result.stdout + result.stderr
            max_lines = 20
            test_output = output.strip()
            test_output = '\n'.join(test_output.splitlines()[- max_lines : ]).strip()

    except Exception:
        test_output = 'Java file compile exceeded time limit.'

    return {
        'passed': passed,
    }, test_output


def run_java_repo_test(repo_path: str, sub_repo: str, test_class: str, test_target: str, timeout: float = 120.0) -> Tuple[Dict, str]:
    test_cmd = f'''\
mvn compiler:testCompile surefire:test -o -q \
-Dgpg.skip -DskipITs -Dinvoker.skip=true -Dspotless.skip=true -Danimal.sniffer.skip=true -Dlicense.skip=true \
-Dtest="{test_target}"
'''

    if os.path.exists(os.path.join(repo_path, sub_repo, f'target/surefire-reports')):
        shutil.rmtree(os.path.join(repo_path, sub_repo, f'target/surefire-reports'))

    score = 0.0
    total = 0
    passed = 0
    try:
        result = subprocess.run(
            test_cmd,
            shell=True,
            text=True,
            cwd=os.path.join(repo_path, sub_repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        test_output_file = os.path.join(repo_path, sub_repo, f'target/surefire-reports/TEST-{test_class}.xml')
        test_output = ''

        if os.path.exists(test_output_file):
            try:
                tree = ET.parse(test_output_file)
                root = tree.getroot()
                test_output = f'''Test class: {root.attrib.get('name')}, tests: {root.attrib.get('tests')}, failures: {root.attrib.get('failures')}, errors: {root.attrib.get('errors')}, skipped: {root.attrib.get('skipped')}'''

                for testcase in root.findall('testcase'):
                    case_name = testcase.attrib.get('name')
                    failure = testcase.find('failure')
                    error = testcase.find('error')

                    if failure is not None:
                        test_output += f'''\n  - [Failure] {case_name}: {failure.attrib.get('message')}'''
                    if error is not None:
                        test_output += f'''\n  - [Error] {case_name}: {error.attrib.get('message')}'''

                    if failure is None and error is None:
                        test_output += f'''\n  - [Passed] {case_name}'''
                        passed += 1
                    total += 1
                score = passed / total
            except Exception:
                pass
        else:
            max_lines = 20
            test_output = result.stdout.strip()
            test_output = '\n'.join(test_output.splitlines()[- max_lines : ]).strip()

    except Exception:
        test_output = 'The "mvn test" command exceeded the time limit.'

    return {
        'score': score,
        'passed': passed,
        'total': total,
    }, test_output
