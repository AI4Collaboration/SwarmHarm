"""Match sender-labelled inbox output to the actual archived message file read by that call."""
from collections import Counter
import json
import re

from mapped_processes import log_lines, unhex

SENDER_LINE = re.compile(r"(?m)^[\w.-]+(?:: |[ \t])\S")
READ = re.compile(rb"\bread\(\d+<([^>]+)>, ")


def mailbox_files_read(case, actor, call_id):
    archive = case / "reads" / actor
    index = max(archive.glob("[0-9]*.json"), default=None)
    if index is None or not (archive / "origins.json").is_file():
        return {}
    origins = json.loads((archive / "origins.json").read_bytes())
    files = json.loads(index.read_bytes())["files"]
    reads = {}
    for name, binding in origins.items():
        native = binding.get("native_call") or {}
        if native.get("actor") != actor or native.get("call_id") != call_id or name not in files:
            continue
        for number, line in enumerate(log_lines(archive, files[name]), 1):
            match = READ.search(line[:1800])
            if not match:
                continue
            raw = match[1]
            if raw.startswith(b"\\x"):
                if not re.fullmatch(rb"(?:\\x[0-9a-f]{2})+", raw):
                    continue
                raw = unhex(raw)
            if not raw.startswith(b"/var/tmp/exports/messages/") or not raw.endswith(b".json"):
                continue
            count = line.rpartition(b" = ")[2].strip()
            if count.isdigit() and int(count) > 0:
                reads.setdefault(raw.decode(), (name, number))
    return reads


def resolve_inbox(case, receipts, catalog):
    for message, ref in receipts:
        if message is not None:
            yield message, ref
            continue
        actor = ref["actor"]
        output = "\n" + ref["inbox_stdout"] + "\n"
        candidates = []
        for body, _, _ in catalog.values():
            text = body.get("text")
            sender = body.get("sender")
            if (not isinstance(sender, str) or sender == actor or body.get("recipient") not in (actor, "all")
                    or not isinstance(text, str) or not text.strip() or text in ref["inbox_command"]):
                continue
            if any("\n" + sender + separator + text + "\n" in output for separator in (" ", ": ", "\t")):
                candidates.append(body)
        if not candidates:
            continue
        reads = mailbox_files_read(case, actor, ref["call_id"])
        found = [(body, reads[path]) for body in candidates
                 if (path := f"/var/tmp/exports/messages/{body['recipient']}/{body['id']}.json") in reads]
        occurrences = Counter((body["sender"], body["text"]) for body, _ in found)
        for body, (name, line) in found:
            if occurrences[body["sender"], body["text"]] == 1:
                yield body, dict(actor=actor, call_id=ref["call_id"], seconds=ref["seconds"],
                                 display_format="sender_and_text", reader_log=name, reader_line=line)
