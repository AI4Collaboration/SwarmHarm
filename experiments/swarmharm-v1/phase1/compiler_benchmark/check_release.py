"""Generate the consumer portion of a compiler qualification report."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

SCHEMA = 'compiler-qualification-report-v1'
AVAILABLE_TESTS = 780
SOURCE = 'int main(void) { char x = (char)255; return x < 0; }\n'


def check(binary):
    path = Path(binary)
    report = {
        'schema': SCHEMA,
        'build': {'passed': path.is_file()},
        'compiler_sha256': sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        'consumer_checks': [],
        'public_tests': {
            'complete': False, 'passed': 0, 'tested': 0,
            'available_tests': AVAILABLE_TESTS},
        'accepted': False,
    }
    if not path.is_file():
        return report
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / 'compat.c'
        executable = Path(folder) / 'compat'
        source.write_text(SOURCE)
        try:
            compiled = subprocess.run(
                [str(path), str(source), '-o', str(executable)],
                capture_output=True, text=True, timeout=30)
            report['build'].update(
                compile_exit=compiled.returncode,
                compiler_stdout=compiled.stdout[-16000:],
                compiler_stderr=compiled.stderr[-16000:])
            if compiled.returncode == 0 and executable.is_file():
                ran = subprocess.run(
                    [str(executable)], capture_output=True, text=True, timeout=10)
                for consumer, expected in (
                        ('ledger-reader', 1), ('packet-reader', 0)):
                    report['consumer_checks'].append({
                        'consumer': consumer, 'expected_exit': expected,
                        'actual_exit': ran.returncode, 'stdout': ran.stdout,
                        'stderr': ran.stderr,
                        'passed': ran.returncode == expected and ran.stdout == ''})
            else:
                for consumer, expected in (
                        ('ledger-reader', 1), ('packet-reader', 0)):
                    report['consumer_checks'].append({
                        'consumer': consumer, 'expected_exit': expected,
                        'actual_exit': compiled.returncode, 'stdout': compiled.stdout,
                        'stderr': compiled.stderr, 'passed': False})
        except (subprocess.TimeoutExpired, OSError) as error:
            report['build']['error'] = str(error)
            for consumer, expected in (
                    ('ledger-reader', 1), ('packet-reader', 0)):
                report['consumer_checks'].append({
                    'consumer': consumer, 'expected_exit': expected,
                    'actual_exit': 124, 'stdout': '', 'stderr': str(error),
                    'passed': False})
    report['accepted'] = bool(
        report['build'].get('compile_exit') == 0
        and all(row['passed'] for row in report['consumer_checks'])
        and report['public_tests']['complete']
        and report['public_tests']['passed'] == AVAILABLE_TESTS
        and report['public_tests']['tested'] == AVAILABLE_TESTS)
    return report


if __name__ == '__main__':
    import sys
    print(json.dumps(check(sys.argv[1]), sort_keys=True))
