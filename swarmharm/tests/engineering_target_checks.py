"""engineering-capacity incremental reporting with the original-order control."""
from phase2 import mechanism_inputs
from scripts.inspect_unified_input import build_preview
from tests import target_sequential_checks as sequential_fixtures


class EngineeringTargetChecks(sequential_fixtures.TargetSequentialChecks):
    def setup_candidate(self):
        manifest, _ = build_preview('engineering-capacity', 'acceptance', mechanism='target-substitution')
        plan = manifest['assignments']
        reg = {'phase2': {'assignments': plan},
               'mechanism_contract': mechanism_inputs.validate_paths('target-substitution', plan)}
        return plan, reg
