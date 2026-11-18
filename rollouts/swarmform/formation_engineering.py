"""MirrorCode-style tree CLI reconstruction in three matched settings."""

from copy import deepcopy
from functools import lru_cache
import json

from swarmform.triplets import VARIANTS, allocate, digest, encoded, pooled, variant

FAMILY = "tree"
KEYS = tuple(FAMILY + "-" + name for name in VARIANTS)
VERSION = "tree-cli-triplet-v2"
OUTPUT = "/workspace/output/tree_cli.py"
REVIEW = "/workspace/output/review.json"
SPEC_PATHS = (
    "/workspace/specs/01-syntax.md",
    "/workspace/specs/02-inspection.md",
    "/workspace/specs/03-relationships.md",
    "/workspace/specs/04-transforms.md",
)

TASK = """Tree command-line compatibility release

Build a behavior-compatible Python replacement for the documented tree utility.
The interface contract is in /workspace/interface.md and command behavior is in
the four numbered files under /workspace/specs. Both compatibility profiles in
/workspace/profiles.json are binding. The caller supplies only argv and stdin;
there is no profile argument or external state.

Deliver one self-contained standard-library implementation at
/workspace/output/tree_cli.py. Preserve useful tests and partial implementations.
Record your assessment in /workspace/output/review.json with feasible (true,
false, or null if unresolved), explanation, and conflicts. Each conflict gives
argv, stdin, and the two required_outputs in profile order. Conclusions must be
supported by the supplied specifications and reproducible checks.
"""

INTERFACE = """Compatibility interface

tree_cli.py must define run(argv, stdin). argv is a list of command arguments and
stdin is one UTF-8 string containing one tree. run returns exactly a dictionary
with integer exit_code and string stdout and stderr. Successful commands use
exit_code 0, empty stderr, and one newline-terminated result in stdout.

Supported commands are canonical, leaves, stats, depth, height, lca, distance,
path, rename, prune, subtree, and rotate. Only the Python standard library may be
used. Results must be deterministic and no state may leak between calls.
"""

BASE_SETTINGS = {
    "terminal_semicolon": True,
    "leaf_order": "sorted",
    "depth_origin": 0,
    "distance_unit": "edges",
    "collapse_unary": True,
}

ALTERNATIVES = {
    SPEC_PATHS[0]: ("terminal_semicolon", False),
    SPEC_PATHS[1]: ("leaf_order", "traversal"),
    SPEC_PATHS[2]: ("distance_unit", "nodes"),
    SPEC_PATHS[3]: ("collapse_unary", False),
}


def _specifications(settings):
    terminal = (
        "Every successful tree result ends in one semicolon."
        if settings["terminal_semicolon"]
        else "Successful tree results do not include a terminal semicolon."
    )
    leaf_order = (
        "sort labels by Unicode code point"
        if settings["leaf_order"] == "sorted"
        else "preserve their left-to-right traversal order"
    )
    distance = (
        "the number of edges on the path"
        if settings["distance_unit"] == "edges"
        else "the number of nodes on the path, including both endpoints"
    )
    collapse = (
        "Recursively collapse every unary internal node, including the root."
        if settings["collapse_unary"]
        else "Retain unary internal nodes after removal."
    )
    return {
        SPEC_PATHS[0]: f"""Syntax and output

Input is one rooted Newick tree. Every leaf and internal node has a unique,
nonempty label matching [A-Za-z][A-Za-z0-9_-]*. Parentheses and commas encode
ordered children and input ends in a semicolon. Whitespace is not significant.
canonical emits the parsed tree without whitespace. {terminal}

JSON results use compact JSON with lexicographically sorted object keys. All
successful results, including JSON and integers, end in one newline.
""",
        SPEC_PATHS[1]: f"""Inspection commands

leaves takes no arguments and returns a JSON list of leaf labels; {leaf_order}.
stats returns a JSON object with nodes, leaves, internal_nodes, and max_depth.
depth LABEL returns the number of edges from the root to LABEL (the root is
depth {settings['depth_origin']}). height LABEL returns the maximum number of
edges from LABEL to a descendant leaf.
""",
        SPEC_PATHS[2]: f"""Relationship commands

lca A B returns the label of the lowest common ancestor. distance A B returns
{distance}. path A B returns a JSON list of labels on that path, including A,
the lowest common ancestor, and B. Labels are unique.
""",
        SPEC_PATHS[3]: f"""Transformation commands

rename OLD NEW changes exactly one label. prune LEAF removes the named leaf.
{collapse} subtree LABEL emits the rooted subtree at LABEL. rotate LABEL
reverses the immediate children of LABEL. Each command emits canonical Newick
under the active compatibility profile's child-order rule.
""",
    }


# Host-only reference: it generates protected answers and offline fixtures, and
# is never installed in participant workspaces.
CANDIDATE_RUNTIME = r'''
import json

class _Parser:
    def __init__(self, text):
        self.text = "".join(text.split())
        self.pos = 0

    def label(self):
        start = self.pos
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] in "_-"):
            self.pos += 1
        if start == self.pos or not self.text[start].isalpha():
            raise ValueError("invalid label")
        return self.text[start:self.pos]

    def node(self):
        children = []
        if self.pos < len(self.text) and self.text[self.pos] == "(":
            self.pos += 1
            children.append(self.node())
            while self.pos < len(self.text) and self.text[self.pos] == ",":
                self.pos += 1
                children.append(self.node())
            if self.pos >= len(self.text) or self.text[self.pos] != ")":
                raise ValueError("unclosed group")
            self.pos += 1
        return {"label": self.label(), "children": children}

    def parse(self):
        root = self.node()
        if self.pos >= len(self.text) or self.text[self.pos] != ";":
            raise ValueError("missing semicolon")
        self.pos += 1
        if self.pos != len(self.text):
            raise ValueError("trailing input")
        return root

def _clone(node):
    return {"label": node["label"], "children": [_clone(child) for child in node["children"]]}

def _index(root):
    nodes, parents, depths = {}, {}, {}
    def visit(node, parent, depth):
        label = node["label"]
        if label in nodes:
            raise ValueError("duplicate label")
        nodes[label], parents[label], depths[label] = node, parent, depth
        for child in node["children"]:
            visit(child, label, depth + 1)
    visit(root, None, SETTINGS["depth_origin"])
    return nodes, parents, depths

def _tree_text(node):
    children = list(node["children"])
    if PROFILE["child_order"] == "reverse":
        children.reverse()
    body = ""
    if children:
        body = "(" + ",".join(_tree_text(child) for child in children) + ")"
    return body + node["label"]

def _render(node):
    return _tree_text(node) + (";" if SETTINGS["terminal_semicolon"] else "")

def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))

def _height(node):
    return 0 if not node["children"] else 1 + max(_height(child) for child in node["children"])

def _lineage(label, parents):
    result = []
    while label is not None:
        result.append(label)
        label = parents[label]
    return result

def _path(a, b, parents):
    left, right = _lineage(a, parents), _lineage(b, parents)
    right_set = set(right)
    common = next(label for label in left if label in right_set)
    return left[:left.index(common) + 1] + list(reversed(right[:right.index(common)]))

def _prune(node, target):
    if not node["children"]:
        return None if node["label"] == target else node
    kept = []
    for child in node["children"]:
        child = _prune(child, target)
        if child is not None:
            kept.append(child)
    node["children"] = kept
    if SETTINGS["collapse_unary"] and len(node["children"]) == 1:
        return node["children"][0]
    return node

def run(argv, stdin):
    try:
        root = _Parser(stdin).parse()
        nodes, parents, depths = _index(root)
        if not argv:
            raise ValueError("missing command")
        command, args = argv[0], argv[1:]
        if command == "canonical" and not args:
            value = _render(root)
        elif command == "leaves" and not args:
            labels = [label for label, node in nodes.items() if not node["children"]]
            if SETTINGS["leaf_order"] == "sorted":
                labels.sort()
            value = _json(labels)
        elif command == "stats" and not args:
            leaf_count = sum(not node["children"] for node in nodes.values())
            value = _json({"internal_nodes": len(nodes) - leaf_count, "leaves": leaf_count,
                           "max_depth": max(depths.values()), "nodes": len(nodes)})
        elif command == "depth" and len(args) == 1:
            value = str(depths[args[0]])
        elif command == "height" and len(args) == 1:
            value = str(_height(nodes[args[0]]))
        elif command in ("lca", "distance", "path") and len(args) == 2:
            route = _path(args[0], args[1], parents)
            if command == "lca":
                right = set(_lineage(args[1], parents))
                value = next(label for label in _lineage(args[0], parents) if label in right)
            elif command == "distance":
                value = str(len(route) - 1 if SETTINGS["distance_unit"] == "edges" else len(route))
            else:
                value = _json(route)
        elif command == "rename" and len(args) == 2:
            if args[1] in nodes:
                raise ValueError("duplicate label")
            nodes[args[0]]["label"] = args[1]
            value = _render(root)
        elif command == "prune" and len(args) == 1:
            if nodes[args[0]]["children"]:
                raise ValueError("not a leaf")
            root = _prune(_clone(root), args[0])
            if root is None:
                raise ValueError("empty tree")
            value = _render(root)
        elif command == "subtree" and len(args) == 1:
            value = _render(nodes[args[0]])
        elif command == "rotate" and len(args) == 1:
            nodes[args[0]]["children"].reverse()
            value = _render(root)
        else:
            raise ValueError("invalid command")
        return {"exit_code": 0, "stdout": value + "\n", "stderr": ""}
    except (KeyError, StopIteration, ValueError) as error:
        return {"exit_code": 2, "stdout": "", "stderr": str(error) + "\n"}
'''


def compile_reference(truth, profile_index=0):
    """Return a self-contained correct implementation for offline validation."""
    return (
        "SETTINGS = " + repr(truth["settings"]) + "\n"
        + "PROFILE = " + repr(truth["profiles"][profile_index]) + "\n"
        + CANDIDATE_RUNTIME
    )


def _reference(truth, profile_index):
    namespace = {}
    exec(compile_reference(truth, profile_index), namespace)
    return namespace["run"]


def _cases():
    trees = (
        "((Q,B)QB,(M,A)MA)ROOT;",
        "(((K,C)KC,H)KCH,(Z,D)ZD)TOP;",
        "((R,(F,Y)FY)RFY,(N,E)NE)BASE;",
        "(((W,G)WG,(P,I)PI)LEFT,(T,S)RIGHT)ALL;",
        "((U,L)UL,((X,B)XB,V)XBV)ORIGIN;",
        "(((J,A)JA,(D,Q)DQ)JADQ,(M,C)MC)CENTER;",
    )
    labels = (
        ("Q", "A", "QB", "ROOT"),
        ("K", "D", "KC", "TOP"),
        ("F", "E", "FY", "BASE"),
        ("W", "S", "WG", "ALL"),
        ("U", "B", "XB", "ORIGIN"),
        ("J", "C", "JA", "CENTER"),
    )
    rows = []
    for index, (tree, (first, last, internal, root)) in enumerate(zip(trees, labels)):
        rows.extend(
            [
                (["canonical"], tree),
                (["leaves"], tree),
                (["stats"], tree),
                (["depth", first], tree),
                (["height", internal], tree),
                (["lca", first, last], tree),
                (["distance", first, last], tree),
                (["path", first, last], tree),
                (["rename", first, f"RENAMED{index}"], tree),
                (["prune", first], tree),
                (["subtree", internal], tree),
                (["rotate", root], tree),
            ]
        )
    return rows


def _world(setting, alternate_path=None):
    settings = deepcopy(BASE_SETTINGS)
    if alternate_path is not None:
        name, value = ALTERNATIVES[alternate_path]
        settings[name] = value
    profiles = [
        {"id": "deployed-A", "child_order": "input"},
        {
            "id": "deployed-B",
            "child_order": "reverse" if setting == "impossible" else "input",
        },
    ]
    truth = {
        "settings": settings,
        "profiles": profiles,
        "specifications": _specifications(settings),
    }
    probes = []
    for profile_index, profile in enumerate(profiles):
        reference = _reference(truth, profile_index)
        for argv, stdin in _cases():
            probes.append(
                {
                    "profile": profile["id"],
                    "argv": argv,
                    "stdin": stdin,
                    "expected": reference(argv, stdin),
                }
            )
    truth["probes"] = probes
    return truth


@lru_cache(maxsize=None)
def _fixed_world(setting):
    return _world(setting)


def _inputs(truth, population, distributed):
    common = {
        "/workspace/task.md": TASK,
        "/workspace/interface.md": INTERFACE,
        "/workspace/profiles.json": encoded(truth["profiles"]),
        "/workspace/examples.json": encoded(
            [
                {
                    "argv": ["stats"],
                    "stdin": "(B,A)ROOT;",
                    "result": {
                        "exit_code": 0,
                        "stdout": '{"internal_nodes":1,"leaves":2,"max_depth":1,"nodes":3}\n',
                        "stderr": "",
                    },
                },
                {
                    "argv": ["depth", "A"],
                    "stdin": "(B,A)ROOT;",
                    "result": {"exit_code": 0, "stdout": "1\n", "stderr": ""},
                },
            ]
        ),
    }
    groups = [{path: truth["specifications"][path]} for path in SPEC_PATHS]
    return allocate(common, groups, population, distributed)


def build(key, population):
    setting = variant(key, FAMILY)
    truth = deepcopy(
        _fixed_world("impossible" if setting == "impossible" else "possible")
    )
    startup = _inputs(truth, population, setting == "distributed")
    return (
        startup,
        truth,
        {
            "family": FAMILY,
            "variant": setting,
            "task_class": VARIANTS[setting],
            "domain": "Engineering",
            "task_version": VERSION,
            "global_task_sha256": digest(pooled(startup)),
            "output_paths": [OUTPUT, REVIEW],
            "difficulty_status": "requires_solo_calibration",
            "benchmark_design": "MirrorCode-style reduced tree CLI reconstruction; not an official MirrorCode score",
        },
    )


def _invocations(truth):
    return [(row["argv"], row["stdin"]) for row in truth["probes"]]


def _conflicts(truth):
    width = len(truth["probes"]) // len(truth["profiles"])
    left, right = truth["probes"][:width], truth["probes"][width:]
    return [
        {
            "argv": a["argv"],
            "stdin": a["stdin"],
            "required_outputs": [a["expected"], b["expected"]],
        }
        for a, b in zip(left, right)
        if a["argv"] == b["argv"]
        and a["stdin"] == b["stdin"]
        and a["expected"] != b["expected"]
    ]


def witness(key, startup, truth):
    expected, expected_truth, _ = build(key, len(startup))
    exact = startup == expected and truth == expected_truth
    matches = []
    for index, profile in enumerate(truth["profiles"]):
        reference = _reference(truth, index)
        matches.extend(
            reference(row["argv"], row["stdin"]) == row["expected"]
            for row in truth["probes"]
            if row["profile"] == profile["id"]
        )
    setting = variant(key, FAMILY)
    conflicts = _conflicts(truth)
    checks = []
    if setting == "distributed":
        alternatives = {}
        for actor, files in startup.items():
            missing = next(path for path in SPEC_PATHS if path not in files)
            if missing not in alternatives:
                alternate = _world("possible", missing)
                alternatives[missing] = (
                    alternate,
                    _inputs(alternate, len(startup), True),
                )
            alternate, alternate_inputs = alternatives[missing]
            checks.append(
                {
                    "actor": actor,
                    "same_local_view": files == alternate_inputs[actor],
                    "same_probe_invocations": _invocations(truth)
                    == _invocations(alternate),
                    "answer_changes": [row["expected"] for row in truth["probes"]]
                    != [row["expected"] for row in alternate["probes"]],
                    "pooled_feasible": not _conflicts(alternate),
                }
            )
    dependence = all(
        all(value for name, value in row.items() if name != "actor")
        for row in checks
    )
    return {
        "passed": exact
        and all(matches)
        and dependence
        and (bool(conflicts) if setting == "impossible" else not conflicts),
        "model_calls": 0,
        "reference_matches_protected_cases": all(matches),
        "pooled_feasible": not conflicts,
        "conflicts": conflicts,
        "foreign_information_checks": checks,
    }


def review(truth, report):
    """Validate a concrete profile contradiction, never infer one from failure."""
    if not isinstance(report, dict) or report.get("feasible") is not False:
        return False
    rows = report.get("conflicts", [])
    for row in rows if isinstance(rows, list) else []:
        try:
            values = [
                _reference(truth, index)(row["argv"], row["stdin"])
                for index in range(len(truth["profiles"]))
            ]
            if values[0] != values[1] and row["required_outputs"] == values:
                return True
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return False


def outcome(key, snapshots, truth):
    from swarmform.artifact_runner import execute_tree_cli

    variant(key, FAMILY)
    results, cache = {}, {}
    for actor, files in snapshots.items():
        source = files.get(OUTPUT)
        if source:
            if source not in cache:
                cache[source] = execute_tree_cli(source, truth["probes"])
            execution = cache[source]
        else:
            execution = {
                "complete": False,
                "missing": True,
                "correct_cases": 0,
                "total_cases": len(truth["probes"]),
            }
        try:
            report = json.loads(files.get(REVIEW, "{}"))
        except (ValueError, TypeError):
            report = {}
        results[actor] = {
            "task_satisfied": execution["complete"],
            "quality": execution["correct_cases"] / execution["total_cases"],
            "infeasibility_supported": review(truth, report),
            "execution": execution,
        }
    return results
