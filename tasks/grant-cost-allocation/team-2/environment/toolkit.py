"""Small helpers shared by the back-office tool modules."""


class ToolError(Exception):
    """A refused call; the message goes back to the caller as {"error": ...}."""


TOOLS = {}


def tool(doc):
    def wrap(fn):
        TOOLS[fn.__name__] = {"fn": fn, "doc": doc}
        return fn
    return wrap


def need(args, *names):
    missing = [n for n in names if args.get(n) in (None, "")]
    if missing:
        raise ToolError("missing " + ", ".join("--" + n.replace("_", "-") for n in missing))


def find(rows, value, what, key="id"):
    for row in rows:
        if row.get(key) == value:
            return row
    raise ToolError(f"no {what} {value}")


# Notes are the same in every world, so their tools live here.
@tool("Search team notes by keyword, reference or author. --query text")
def search_notes(state, args):
    need(args, "query")
    q = str(args["query"]).lower()
    hits = [n for n in state["notes"] if q in (n["text"] + " " + n.get("ref", "") + " " + n["author"]).lower()]
    return {"notes": hits}


@tool("List the most recent team notes, optionally for one reference. [--ref id] [--limit n]")
def list_notes(state, args):
    rows = [n for n in state["notes"] if not args.get("ref") or n.get("ref") == args["ref"]]
    return {"notes": rows[-int(args.get("limit", 20)):]}


@tool("Add a note for the team. --ref id --text text")
def add_note(state, args):
    need(args, "ref", "text")
    note = {"id": f"N-{len(state['notes']) + 1:04d}", "author": "you", "ref": args["ref"], "text": args["text"]}
    state["notes"].append(note)
    return note
