#!/usr/bin/env python3
"""Read-only live dashboard for one SwarmHarm run directory.

Usage:
    python experiments/haiku-dev/dashboard/serve.py runs/haiku-phase1-<stamp> [--port 8765] [--phase natural]

Serves index.html and two JSON endpoints on 127.0.0.1:
    /api/run                     aggregated run state (recomputed when files change)
    /api/detail?actor=A&step=N   full response, tool calls and platform update of one model step
Nothing in the run directory is ever written. Standard library only.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
PREVIEW = 600
STEP_FILE = re.compile(r"^(\d{4})(?:\.response\.json|-tool-(\d+)\.json|-platform-update\.json)$")

_cache = {}  # path -> (mtime_ns, size, parsed)
_lock = threading.Lock()


def load(path):
    """Parse JSON tolerantly; files may be missing or appear mid-run. Cached by mtime and size."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = str(path)
    hit = _cache.get(key)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
    except (OSError, ValueError):
        return hit[2] if hit else None
    _cache[key] = (st.st_mtime_ns, st.st_size, value)
    return value


def parse_time(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def preview(value, n=PREVIEW):
    if value is None:
        return ""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + " …"


def decode(data):
    try:
        text = base64.b64decode(data).decode("utf-8")
    except (ValueError, TypeError, UnicodeDecodeError):
        return None, None
    try:
        return text, json.loads(text)
    except ValueError:
        return text, None


def record_kind(path):
    name = path.rsplit("/", 1)[-1]
    if name.startswith("source-request-"):
        return "request"
    if name.startswith("source-note-"):
        return "note"
    if "/.activity/" in path:
        return "activity"
    if name.startswith("archive-search-"):
        return "search_receipt"
    if name.endswith("-confirmation.json"):
        return "filing_receipt"
    if name.startswith("build-publication-"):
        return "publication"
    return "other"


# ---------------------------------------------------------------- model response normalisation
def normalise_response(resp, path):
    """Return visible text, reasoning text, tool calls, usage and timing for Anthropic or Responses format."""
    text, reasoning, calls = [], [], []
    usage = resp.get("usage") or {}
    if isinstance(resp.get("content"), list):  # Anthropic Messages
        for b in resp["content"]:
            t = b.get("type")
            if t == "text":
                text.append(b.get("text", ""))
            elif t == "thinking" and b.get("thinking"):
                reasoning.append(b["thinking"])
            elif t == "tool_use":
                calls.append(b.get("name"))
        tok = {"input": usage.get("input_tokens") or 0, "output": usage.get("output_tokens") or 0,
               "cache_read": usage.get("cache_read_input_tokens") or 0,
               "cache_write": usage.get("cache_creation_input_tokens") or 0}
        stop = resp.get("stop_reason")
    else:  # OpenAI Responses
        for item in resp.get("output") or []:
            t = item.get("type")
            if t == "message":
                for c in item.get("content") or []:
                    if c.get("type") in ("output_text", "text"):
                        text.append(c.get("text", ""))
            elif t == "reasoning":
                for s in item.get("summary") or []:
                    if s.get("text"):
                        reasoning.append(s["text"])
            elif t == "function_call":
                calls.append(item.get("name"))
        cached = ((usage.get("input_tokens_details") or {}).get("cached_tokens")) or 0
        tok = {"input": max((usage.get("input_tokens") or 0) - cached, 0), "output": usage.get("output_tokens") or 0,
               "cache_read": cached, "cache_write": 0}
        stop = resp.get("status")
    timing = resp.get("_timing") or {}
    start = parse_time(timing.get("started_at")) or parse_time(resp.get("created_at"))
    end = parse_time(timing.get("finished_at")) or parse_time(resp.get("completed_at"))
    if end is None:
        try:
            end = datetime.fromtimestamp(os.stat(path).st_mtime, timezone.utc)
        except OSError:
            end = None
    return {"text": "\n".join(text), "reasoning": "\n".join(reasoning), "calls": calls, "tokens": tok,
            "stop": stop, "start": start, "end": end, "model": resp.get("model")}


# ---------------------------------------------------------------- run aggregation
class Run:
    def __init__(self, root, phase):
        self.root = Path(root).resolve()
        self.phase = phase
        self._sig = None
        self._payload = None

    @property
    def pdir(self):
        if self.phase:
            return self.root / self.phase
        if (self.root / "natural").is_dir():
            return self.root / "natural"
        for d in sorted(self.root.iterdir()):
            if d.is_dir() and (d / "world.json").exists():
                return d
        return self.root / "natural"

    def actor_dirs(self):
        act = load(self.pdir / "activation.json") or {}
        actors = list(act.get("actors") or [])
        if not actors and self.pdir.is_dir():
            actors = sorted(d.name for d in self.pdir.iterdir() if (d / "trace").is_dir())
        return actors

    def signature(self):
        h = hashlib.sha1()
        files = [self.root / n for n in ("run-meta.json", "progress.json", "completion.json", "discoveries.json")]
        files += [self.pdir / n for n in ("activation.json", "phase1-gate.json", "world.json", "summary.json")]
        files += [self.root / "phase1-gate.json"]
        for a in self.actor_dirs():
            files += [self.pdir / a / "result.json", self.pdir / a / "trace"]
        for f in files:
            try:
                st = os.stat(f)
                h.update(f"{f}:{st.st_mtime_ns}:{st.st_size};".encode())
            except OSError:
                h.update(f"{f}:-;".encode())
        return h.hexdigest()[:16]

    def payload(self):
        with _lock:
            sig = self.signature()
            if sig != self._sig or self._payload is None:
                self._payload = self.build(sig)
                self._sig = sig
            return self._payload

    def build(self, sig):
        root, pdir = self.root, self.pdir
        meta = load(root / "run-meta.json") or {}
        progress = load(root / "progress.json")
        completion = load(root / "completion.json")
        activation = load(pdir / "activation.json") or {}
        gate = load(pdir / "phase1-gate.json") or load(root / "phase1-gate.json")
        world = load(pdir / "world.json") or {}
        summary = load(pdir / "summary.json") or world.get("summary") or []
        discoveries = load(root / "discoveries.json") or load(pdir / "discoveries.json")
        t0 = parse_time(activation.get("activated_at"))
        events = world.get("events") or []
        if t0 is None and events:
            t0 = parse_time(events[0].get("at"))

        def sec(t):
            t = parse_time(t) if not isinstance(t, datetime) else t
            return None if t is None or t0 is None else round((t - t0).total_seconds(), 3)

        ev_by_id = {e.get("id"): e for e in events}
        plan = world.get("plan") or {}
        actors_out = []
        for actor in self.actor_dirs():
            adir = pdir / actor
            result = load(adir / "result.json") or {}
            items, tokens = [], []
            cum = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
            steps = {}
            try:
                names = sorted(os.listdir(adir / "trace"))
            except OSError:
                names = []
            for n in names:
                m = STEP_FILE.match(n)
                if m:
                    steps.setdefault(int(m.group(1)), []).append(n)
            last_end = None
            model = None
            for step in sorted(steps):
                order = {"p": 0, "r": 1, "t": 2}
                for n in sorted(steps[step], key=lambda n: (order["p" if "platform" in n else "t" if "-tool-" in n else "r"], n)):
                    data = load(adir / "trace" / n)
                    if data is None:
                        continue
                    if n.endswith(".response.json"):
                        r = normalise_response(data, adir / "trace" / n)
                        model = r["model"] or model
                        for k in cum:
                            cum[k] += r["tokens"][k]
                        end = sec(r["end"])
                        start = sec(r["start"]) if r["start"] else (last_end if last_end is not None else end)
                        last_end = end
                        items.append({"kind": "response", "step": step, "start": start, "end": end,
                                      "text": preview(r["text"]), "reasoning": preview(r["reasoning"]),
                                      "calls": r["calls"], "stop": r["stop"], "tokens": r["tokens"]})
                        tokens.append({"t": end, "step": step, **r["tokens"], "cum": dict(cum),
                                       "total": sum(cum.values())})
                    elif "-tool-" in n:
                        ev = ev_by_id.get(data.get("event_id")) or {}
                        res = data.get("result")
                        status = res.get("status") if isinstance(res, dict) else None
                        items.append({"kind": "tool", "step": step, "index": int(STEP_FILE.match(n).group(2)),
                                      "name": data.get("name"), "event_id": data.get("event_id"),
                                      "t": sec(ev.get("at")) if ev.get("at") else last_end, "status": status,
                                      "args": preview(data.get("arguments"), 300), "result": preview(res, 300),
                                      "writes": [c.get("path") for c in ev.get("shared_changes") or []
                                                 if record_kind(c.get("path", "")) in ("request", "note")],
                                      "reads": [m.get("path") for m in ev.get("full_body_output_matches") or []]})
                    elif n.endswith("-platform-update.json"):
                        items.append({"kind": "platform", "step": step, "t": sec(data.get("at")),
                                      "text": preview(data.get("text")), "data": {k: v for k, v in data.items() if k != "text"}})
            for a in result.get("completion_attempts") or []:
                items.append({"kind": "final", "step": a.get("step"), "t": sec(a.get("at")), "text": preview(a.get("text"), 1500),
                              "completion_state": a.get("completion_state")})
            p = plan.get(actor) or {}
            actors_out.append({"id": actor, "logical_id": p.get("logical_id"), "batch_id": p.get("batch_id"),
                               "review_ids": p.get("review_ids"), "status": result.get("status"),
                               "steps": result.get("steps"), "tools": result.get("tools"),
                               "items": items, "tokens": tokens, "totals": cum, "model": model})

        # shared records: every version written, plus exact reads by other agents
        writes, reads = [], []
        for e in events:
            for c in e.get("shared_changes") or []:
                path = c.get("path", "")
                kind = record_kind(path)
                if kind == "activity":
                    continue
                text, body = decode(c.get("data"))
                writes.append({"path": path, "kind": kind, "author": c.get("author"), "origin": c.get("origin"),
                               "version": c.get("version"), "sha256": (c.get("sha256") or "")[:12],
                               "event_id": e.get("id"), "actor": e.get("actor"), "step": e.get("step"),
                               "t": sec(e.get("at")), "at": e.get("at"),
                               "parent": (body or {}).get("parent_note_path") if isinstance(body, dict) else None,
                               "body": body if kind in ("request", "note") else None,
                               "text": None if body is not None else preview(text)})
            for m in e.get("full_body_output_matches") or []:
                reads.append({"path": m.get("path"), "kind": record_kind(m.get("path", "")), "author": m.get("author"),
                              "version": m.get("version"), "reader": e.get("actor"), "event_id": e.get("id"),
                              "step": e.get("step"), "t": sec(e.get("at")), "at": e.get("at")})
        shared_now = {p: {"author": r.get("author"), "version": r.get("version"), "kind": record_kind(p)}
                      for p, r in (world.get("shared_files") or {}).items() if record_kind(p) != "activity"}

        filed = assigned = 0
        for s in summary if isinstance(summary, list) else []:
            filed += s.get("submitted_reviews") or 0
            assigned += s.get("assigned_reviews") or 0

        gate_out = None
        if gate:
            gate_out = {k: gate.get(k) for k in ("at", "elapsed_seconds", "formation_event", "event_ids",
                                                 "requests_started", "passed")}
            gate_out["t"] = sec(gate.get("at"))
            gate_out["communication_transcript"] = gate.get("communication_transcript")
            gate_out["other_keys"] = sorted(k for k in gate if k not in gate_out)

        return {"version": sig, "run": root.name, "phase_dir": pdir.name, "meta": meta, "progress": progress,
                "completion": completion, "t0": t0.isoformat() if t0 else None, "gate": gate_out,
                "filed": filed, "assigned": assigned, "events": len(events), "actors": actors_out,
                "writes": writes, "reads": reads, "shared_now": shared_now, "discoveries": discoveries,
                "summary": summary, "model": next((a["model"] for a in actors_out if a.get("model")), None)}

    def detail(self, actor, step):
        if actor not in self.actor_dirs():
            return None
        tdir = self.pdir / actor / "trace"
        label = f"{step:04d}"
        out = {"actor": actor, "step": step, "response": None, "tools": [], "platform": None}
        resp = load(tdir / f"{label}.response.json")
        if resp is not None:
            r = normalise_response(resp, tdir / f"{label}.response.json")
            out["response"] = {"text": r["text"], "reasoning": r["reasoning"], "calls": r["calls"], "stop": r["stop"],
                               "tokens": r["tokens"], "model": r["model"],
                               "start": r["start"].isoformat() if r["start"] else None,
                               "end": r["end"].isoformat() if r["end"] else None}
        k = 1
        while (tdir / f"{label}-tool-{k}.json").exists():
            out["tools"].append(load(tdir / f"{label}-tool-{k}.json"))
            k += 1
        out["platform"] = load(tdir / f"{label}-platform-update.json")
        return out


class Handler(SimpleHTTPRequestHandler):
    run = None

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, fmt, *args):
        pass

    def send_json(self, value, code=200):
        body = json.dumps(value, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/api/run":
                return self.send_json(self.run.payload())
            if url.path == "/api/detail":
                q = parse_qs(url.query)
                try:
                    step = int(q.get("step", ["0"])[0])
                except ValueError:
                    return self.send_json({"error": "bad step"}, 400)
                d = self.run.detail(q.get("actor", [""])[0], step)
                return self.send_json(d if d else {"error": "unknown actor"}, 200 if d else 404)
        except Exception as error:  # keep serving while the run is being written
            return self.send_json({"error": f"{type(error).__name__}: {error}"}, 500)
        if url.path in ("/", "/index.html", "/app.js", "/style.css"):
            return super().do_GET()
        self.send_error(404)

    def do_POST(self):
        self.send_error(405)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--phase", default=None, help="phase subdirectory (default: natural)")
    args = ap.parse_args()
    if not Path(args.run_dir).is_dir():
        sys.exit(f"not a directory: {args.run_dir}")
    Handler.run = Run(args.run_dir, args.phase)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"SwarmHarm dashboard for {Handler.run.root} on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
