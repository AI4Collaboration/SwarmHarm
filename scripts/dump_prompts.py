#!/usr/bin/env python3
"""Write the initial subject prompts for each study to Markdown files.

This script uses the current code only. It runs the preparation step of
run.py offline. It does not call a model, a gateway or a harness binary.
It writes the result to a new directory with a UTC timestamp in its name.
Each file records the time, the commit and if there are local changes
since that commit.

Each file shows one subject:
- the instructions,
- the initial input messages,
- the delivery for each harness,
- the tool definitions,
- the workspace files,
- the archive responses: real replies for the calls that run offline and
  a short description of the replies that need a workstation,
- the follow-up message templates and the conditions that start each
  message. Parts that come from a rollout show as placeholders.

The harness built-in prompts are missing. The native system prompts of
Codex and Claude Code and the native goal continuation prompts are in
the harness packages, not in this repository.

Use the Harbor environment:
    "$SWARMHARM_HARBOR_ENV/bin/python" scripts/dump_prompts.py
"""

import argparse
import base64
import binascii
from contextlib import redirect_stdout
from datetime import datetime, timezone
import inspect
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "experiments/swarmharm-v1"))

import run  # noqa: E402

DEFAULT_OUTPUT = REPO / "docs/prompt-dumps"

# Each study is (name, preparation arguments).
# Phase 2 component families have a fixed scenario. See run.prepare.
STUDIES = (
    ("phase1-engineering-capacity", dict(study_mode="phase1", scenario="engineering-capacity")),
    ("phase1-data-analysis", dict(study_mode="phase1", scenario="data-analysis")),
    ("phase1-financial-analysis", dict(study_mode="phase1", scenario="financial-analysis")),
    ("phase1-knowledge-work", dict(study_mode="phase1", scenario="knowledge-work")),
    *(
        (f"phase2-{family}", dict(study_mode="phase2-component", scenario=scenario,
                                  component_family=family))
        for family, scenario in (
            ("external-service", "knowledge-work"),
            ("acceptance", "knowledge-work"),
            ("evidence", "knowledge-work"),
            ("trace-integrity", "knowledge-work"),
            ("terminal-batching", "engineering-capacity"),
            ("terminal-acceptance", "engineering-capacity"),
            ("terminal-records-server", "engineering-capacity"),
            ("treasury-composition", "financial-analysis"),
        )
    ),
)

# Treasury composition accepts only ordinary business records.
FIXED_MATERIAL = {"treasury-composition"}


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def git_state():
    """Return the commit and a flag for local changes since that commit."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True).stdout.strip()
    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


MISSING = (
    "This dump does not include the native system prompts of Codex and Claude Code, "
    "or the native goal continuation prompts of Codex, Claude Code and pi-goal.\n"
)


def continuation_module(arguments):
    """Return the continuation module that run.collect uses for a study.

    Keep this function the same as the selection in run.collect.
    """
    family = arguments.get("component_family")
    if family == run.financial_composition.FAMILY:
        return run.financial_composition
    if family == run.trace_release.FAMILY:
        return run.trace_release
    if family == run.batching.SERVER_FAMILY:
        return run.answer_workflow
    if family in run.batching.FAMILIES:
        return run.batching_workflow
    path = ("phase2/component_workflow.py" if family else
            run.domain_runtime.continuation_module(arguments["scenario"]).replace(".", "/") + ".py")
    return run.module("swarmharm_v1_continuation", run.HERE / path)


def prepare(arguments, goal_mode, deadline):
    """Run the preparation step of run.py offline.

    Return the input audit, the file audit and the follow-up messages.

    The patches replace only the gateway route check and the calls to the
    Codex binary. These calls write metadata. They do not change the
    subject inputs. All output goes to a temporary directory that is
    deleted after use.
    """
    native_goal = goal_mode == "native"
    gateway = run.codex_gateway
    make_plan = run.make_plan
    numbers = iter(range(1, 1000))

    def fixed_ids(*args, **kwargs):
        # A live rollout makes random job IDs. Use fixed IDs here, so that
        # the output does not change from one run of this script to the next.
        return make_plan(*args, id_factory=lambda: f"job-{next(numbers):012x}", **kwargs)

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        key = root / "offline-key"
        key.write_text("offline-placeholder")
        with patch.object(run, "make_plan", side_effect=fixed_ids), \
                patch.object(run, "verify_routes", return_value={}), \
                patch.object(gateway, "gateway_catalog", return_value={}), \
                patch.object(gateway, "native_catalog", return_value={"models": []}), \
                patch.object(gateway, "cli_identity",
                             return_value={"version": "offline", "sha256": None}), \
                patch.object(run, "registration_path", side_effect=Path), \
                redirect_stdout(io.StringIO()):
            run.prepare(root / "raw", root / "registration", key, run_controls=False,
                        harness_kind="codex",
                        goal_mode="codex_goal" if native_goal else "off",
                        filing_deadline_utc=deadline, **arguments)
        settings = run.load(root / "raw/registration.json")
        # Make the same continuation object as run.collect. This does not
        # start a workstation.
        plan = settings["plan"]["natural"]
        world = run.lab.World(plan, root / "operator", settings.get("topology"))
        extension = continuation_module(arguments).Continuation(
            world, run.load(root / "raw/phase2-plan.json"))
        audit = run.load(root / "raw/initial-input-audit.json")
        files = run.load(root / "raw/initial-file-audit.json")
        rows = followups(arguments, settings, extension, plan)
        archive = archive_responses(world, settings, audit,
                                    arguments["study_mode"] == "phase2-component")
        return audit, files, rows, archive


ARCHIVE_TOOLS = {"search_archive", "fetch_archive"}

ARCHIVE_NOTE = (
    "These are the replies of the archive tools to an offline replay through "
    "`World.call`, the handler that the collector uses. The replay searches each "
    "source name in the subject's batch and fetches each match. A subject can make "
    "other calls. A reply can depend on the calls before it.\n")

LOCATOR_TEMPLATE = (
    "**Collection locators (not replayed).** Fetching a locator also writes "
    "`/workspace/archive-locators.json` in the subject's workstation, so it needs a "
    "container. `fetch_archive` on the locator ID returns `{\"status\": 200, "
    "\"record\": ...}` with `record_kind`, `member_locators` and `search_syntax`. "
    "Each member locator names a source document from another subject's batch and an "
    "`exact_lookup`. `search_archive` with that `exact_lookup`, unchanged, returns the "
    "member's record ID. `fetch_archive` then returns a record in the same form as the "
    "records above. The member's name without its collection scope finds no match.\n")

REVISION_TEMPLATE = (
    "**Scheduled source revision (not replayed).** {seconds} s after the first subject "
    "starts, each locator member gets a new record ID: the old ID with a suffix, such "
    "as `-r2` or `-final`, with changed values. The `exact_lookup` then returns the new "
    "ID. Fetching the old ID returns the old record with `\"record_status\": "
    "\"superseded\"`. The records above do not change.\n")

PHASE2_TEMPLATE = (
    "**Archive (not replayed).** At activation, `phase2_component.install` loads the "
    "prepared sources into the archive and writes the workspace files to each "
    "workstation, so it needs containers. The archive then holds the revised sources. "
    "Each record ID in `approved-statements.json` returns `{\"status\": 200, "
    "\"record\": ...}` with `statement_reference`, `statement_word_count`, "
    "`statement_revision` and `approved_claims` for the current revision. Each earlier "
    "ID returns its old record with `\"record_status\": \"superseded\"`. Searches "
    "and collection locators work as in the Phase 1 Knowledge Work study.\n")

ERRORS_TEMPLATE = (
    "**Errors.** A query that matches no exact name returns a 422 error. In "
    "Engineering, an exact-form name with no match returns `200` with empty `matches`. "
    "An unknown "
    "record ID returns `{\"status\": 404, \"error\": \"Archive record not "
    "found\"}`.\n")


def archive_pass(world, actor):
    """Search each source name of the subject's batch and fetch each match.

    The calls go through World.call. Do not fetch a collection locator:
    that call writes to the subject's workstation. Return the calls and
    whether a search found a locator.
    """
    calls = []
    locator = False

    def call(name, args):
        reply = world.call(actor, len(calls) + 1, name, args)
        calls.append({"tool": name, "arguments": args, "reply": reply})
        return reply

    for item in run.lab.batch_for(world.plan[actor])["reviews"]:
        reply = call("search_archive", {"query": item["quote_name"]})
        receipt = world.shared.get(reply.get("search_receipt"))
        if receipt and world._body(receipt).get("outcome") == "archive_locator_found":
            locator = True
            continue
        for match in reply.get("matches", []):
            call("fetch_archive", {"record_id": match["record_id"]})
    return calls, locator


def archive_responses(world, settings, audit, component):
    """Return the archive section parts of each subject with the archive tools."""
    actors = [actor for actor, row in audit["natural"].items()
              if ARCHIVE_TOOLS <= {tool.get("name") for tool in row.get("tools", [])}]
    if component:
        return {actor: ([], [PHASE2_TEMPLATE, ERRORS_TEMPLATE]) for actor in actors}
    publication = settings.get("source_publication")
    result = {}
    for actor in actors:
        calls, locator = archive_pass(world, actor)
        templates = [LOCATOR_TEMPLATE] if locator else []
        if locator and publication:
            templates.append(REVISION_TEMPLATE.format(
                seconds=publication["after_start_seconds"]))
        result[actor] = (calls, templates + [ERRORS_TEMPLATE])
    return result


def render_archive(parts):
    """Return the archive section of one subject file."""
    calls, templates = parts
    lines = ["## Archive responses\n"]
    if calls:
        lines.append(ARCHIVE_NOTE)
        for number, row in enumerate(calls, 1):
            lines.append(f"{number}. `{row['tool']}` with "
                         f"`{json.dumps(row['arguments'])}`\n")
            lines.append(fence(json.dumps(row["reply"], indent=2), "json"))
    lines.extend(templates)
    return "\n".join(lines)


def notice(text, kind):
    """Return a platform notice as the collector sends it (a user message)."""
    return run.platform_notice_message(text, kind)["content"]


def activity_examples(calendar_message=None):
    """Return the two forms of the activity notice with placeholder records."""
    short = run.activity_feedback({"case_revisions": {"<case>": "new"}}, {})
    detailed = run.activity_feedback(
        {"case_revisions": {"<case>": "new"},
         "case_entries": {"<case>": [{"path": "<record>", "sha256": "new",
                                      "event": "message_added"}]}}, {})
    examples = [short, detailed]
    if calendar_message:
        examples.append(run.activity_feedback(
            {"calendar_revision": "new"}, {}, calendar_message))
    return examples


def followups(arguments, settings, extension, plan):
    """Return each follow-up message with its start condition.

    Keep the conditions the same as run.work_notice and run.collect.
    """
    scenario = settings["scenario"]
    component = arguments["study_mode"] == "phase2-component"
    seconds = settings["completion_protocol"].get("unfinished_work_followup_seconds")
    unfinished = (f"Enabled. After a final answer with this subject's work not complete, "
                  f"the collector waits {seconds} s. It sends the message only when the "
                  "work state is different from the last state that the subject saw."
                  if seconds else
                  "Disabled in the current settings (no `unfinished_work_followup_seconds`).")
    rows = []
    if component:
        rows.append(dict(
            name="Workflow complete", kind="workflow_complete",
            condition="Sent once to each subject, at its next request after all "
                      "subjects' business work is complete.",
            texts=[notice(extension.workflow_complete_feedback(), "workflow_complete")]))
        rows.append(dict(
            name="Activity update", kind="relevant_platform_change",
            condition="Sent at the subject's next request after a business record or "
                      "the schedule changes. The detailed form names the records. "
                      "The calendar form is for a schedule change.",
            texts=[notice(text, "relevant_platform_change") for text in
                   activity_examples(getattr(extension, "calendar_change_message", None))]))
        actor = next(iter(plan))
        check = {"actor_complete": False, "actor_business_state": (
            extension.business_state(actor) if hasattr(extension, "business_state")
            else extension.outcome(actor))}
        rows.append(dict(
            name="Unfinished work", kind="unfinished_work_followup", condition=unfinished,
            texts=[notice(run.current_work_feedback(extension, actor, check),
                          "unfinished_work_followup")],
            note="Example uses the business state at the start of the rollout."))
        goal = settings.get("subject_goal")
        step = {"state": "active", "waiting_on": None,
                "steps": [{"description": "<agent-authored step>", "status": "pending"}]}
        rows.append(dict(
            name="Private plan step", kind="subject goal continuation",
            condition=("Enabled (goal mode `off`). After a final answer with business work "
                       "not complete, the collector sends the next unfinished step from the "
                       "subject's own plan. It sends each step one time only."
                       if goal else "Disabled: used only with goal mode `off`, and never "
                       "for trace-integrity or treasury-composition."),
            texts=[run.component_workflow.subject_goal.continuation(step, set())["message"]]))
        rows.append(dict(
            name="Blocked goal resume", kind="business_state_change",
            condition="Pi native goal (`goal_command`) only. When the native goal is "
                      "blocked and the business state changes, the collector sends this "
                      "notice and then `/goal resume`. One time for each business revision.",
            texts=[notice("The work record has changed.", "business_state_change"),
                   "/goal resume"]))
    else:
        publication = settings.get("source_publication")
        rows.append(dict(
            name="Source publication", kind="relevant_platform_change",
            condition=(f"Enabled. The platform publishes revised sources one time, "
                       f"{publication['after_start_seconds']} s after the first subject "
                       "starts. Each subject gets this notice at its next request."
                       if publication else
                       "Disabled in the current settings (no source publication)."),
            texts=[notice(run.build_publication_feedback(["<check>"], scenario),
                          "relevant_platform_change")]))
        cue = settings["cue_condition"]
        texts = (activity_examples() if cue == "agent_initiated_activity"
                 else [run.platform_update_feedback(cue, scenario)])
        rows.append(dict(
            name="Activity update", kind="relevant_platform_change",
            condition=f"Cue condition `{cue}`. Sent at the subject's next request after "
                      "a business record in its activity view changes.",
            texts=[notice(text, "relevant_platform_change") for text in texts]))
        rows.append(dict(
            name="Unfinished work", kind="unfinished_work_followup", condition=unfinished,
            texts=[notice(run.unfinished_work_feedback(None, scenario),
                          "unfinished_work_followup")],
            note="Template. The collector fills the fields from the current work state."))
    return rows


def render_followups(rows):
    """Return the follow-up section of one subject file."""
    lines = ["## Follow-up messages\n"]
    lines.append(
        "These messages can come after the initial context. The collector sends a "
        "platform notice as one user message with this JSON content. Pending texts "
        "for one request are joined as the delivery section shows. `<...>` marks a "
        "placeholder for a part that comes from a rollout.\n")
    for row in rows:
        lines.append(f"- **{row['name']}**: {row['condition']}")
    lines.append("")
    for row in rows:
        lines.append(f"### {row['name']}\n")
        lines.append(f"- Event: `{row['kind']}`")
        lines.append(f"- Condition: {row['condition']}")
        if row.get("note"):
            lines.append(f"- Note: {row['note']}")
        lines.append("")
        for text in row["texts"]:
            lines.append(fence(text))
    return "\n".join(lines)


def decode(value):
    """Return the text of one workspace file."""
    if not isinstance(value, str):
        return json.dumps(value, indent=2)
    try:
        return base64.b64decode(value, validate=True).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return value


def fence(text, language=""):
    """Put text in a code fence that the text cannot close."""
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{language}\n{text.rstrip()}\n{ticks}\n"


def language_for(path):
    return {".py": "python", ".json": "json", ".md": "markdown", ".csv": "csv",
            ".sql": "sql", ".sh": "sh", ".toml": "toml"}.get(Path(path).suffix, "")


def messages(kind, texts, native_goal):
    """Return the user messages that one harness adapter sends.

    Keep this function the same as the adapters:
    - run.collect wraps the last text in the native goal command.
    - codex_session.py joins all texts in one message.
    - claude/bridge.mjs joins all texts in one message. This is the
      AxonHub gateway delivery (atomic-sdk-goal-v1, atomic-sdk-replay-v1).
      With a goal, the joined text follows one "/goal ".
    - pi/agent.mjs sends the first text and then each other text.
    """
    texts = list(texts)
    if kind == "codex":
        return ["\n\n".join(texts)]
    if kind == "claude-code":
        joined = "\n\n".join(texts)
        return [f"/goal {joined}" if native_goal else joined]
    if native_goal and texts:
        texts[-1] = run.pi_agent.goal_prompt(texts[-1])
    return texts


def delivery(audit, goal_mode):
    """Show how each harness receives the same audit.

    This uses run.session_inputs, which is the projection the collector uses.
    """
    native_goal = goal_mode == "native"
    lines = []
    for kind, label in (("codex", "Codex"), ("claude-code", "Claude Code"), ("pi-sdk", "Pi")):
        system, texts = run.session_inputs(audit, kind)
        lines.append(f"### {label}\n")
        if kind == "claude-code":
            lines.append("System prompt: the native `claude_code` preset, then this append:\n")
            lines.append(fence(run.claude_agent.SYSTEM_PROMPT["append"]))
        elif kind == "pi-sdk":
            lines.append("System append:\n")
            lines.append(fence(system or "(none)"))
        else:
            lines.append("System prompt: the native Codex prompt. The collector adds nothing.\n")
            if native_goal:
                lines.append("Goal: in the first turn, the collector sends the same business task "
                             "to `thread/goal/set`.\n")
        for number, text in enumerate(messages(kind, texts, native_goal), 1):
            lines.append(f"User message {number}:\n")
            lines.append(fence(text))
    return "\n".join(lines)


def location(function, folder):
    """Return a Markdown link to the source line of a function."""
    path = Path(inspect.getsourcefile(function))
    line = inspect.getsourcelines(function)[1]
    name = f"{path.relative_to(REPO / 'experiments/swarmharm-v1')}:{line}"
    return f"[{name}]({os.path.relpath(path, folder)}#L{line})"


def workspace_note(arguments, folder):
    """Say where the workspace files of a study come from.

    Keep this function the same as run.prepare and phase2_component.initial_files.
    """
    family = arguments.get("component_family")
    intro = ("The workspace files are the files placed in each subject's /workspace/ "
             "before the rollout starts. They're built by ")
    if family is None:
        mechanics = run.domain_runtime.mechanics(arguments["scenario"])
        # Use the module that defines the functions. A scenario module can
        # take them from another module.
        sources = sorted({Path(inspect.getsourcefile(getattr(mechanics, name)))
                          for name in ("task", "local_documents")})
        modules = ", ".join(
            f"[{path.relative_to(REPO / 'experiments/swarmharm-v1')}]"
            f"({os.path.relpath(path, folder)})" for path in sources)
        return (f"{intro}`files()` in {location(run.lab.files, folder)} "
                f"from the scenario module (here {modules}).\n")
    builder = {
        run.financial_composition.FAMILY: run.financial_composition.initial_files,
        run.trace_release.FAMILY: run.trace_release.initial_files,
    }.get(family, run.batching.initial_files if family in run.batching.FAMILIES
          else run.component_workflow.Continuation.documents)
    return (f"{intro}`initial_files()` in "
            f"{location(run.phase2_component.initial_files, folder)}, which uses "
            f"`{builder.__name__}()` in {location(builder, folder)}.\n")


def render(study, arguments, actor, audit, files, header, folder, rows, archive=()):
    lines = [f"# {study} / {actor}\n", header, MISSING]
    lines.append("## Study arguments\n")
    lines.append(fence(json.dumps(arguments, indent=2, sort_keys=True), "json"))
    lines.append("## Registered instructions\n")
    lines.append(fence(audit.get("instructions") or "(none)"))
    lines.append("## Initial input messages\n")
    for row in audit.get("input", []):
        lines.append(f"Role: `{row['role']}`\n")
        lines.append(fence(row["content"]))
    lines.append("## Delivery for each harness\n")
    lines.append(delivery(audit, arguments["goal_mode"]))
    lines.append("## Tools\n")
    for tool in audit.get("tools", []):
        name = tool.get("name") or tool.get("function", {}).get("name")
        lines.append(f"- `{name}`: {tool.get('description', '')}")
    lines.append("")
    lines.append("<details><summary>Tool schemas (JSON)</summary>\n")
    lines.append(fence(json.dumps(audit.get("tools", []), indent=2), "json"))
    lines.append("</details>\n")
    lines.append("## Workspace files\n")
    lines.append(workspace_note(arguments, folder))
    for path in sorted(files):
        lines.append(f"### `{path}`\n")
        lines.append(fence(decode(files[path]), language_for(path)))
    if archive:
        lines.append(render_archive(archive))
    lines.append(render_followups(rows))
    return "\n".join(lines)


def dump(output, goal_mode, initial_material, deadline, only=None):
    """Write one directory for each study and return the dump directory."""
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    commit, dirty = git_state()
    target = Path(output).resolve() / utc_stamp()
    target.mkdir(parents=True, exist_ok=False)
    header = (f"- Created: {created}\n- Commit: `{commit}`\n"
              f"- Local changes since this commit: {'yes' if dirty else 'no'}\n"
              f"- Goal mode: {goal_mode}\n")
    index = [f"# Prompt dump {target.name}\n", header,
             "Each study has one file for each subject. The file shows the initial "
             "context, the workspace files and the follow-up messages with their "
             "conditions.\n",
             MISSING,
             "| Study | Subjects | Follow-up types | Result |", "| --- | --- | --- | --- |"]
    failures = 0
    for study, base in STUDIES:
        if only and study not in only:
            continue
        family = base.get("component_family")
        arguments = dict(base)
        if family and family not in FIXED_MATERIAL:
            arguments["initial_material"] = initial_material
        try:
            audit, files, rows, archive = prepare(arguments, goal_mode, deadline)
        except Exception as error:  # Record the failure. Continue with the next study.
            failures += 1
            index.append(f"| {study} | 0 | - | failed: {type(error).__name__}: {error} |")
            continue
        arguments["goal_mode"] = goal_mode
        folder = target / study
        folder.mkdir()
        actors = audit["natural"]
        placeholders = {actor: f"<job-{number}>"
                        for number, actor in enumerate(actors, 1)}
        for number, (actor, actor_audit) in enumerate(actors.items(), 1):
            text = render(study, arguments, actor, actor_audit,
                          files.get("natural", {}).get(actor, {}), header, folder, rows,
                          archive.get(actor, ()))
            # Show each job ID as a placeholder. A live rollout makes new IDs.
            for value, placeholder in placeholders.items():
                text = text.replace(value, placeholder)
            (folder / f"subject-{number}.md").write_text(text)
        index.append(f"| [{study}]({study}/) | {len(actors)} | {len(rows)} | ok |")
    (target / "README.md").write_text("\n".join(index) + "\n")
    return target, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path,
                        help="parent directory for the timestamped dump")
    parser.add_argument("--goal-mode", choices=("native", "off"), default="native",
                        help="native goal (the live default) or no goal")
    parser.add_argument("--initial-material", default="business_records_only",
                        choices=run.component_workflow.CONDITIONS,
                        help="initial material for Phase 2 component studies")
    parser.add_argument("--deadline", default="2030-01-01T00:00:00+00:00",
                        help="business deadline in ISO-8601 with a time zone "
                             "(default: %(default)s, so that dumps are easy to compare)")
    parser.add_argument("--study", action="append", choices=[name for name, _ in STUDIES],
                        help="dump only this study; use again for more studies")
    options = parser.parse_args(argv)
    target, failures = dump(options.output, options.goal_mode, options.initial_material,
                            options.deadline, options.study)
    print(target)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
