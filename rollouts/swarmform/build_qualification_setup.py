"""Attach optional reference qualification to an existing station entry point."""
from pathlib import Path


def replace_one(script, original, replacement):
    if script.count(original) != 1:
        raise ValueError(f"Qualification entry point changed: {original}")
    return script.replace(original, replacement, 1)


def install_ctags(files):
    files["/workspace/ctags_qualification.py"] = Path(__file__).with_name("ctags_qualification.py").read_text()
    name = "/workspace/ctags_booking_index.py"
    source = replace_one(files[name], "check_reference=False, output=None):",
                         "check_reference=False, output=None, check_edition=None):")
    source = replace_one(source, '        if len(selected) != 1 or not selected <= {"A","B"}:',
                         '        if operation == "check-index" and check_edition in selected:\n'
                         '            selected = {check_edition}\n'
                         '        if len(selected) != 1 or not selected <= {"A","B"}:')
    files[name] = replace_one(source, "    parser.add_argument(\"booking\",",
                              '    if operation == "check-index":\n'
                              '        from ctags_qualification import check\n'
                              '        try:\n'
                              '            return check(arguments)\n'
                              '        except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:\n'
                              '            parser.exit(2, f"{error}\\n")\n'
                              '    parser.add_argument("booking",')


def install_meter(files):
    name = "/workspace/booking_regression.py"
    source = replace_one(files[name], '    if record == bool(args.candidate):',
                         '    if record and args.candidate:')
    source = replace_one(source, 'check requires a candidate executable; record takes only booking and edition',
                         'record takes only booking and edition')
    files[name] = replace_one(source, '            cli = args.candidate.resolve()',
                              '            from installed_meter import candidate\n'
                              '            cli = candidate(args.candidate, root)')
    files["/workspace/installed_meter.py"] = Path(__file__).with_name("installed_meter.py").read_text()


def install_php(files):
    name = "/workspace/port_php.py"
    files["/workspace/port_cli_case.py"] = Path(__file__).with_name("port_cli_case.py").read_text()
    files[name] = replace_one(files[name], "def main():\n", 'def main():\n'
                              '    if sys.argv[1:2] == ["--cli-case"]:\n'
                              '        from port_cli_case import main as cli_case\n'
                              '        return cli_case(sys.argv[2:])\n')
