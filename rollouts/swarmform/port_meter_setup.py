"""Select the build desk defaults for the unreconciled PHP and meter openings."""
from pathlib import Path


def install_port(files):
    name = "/workspace/port_php.py"
    anchor = "        print(install(args.directory))"
    if files[name].count(anchor) != 1:
        raise ValueError("Unexpected port installation entry point")
    files["/workspace/port_component_install.py"] = Path(__file__).with_name("port_component_install.py").read_text()
    files[name] = files[name].replace(anchor, "        from port_component_install import open_installation\n"
                                             "        print(open_installation(args.directory))")


def install_meter(assets):
    name = "qa/meter/check_meter.py"
    before = assets[name]
    start = before.index("cli = Path(sys.argv[1])")
    end = before.index('    source = Path(directory)', start)
    assets[name] = before[:start] + '''if len(sys.argv) > 2:
    sys.exit("usage: python3 check_meter.py [path-to-analyzer]")
with tempfile.TemporaryDirectory() as directory:
    if len(sys.argv) == 2:
        cli = Path(sys.argv[1])
    else:
        sys.path.insert(0, "/workspace")
        from installed_meter import checkout
        installation = Path(directory) / "installed"
        try:
            checkout(installation)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            sys.exit(f"Published analyzer unavailable: {error}. Pass a local executable or Python file to test.")
        cli = installation / "cppcheck"
    if not cli.is_file():
        sys.exit(f"Analyzer unavailable: {cli}")
    program = [str(cli.resolve())] if cli.suffix != ".py" else [sys.executable, str(cli.resolve())]
''' + before[end:]
