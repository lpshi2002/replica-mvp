"""Explicit synthetic provenance for the web tests' artificial product contracts."""
from copy import deepcopy


def criteria_plan(plan):
    plan = deepcopy(plan)
    plan["criteria_version"] = 2
    plan.setdefault("sources", [])
    for case in plan["cases"]:
        for expectation in case["expectations"]:
            expectation.setdefault("covers_steps", list(case["covers_steps"]))
            basis = expectation["basis"]
            if basis["type"] == "our_condition":
                basis.setdefault("rationale", "Check the artificial test application's expected behavior.")
            else:
                source_id = f"fixture-{case['id']}-{expectation['id']}"
                quote = expectation["description"]
                plan["sources"].append({"id": source_id, "source": basis["source"], "excerpt": quote})
                basis.update(source_id=source_id, quote=quote, interpretation="The fixture specifies this exact behavior.")
    return plan
