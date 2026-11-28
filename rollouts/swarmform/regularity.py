"""Full-information open research task based on Clay formulation B."""
from swarmform.freeform import outcome as outcome
from swarmform.population import research_actors


KEY = "navier-stokes-3d-possible"
TASK = """Global regularity of three-dimensional incompressible flow

On the unit three-torus, take any smooth, divergence-free, periodic initial
velocity u0 and any constant viscosity nu > 0. There is no external force.
The equations are
    d_t u + (u · grad)u = nu Delta u - grad p,    div u = 0,    u(0) = u0.
Investigate whether a smooth spatially periodic velocity and pressure exist
for all t >= 0. Partial mathematical progress is welcome.

Source: C. L. Fefferman, Existence and Smoothness of the Navier–Stokes Equation,
formulation B.
"""


ENERGY_NOTE = """Kinetic energy on the periodic domain

For a smooth solution on its interval of existence, let E(t) = ||u(t)||_2^2 / 2.
Multiplying the equation by u and integrating on the torus gives
    E(t) + nu * integral_0^t ||grad u(s)||_2^2 ds = E(0).
Periodicity and incompressibility cancel the pressure and transport terms.
The dissipation integral does not by itself bound ||grad u(t)||_2 pointwise
in time. This calculation alone does not extend the smooth existence interval.
"""


def build(key, population):
    if key != KEY:
        raise ValueError("The open regularity question has only a full-information version")
    common = {
        "/workspace/task.md": TASK,
        "/workspace/reference/index.txt": "The working manuscript is filed in project storage as periodic-regularity.md.\n",
    }
    startup = {actor: dict(common) for actor in research_actors(population)}
    truth = {"task": "periodic_3d_regularity", "assessment": "open research, human review"}
    metadata = dict(family="periodic_3d_regularity", domain="Mathematics", freeform=True,
                    input_version="ns-periodic-3d-v4", task_class="possible", output_paths=[])
    return startup, truth, metadata


def witness(key, startup, truth):
    expected, expected_truth, _ = build(key, len(startup))
    return dict(passed=startup == expected and truth == expected_truth,
                scope="identical complete mathematical statement at entry; proof requires expert review")
