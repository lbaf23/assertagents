import subprocess
import os


def download_java_dependencies(repo_path: str, sub_repo: str) -> bool:
    cmd = 'mvn clean install -DskipTests -Dgpg.skip -Dcheckstyle.skip=true'
    print(f'''Run {cmd} at {os.path.join(repo_path, sub_repo)}''')
    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        cwd=os.path.join(repo_path, sub_repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    passed = result.returncode == 0
    if not passed:
        print(f'mvn run failed: {result.stdout}')
    return passed


def extract_java_dependencies(repo_path: str, sub_repo: str) -> bool:
    cmd = 'mvn dependency:build-classpath -o -Dmdep.outputFile=cp.txt'
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=os.path.join(repo_path, sub_repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0
