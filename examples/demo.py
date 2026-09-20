"""Example deterministic agent. Its only data source is the supplied API callback."""
import copy
import json
from decimal import Decimal, ROUND_HALF_UP
from rlvr_business import BusinessEnvironment, task_prompt, evaluate
from rlvr_business.config import RULES
from rlvr_business.task import task_id


def solve(call, seed=0):
    def api(name, **args):
        response = call(name, args)
        if not response["ok"]:
            raise RuntimeError(response["error"])
        return response["data"]

    channels = api("list_channels", region=RULES.region)
    policy = api("get_channel_policy")
    orders, cursor = [], 0
    while cursor is not None:
        page = api("list_orders", channel_ids=[c["channel_id"] for c in channels],
                   start=RULES.start, end=RULES.end, status="paid", cursor=cursor)
        orders.extend(page["items"])
        cursor = page["next_cursor"]
    refunds, costs = [], []
    ids = [o["id"] for o in orders]
    for offset in range(0, len(ids), RULES.max_batch):
        batch = ids[offset:offset+RULES.max_batch]
        refunds.extend(api("list_refunds", order_ids=batch, as_of=RULES.cutoff))
        costs.extend(api("list_fulfillment_costs", order_ids=batch, as_of=RULES.cutoff))
    rows = []
    for channel in channels:
        cid = channel["channel_id"]
        cohort = [o for o in orders if o["channel_id"] == cid]
        keys = {o["id"] for o in cohort}
        gross = sum(o["gross_cents"] for o in cohort)
        refund = sum(r["amount_cents"] for r in refunds if r["order_id"] in keys and r["status"] == "confirmed")
        cost = sum(c["amount_cents"] for c in costs if c["order_id"] in keys and c["status"] == "booked")
        net = gross - refund
        fee = int((Decimal(net) * Decimal(policy["fee_bps"][cid]) / 10000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        contribution = net - cost - fee
        eligible = (len(cohort) >= policy["min_orders"] and gross > 0 and
                    refund * 10000 <= gross * policy["max_refund_bps"] and contribution > 0)
        rows.append(dict(channel_id=cid, order_count=len(cohort), gross_cents=gross, refund_cents=refund,
                         net_cents=net, cost_cents=cost, fee_cents=fee, contribution_cents=contribution, eligible=eligible))
    selected = sorted([r for r in rows if r["eligible"]], key=lambda r: (-r["contribution_cents"], r["channel_id"]))[:RULES.top_k]
    return dict(task_id=task_id(seed), channels=rows, ranking=[r["channel_id"] for r in selected],
                total_contribution_cents=sum(r["contribution_cents"] for r in selected))


def main():
    prompt = task_prompt(0)
    with BusinessEnvironment(0) as env:
        calls = []
        def tracked_call(name, args):
            calls.append(name)
            return env.call(name, args)
        answer = solve(tracked_call)
        print(json.dumps({"api_calls": calls, "correct_answer": answer}, ensure_ascii=False, indent=2))
        wrong = copy.deepcopy(answer)
        # Common business error: treat all June receipts as net revenue (ignore refunds).
        for row in wrong["channels"]:
            row["net_cents"] = row["gross_cents"]
            row["refund_cents"] = 0
        reversed_rank = copy.deepcopy(answer)
        reversed_rank["ranking"].reverse()
        wrong_selection = copy.deepcopy(answer)
        wrong_selection["ranking"] = ["C01", "C03"]
        cases = {"correct": answer, "wrong_refunds": wrong,
                 "reversed_ranking": reversed_rank, "wrong_selection": wrong_selection,
                 "malformed": "not JSON"}
        for name, result in cases.items():
            report = evaluate(prompt, result)
            print(json.dumps({"scenario": name, **report}, ensure_ascii=False))
            assert report["success"] == (name == "correct")
        print(json.dumps({"invalid_api_example": env.call("execute_sql", {"sql": "SELECT * FROM orders"})}))


if __name__ == "__main__":
    main()
