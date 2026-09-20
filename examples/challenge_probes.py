"""Deterministic faulty strategies: show that business traps change final rewards."""
import copy
import json
from .demo import solve
from rlvr_business import BusinessEnvironment, task_prompt, evaluate


def run_probes():
    reports = {}
    for strategy in ("correct", "june_only_refunds", "include_pending", "gmv_ranking", "ignore_gate"):
        with BusinessEnvironment() as env:
            def call(name, arguments):
                arguments = dict(arguments)
                if strategy == "june_only_refunds" and name == "list_refunds":
                    arguments["as_of"] = "2026-06-30"
                response = env.call(name, arguments)
                if strategy == "include_pending" and name == "list_refunds" and response["ok"]:
                    response = copy.deepcopy(response)
                    for row in response["data"]:
                        row["status"] = "confirmed"
                return response
            answer = solve(call)
            if strategy in ("gmv_ranking", "ignore_gate"):
                if strategy == "gmv_ranking":
                    answer["ranking"] = env.call("platform_gmv_dashboard")["data"]["ranking"][:2]
                else:
                    answer["ranking"] = [r["channel_id"] for r in sorted(answer["channels"], key=lambda r: -r["contribution_cents"])[:2]]
                answer["total_contribution_cents"] = sum(r["contribution_cents"] for r in answer["channels"] if r["channel_id"] in answer["ranking"])
            reports[strategy] = evaluate(task_prompt(), answer)
    return reports


if __name__ == "__main__":
    print(json.dumps(run_probes(), ensure_ascii=False, indent=2))
