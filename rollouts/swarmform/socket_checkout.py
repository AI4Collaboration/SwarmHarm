"""Socket checkout performs the ordinary versioned requests in its caller."""
import base64
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import formation_store as store


def socket_checkout_call(arguments):
    operation = arguments[0]
    name = arguments[1] if operation == "read" else None
    version = int(arguments[3]) if operation == "read" else None
    config = json.loads(Path("/workspace/project-access.json").read_text())
    request = Request(config["url"] + "/artifacts",
                      data=store.encode({"operation": operation, "name": name, "version": version}),
                      headers={"Authorization": config["key"], "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error)
        except (ValueError, OSError):
            raise RuntimeError(f"Project operation failed: {operation}") from error
        if not isinstance(detail, dict) or not isinstance(detail.get("error"), str):
            raise RuntimeError(f"Project operation failed: {operation}") from error
        print(json.dumps({"name": name, "error": detail["error"]}, ensure_ascii=False), file=sys.stderr)
        raise RuntimeError(f"Project operation failed: {operation}") from error
    except OSError as error:
        print(str(error), file=sys.stderr)
        raise RuntimeError(f"Project operation failed: {operation}") from error
    if operation == "read":
        output = arguments[5]
        Path(output).write_bytes(base64.b64decode(result.pop("data")))
        result["saved_to"] = output
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    if sys.argv[1:2] == ["work"]:
        from socket_worktree import main
        raise SystemExit(main(sys.argv[2:]))
    if sys.argv[1:] in (["--help"], ["-h"]):
        print("work PATH [PATH ...] -- COMMAND [ARG ...] runs COMMAND in a private directory of the named project files. Current versions are downloaded. Successful commands save changed named files, one at a time, if their base versions still match. Unlisted local files are temporary. A failed command or save retains the local directory.")
    if sys.argv[1:2] == ["checkout"]:
        # Keep the common checkout validation, file verification and cleanup.
        store.client_call = socket_checkout_call
    raise SystemExit(store.main())
