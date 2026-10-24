"""Write a launchd one-shot definition; loading it is a separate explicit action."""
import argparse
from pathlib import Path
import plistlib


def configuration(label, command, directory):
    directory = Path(directory).resolve()
    if not label or not command or not Path(command[0]).is_absolute():
        raise ValueError('Use a named job and an absolute executable')
    return {'Label': label, 'ProgramArguments': command, 'RunAtLoad': True, 'KeepAlive': False,
            'WorkingDirectory': str(directory),
            'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
            'StandardOutPath': str(directory / (label + '.log')),
            'StandardErrorPath': str(directory / (label + '.err'))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    with args.out.open('xb') as file:
        file.write(plistlib.dumps(configuration(args.label, command, args.directory)))
