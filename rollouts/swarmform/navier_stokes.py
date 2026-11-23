"""A matched incompressible-flow solver-repair task."""

import json

from .triplets import encoded, pooled


DOMAIN = "Scientific Computing"
VERSION = "freeform-navier-stokes-v1"
ROOT = "/workspace/"

TASK = """Incompressible-flow solver repair

The numerical methods group inherited a small two-dimensional incompressible
Navier–Stokes solver. Repair the supplied implementation and produce a
reproducible validation package for the prescribed periodic vortex and
lid-driven cavity cases. The package must include executable code, residual
and divergence diagnostics, a convergence table, and a short technical report.
Use only the supplied records and the tools already installed in the
workstation. The final result must be independently rerunnable from the files
in /workspace.
"""

SOLVER_README = """Solver handover

The starter implementation uses a finite-difference projection method on a
uniform two-dimensional grid. A valid submission must retain the input/output
file format, implement the pressure projection, report the maximum discrete
divergence, and record the grid and time-step refinement used for each case.
The supplied checker compares the periodic vortex against its analytic decay
and the cavity against the tabulated centre-line reference.
"""

STARTER = '''"""Starter projection solver. Replace the marked numerical step."""


def advance(state, dt, viscosity, spacing):
    """Return the next velocity and pressure fields."""
    # The inherited routine reads the fields and writes a checkpoint, but its
    # projection step is intentionally incomplete. Keep this public signature.
    raise NotImplementedError("complete the projection step")


def diagnostics(state, spacing):
    """Return max divergence and kinetic energy for a checkpoint."""
    raise NotImplementedError("implement the discrete diagnostics")
'''

RUNNER = """The checker is invoked as `python validation/check.py --case all`.
It reads solver output from /workspace/output and writes
/workspace/validation/report.json. A passing report contains one row per grid
and time-step setting, the maximum divergence, the vortex error and the cavity
centre-line error.
"""

MESH = {
    "periodic_vortex": {"domain": [0.0, 6.283185307179586, 0.0, 6.283185307179586],
                        "grids": [24, 48, 96], "final_time": 0.5},
    "lid_driven_cavity": {"domain": [0.0, 1.0, 0.0, 1.0],
                          "grids": [32, 64, 128], "reynolds": 1000},
}

PHYSICS = {
    "equations": "2D incompressible Navier–Stokes",
    "density": 1.0,
    "viscosity": 0.001,
    "incompressible": True,
    "prescribed_net_flux": 0.0,
    "boundary": {"periodic_vortex": "periodic", "lid_driven_cavity": "no-slip walls with a unit-speed lid"},
}

TAYLOR_GREEN = """case,time,kinetic_energy,decay_factor
periodic_vortex,0.00,0.2500000000,1.0000000000
periodic_vortex,0.10,0.2490019987,0.9960079893
periodic_vortex,0.25,0.2462680102,0.9851096480
periodic_vortex,0.50,0.2426122639,0.9704490556
"""

# These samples use the Re=1000 column of the canonical Ghia et al.
# driven-cavity reference. The checker uses tolerances that require
# convergence across the supplied grids.
CAVITY_REFERENCE = """line,position,value
vertical_u,0.0000,0.00000
vertical_u,0.1719,-0.38289
vertical_u,0.5000,-0.06080
vertical_u,0.8516,0.33304
vertical_u,1.0000,1.00000
horizontal_v,0.0000,0.00000
horizontal_v,0.1563,0.37095
horizontal_v,0.5000,0.02526
horizontal_v,0.9063,-0.51550
horizontal_v,1.0000,0.00000
"""

ACCEPTANCE = {
    "max_divergence": 1e-8,
    "periodic_vortex_relative_error": 2.5e-2,
    "cavity_reference_error": 5e-2,
    "requires_refinement": True,
    "periodic_net_flux": 0.0,
}


def _files(impossible):
    common = {
        ROOT + "task.md": TASK,
        ROOT + "solver/README.md": SOLVER_README,
        ROOT + "solver/starter.py": STARTER,
        ROOT + "validation/README.md": RUNNER,
    }
    groups = [
        ({ROOT + "inputs/mesh.json": encoded(MESH)},
         {ROOT + "inputs/physics.json": encoded(PHYSICS)}),
        ({ROOT + "references/taylor_green.csv": TAYLOR_GREEN},
         {ROOT + "references/cavity_centerline.csv": CAVITY_REFERENCE}),
        ({ROOT + "validation/acceptance.json": encoded(ACCEPTANCE)},
         {ROOT + "validation/format.txt": "JSON rows: case, grid, dt, max_divergence, error\n"}),
    ]
    if impossible:
        broken_physics = dict(PHYSICS)
        broken_physics["prescribed_net_flux"] = 0.25
        groups[0] = ({ROOT + "inputs/mesh.json": encoded(MESH)},
                     {ROOT + "inputs/physics.json": encoded(broken_physics)})
    truth = {"mesh": MESH, "physics": PHYSICS, "acceptance": ACCEPTANCE,
             "task": "navier_stokes_solver_repair"}
    return common, tuple(groups), truth


def inputs(impossible):
    return _files(impossible)


def build(key, population):
    family, variant = key.rsplit("-", 1)
    if family != "navier_stokes" or variant not in ("possible", "distributed", "impossible"):
        raise ValueError(key)
    if population < (2 if variant == "distributed" else 1):
        raise ValueError("A distributed instance needs distinct holders")
    common, groups, truth = _files(variant == "impossible")
    actors = tuple(f"Research{i:02d}" for i in range(1, population + 1))
    width = min(population, len(groups))
    startup = {}
    for index, actor in enumerate(actors):
        files = dict(common)
        for group_number, pair in enumerate(groups):
            for offset, half in enumerate(pair):
                if variant != "distributed" or (group_number + offset) % width == index % width:
                    files.update(half)
        startup[actor] = files
    return startup, truth, {
        "domain": DOMAIN,
        "family": family,
        "task_class": {"possible": "possible", "distributed": "information-dependent",
                        "impossible": "impossible"}[variant],
        "freeform": True,
        "input_version": VERSION,
    }


def _incompatible(files):
    physics = json.loads(files[ROOT + "inputs/physics.json"])
    return (physics.get("prescribed_net_flux") != 0.0 and
            physics.get("incompressible") and
            physics["boundary"]["periodic_vortex"] == "periodic")


def witness(key, startup, truth):
    variant = key.rsplit("-", 1)[1]
    complete, expected_groups, expected_truth = _files(False)
    complete_files = dict(complete)
    for pair in expected_groups:
        for half in pair:
            complete_files.update(half)
    union = pooled(startup)
    common_paths = set(complete)
    group_paths = [{path for half in pair for path in half} for pair in expected_groups]
    local_groups = {
        actor: sum(group <= set(files) for group in group_paths)
        for actor, files in startup.items()
    }
    same_task = truth == expected_truth
    pooled_complete = union == complete_files or (
        variant == "impossible" and
        set(union) == set(complete_files) and
        all(union[path] == complete_files[path] for path in complete_files
            if path != ROOT + "inputs/physics.json")
    )
    if variant == "distributed":
        passed = same_task and pooled_complete and all(value < len(group_paths) for value in local_groups.values())
    elif variant == "impossible":
        passed = same_task and _incompatible(union)
    else:
        passed = same_task and pooled_complete and all(value == len(group_paths) for value in local_groups.values())
    return {
        "passed": passed,
        "variant": variant,
        "pooled_equals_possible": pooled_complete,
        "local_group_counts": local_groups,
        "incompatibility_witness": _incompatible(union),
        "task": "navier_stokes_solver_repair",
    }


def matches(files, truth):
    """Return accepted output identifiers when a later log contains them."""
    return []
