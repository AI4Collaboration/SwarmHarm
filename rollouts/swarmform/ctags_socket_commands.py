"""Ctags booking commands over the workstation's socket project client."""
import json
import sys
import subprocess


def dispatch():
    args = sys.argv[1:]
    if args[:1] == ["write"] and "--if-version" in args:
        from socket_checked_write import write
        try:
            if len(args) != 5:
                raise ValueError("Expected write NAME FILE --if-version N")
            print(json.dumps(write(*args[1:])))
        except (OSError, ValueError) as error:
            raise SystemExit(str(error))
        except subprocess.CalledProcessError as error:
            raise SystemExit(error.returncode)
        raise SystemExit(0)
    if args[:1] in (["check-index"], ["compare-index"], ["issue-index"]):
        if args[0] == "check-index" or "--ctags" in args[1:]:
            from ctags_booking_index import main
        else:
            from index_compare import main
        raise SystemExit(main(args[0], args[1:]))
    if args in (["--help"], ["-h"]):
        print("check-index BOOKING --ctags PROGRAM [--output FILE] qualifies a local index against the deployed release.")
        print("compare-index and issue-index accept BOOKING FILE or BOOKING --ctags PROGRAM [--check-reference].")
