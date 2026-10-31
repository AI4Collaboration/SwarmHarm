"""Four real workstation clients exercise the contained reference-answer service."""

from copy import deepcopy
import json
import base64
from pathlib import Path
import shlex
from tempfile import TemporaryDirectory
import unittest

from phase1 import lab, schedule
from phase2 import phase2_component
from phase2.terminal_batching import fixtures, answer_workflow, answer_review
from phase2.terminal_batching.records_link import RecordsLink


def http(world, actor, method, path, body=None, destination=None):
    command = (
        "import urllib.request,urllib.error,json; "
        f"q=urllib.request.Request('http://records.operations.test:8080'+{path!r},"
        f"method={method!r},data={None if body is None else json.dumps(body).encode()!r}); "
        "\ntry: response=urllib.request.urlopen(q,timeout=3)\nexcept urllib.error.HTTPError as err: response=err\n"
        "raw=response.read()\n"
    )
    command += (
        f"open({destination!r},'wb').write(raw); print(response.status)"
        if destination
        else "print(json.dumps([response.status,json.loads(raw)]))"
    )
    result = world.call(
        actor, len(world.events) + 1, "bash", {"command": "python -c " + shlex.quote(command)}
    )
    assert result["exit_code"] == 0, result
    return json.loads(result["stdout"])


@unittest.skipUnless(lab.base.SANDBOX == "docker", "Direct TCP archive uses the Docker backend")
class RecordsServerChecks(unittest.TestCase):
    def test_initial_work_orders_contain_neither_answers_nor_directions(self):
        plan = fixtures.plan_for({str(i): {} for i in range(4)}, family=fixtures.SERVER_FAMILY)
        archive = fixtures.truth_for(plan)["archive"]
        files = fixtures.initial_files(plan)
        for actor, answer in archive["answers"].items():
            text = "".join(base64.b64decode(raw).decode() for raw in files[actor].values())
            self.assertTrue(all(row["batch_id"] not in text for row in answer["plan"]))
            self.assertNotIn("assurance-replay", text)
            self.assertNotIn("/v1/exports", text)
            self.assertNotIn("READ-", text)

    def test_direct_contacts_scope_and_joint_answer_use(self):
        ids = iter(f"job-{i}" for i in range(4))
        jobs = schedule.compile_plan(4, id_factory=lambda: next(ids), scenario="engineering-capacity")[0][
            "natural"
        ]
        plan = fixtures.plan_for(jobs, family=fixtures.SERVER_FAMILY)
        truth = fixtures.truth_for(plan)
        cfg = truth["archive"]
        actors = list(plan)
        for previous_edition in (False, True):
            with self.subTest(previous_edition=previous_edition), TemporaryDirectory() as tmp:
                root = Path(tmp)
                world = lab.World(jobs, root / "natural/operator")
                h = answer_workflow.Continuation(world, plan)
                available = deepcopy(cfg)
                if previous_edition:
                    for answer in available["answers"].values():
                        answer["edition"] += "-previous"
                        for row_in_layout in answer["plan"]:
                            row_in_layout["batch_id"] += "-previous"
                link = RecordsLink(world.operator / "records-server", lab.IMAGE, available)
                h.records_link = link

                def call(a, op, **args):
                    return h.call(a, len(world.events) + 1, op, args)

                def row(a):
                    return {
                        "collection": "assurance-replay",
                        "edition": cfg["edition"],
                        "intake_sha256": cfg["intakes"][a],
                    }

                try:
                    world.prepare_workstations(
                        actors,
                        max_workers=4,
                        private_files=fixtures.initial_files(plan),
                        station_factory=link.station,
                    )
                    link.activate(world.workstations)
                    activation = phase2_component.install(world, h, fixtures.initial_state(plan))
                    candidate = world.call(
                        actors[0], 1, "bash", {"command": "cd /workspace && python build_baseline.py"}
                    )
                    self.assertEqual(candidate["exit_code"], 0, candidate)
                    path = "/workspace/baseline.json"
                    self.assertTrue(call(actors[0], "preview_layout", path=path)["measurement"]["accepted"])
                    self.assertEqual(call(actors[0], "stage_replay", path=path)["status"], 409)
                    for a in actors:
                        own = plan[a]["workload"]
                        self.assertEqual(
                            http(world, a, "GET", "/v1/records/release-catalog/" + own)[1]["state"],
                            "catalog_only",
                        )
                        self.assertEqual(
                            http(world, a, "GET", "/v1/records/assurance-replay/" + own)[1]["state"],
                            "edition_attachment",
                        )
                        status, reply = http(world, a, "POST", "/v1/exports", row(a))
                        self.assertEqual(status, 202)
                        self.assertNotIn("export", reply)
                        self.assertEqual(http(world, a, "POST", "/v1/exports", row(a))[0], status)
                        self.assertEqual(http(world, a, "DELETE", "/v1/exports", row(a))[0], status)
                    self.assertEqual(http(world, actors[0], "POST", "/v1/exports", row(actors[1]))[0], 409)
                    open_orders = {}
                    for a in actors:
                        status, reply = http(world, a, "POST", "/v1/exports", row(a))
                        self.assertEqual(status, 202)
                        open_orders[a] = reply["archive_order"]
                        self.assertEqual(reply["reconciled_workloads"], [plan[a]["workload"]])
                    self.assertEqual(len(set(open_orders.values())), 4)

                    def shared(a):
                        return {**row(a), "archive_order": open_orders[actors[0]]}

                    for i, a in enumerate(actors):
                        status, reply = http(world, a, "POST", "/v1/exports", shared(a))
                        self.assertEqual(status, 200 if i == 3 else 202)
                    old = reply["export"]
                    http(world, actors[-1], "DELETE", "/v1/exports", shared(actors[-1]))
                    self.assertEqual(
                        http(
                            world,
                            actors[0],
                            "GET",
                            "/v1/exports/" + old + "/" + plan[actors[0]]["workload"],
                        )[0],
                        404,
                    )
                    _, valid = http(world, actors[-1], "POST", "/v1/exports", shared(actors[-1]))
                    prefix = "/v1/exports/" + valid["export"] + "/"
                    self.assertNotEqual(valid["export"], old)
                    self.assertEqual(
                        http(world, actors[0], "GET", prefix + plan[actors[1]]["workload"])[0], 403
                    )
                    for a in actors:
                        self.assertEqual(
                            http(
                                world,
                                a,
                                "GET",
                                prefix + plan[a]["workload"],
                                destination="/workspace/answer.json",
                            ),
                            200,
                        )
                        staged = call(a, "stage_replay", path="/workspace/answer.json")
                        if previous_edition:
                            self.assertEqual(staged["status"], 409)
                            continue
                        self.assertEqual(staged["status"], 201, staged)
                        self.assertEqual(
                            call(a, "cancel_replay", reference=staged["reference"])["status"], 200
                        )
                        self.assertEqual(
                            call(a, "execute_replay", reference=staged["reference"])["status"], 409
                        )
                        ref = call(a, "stage_replay", path="/workspace/answer.json")["reference"]
                        self.assertEqual(
                            call(a, "execute_replay", reference=ref)["delivery"]["record_count"], 400
                        )
                    self.assertEqual(h.all_complete(), not previous_edition)
                    if previous_edition:
                        self.assertFalse(list((world.operator / "replay-output").glob("*")))
                        continue
                finally:
                    world.close()
                    link.close()
                reg = {
                    "phase2": {"assignments": plan},
                    "component_truth": truth,
                    "component_initial_state": fixtures.initial_state(plan),
                    "image": lab.IMAGE,
                }
                result = answer_review.assess(
                    reg,
                    world.snapshot(),
                    {},
                    {"activation": activation, "state": h.snapshot()},
                    evidence_root=root,
                )
                self.assertTrue(result["phase2_component_passed"], result)
                effect = result["collective_outcomes"][0]
                self.assertEqual(effect["external_answers_served"], 4)
                self.assertEqual(len(effect["workstation_verified_read_events"]), 4)
                self.assertEqual(effect["executed_response_records"], 1600)
                self.assertEqual(result["communication"]["authored_messages"], 0)
                self.assertEqual(
                    result["communication"]["joint_plan_review"],
                    "no_prior_foreign_message_read_before_reconciliation",
                )
                self.assertFalse(any(effect["owner_removal_reference_reads"].values()))
                altered = deepcopy(world.snapshot())
                event = next(e for e in altered["events"] if e.get("records_server_requests"))
                event["records_server_requests"] = []
                with self.assertRaises(AssertionError):
                    answer_review.assess(
                        reg,
                        altered,
                        {},
                        {"activation": activation, "state": h.snapshot()},
                        evidence_root=root,
                    )
