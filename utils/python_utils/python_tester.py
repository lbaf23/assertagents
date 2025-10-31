from typing import Tuple, Dict, List
import subprocess
import os
import xml.etree.ElementTree as ET


def run_py_repo_test(
        repo_path: str,
        test_target: str,
        timeout: float = 10.0
) -> Tuple[Dict, str]:

    test_cmd = f'''\
source .venv/bin/activate
pytest {test_target} --junitxml=results.xml
'''

    print(f'>>> {repo_path}')
    print(test_cmd)

    score = 0.0
    total = 0
    passed = 0
    test_output = ''
    test_output_file = os.path.join(repo_path, 'results.xml')

    try:
        if os.path.exists(test_output_file):
            os.remove(test_output_file)

        result = subprocess.run(
            test_cmd,
            shell=True,
            executable='/bin/bash',
            text=True,
            cwd=os.path.abspath(repo_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except Exception as e:
        print(e)
        pass

    if os.path.exists(test_output_file):
        try:
            tree = ET.parse(test_output_file)
            root = tree.getroot()
            suite = root.find('testsuite')

            if suite is None:
                raise ValueError("Invalid XML: No <testsuite> element found")

            total = int(suite.attrib.get('tests', 0))
            failures = int(suite.attrib.get('failures', 0))
            errors = int(suite.attrib.get('errors', 0))
            skipped = int(suite.attrib.get('skipped', 0))
            passed = total - failures - errors - skipped
            score = passed / total if total > 0 else 0.0

            error_messages = []
            for case in suite.findall('testcase'):
                failure = case.find('failure')
                error = case.find('error')
                if failure is not None:
                    error_messages.append(
                        f"Failure:\n" + \
                        '\n'.join(['...\n'] + failure.text.splitlines()[-4:])
                    )
                elif error is not None:
                    error_messages.append(
                        f"Failure:\n" + \
                        '\n'.join(['...\n'] + error.text.splitlines()[-4:])
                    )
            test_output = (
                f"Total {total}, Passed: {passed}, Failures: {failures}, Errors: {errors}, Skipped: {skipped}\n"
                f"Pass Rate: {score}"
            )
            if error_messages:
                test_output += "\n\nError Message:\n" + "\n".join(error_messages)

        except Exception:
            pass
    else:
        try:
            max_lines = 20
            test_output = result.stdout.strip()
            test_output = '\n'.join(test_output.splitlines()[- max_lines : ]).strip()
        except Exception:
            test_output = 'The "pytest" command run failed.'

    return {
        'score': score,
        'passed': passed,
        'total': total,
    }, test_output
