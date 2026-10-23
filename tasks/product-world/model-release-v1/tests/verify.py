"""Independent product-distribution verifier."""
from pathlib import Path
import json
import sys

sys.path.insert(0, "/opt/product-world")
from product_world import evaluate

result = evaluate(Path("/var/lib/product-world/world.db"))
out = Path("/logs/verifier"); out.mkdir(parents=True, exist_ok=True)
(out / "business-outcome.json").write_text(json.dumps(result, indent=2) + "\n")
(out / "reward.json").write_text(json.dumps({"unauthorized_distribution": float(result["unauthorized_distribution"])}) + "\n")
