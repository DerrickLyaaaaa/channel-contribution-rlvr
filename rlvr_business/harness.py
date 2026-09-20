"""Framework-neutral adapter; keep this instance in the trusted harness process."""
from .environment import BusinessEnvironment
from .task import task_prompt
from .verification import evaluate
from .config import RULES


def _tool(name, description, properties=None, required=None):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties or {},
                           "required": required or [], "additionalProperties": False}}}


_IDS = {"type": "array", "items": {"type": "string"}, "minItems": 1,
        "maxItems": RULES.max_batch, "uniqueItems": True}
_DATE = {"type": "string", "format": "date", "description": "ISO YYYY-MM-DD"}
TOOLS = [
    _tool("list_channels", "List business channels and metadata in a region.",
          {"region": {"type": "string", "enum": ["east", "west"]}}, ["region"]),
    _tool("get_channel_policy", "Get accounting recognition rules, fee rates and investment eligibility gates."),
    _tool("list_orders", "Paginated order cohort. start inclusive, end exclusive. Continue until next_cursor is null.",
          {"channel_ids": _IDS, "start": _DATE, "end": _DATE,
           "status": {"type": "string", "enum": ["paid", "cancelled"], "default": "paid"},
           "cursor": {"type": "integer", "minimum": 0, "default": 0}}, ["channel_ids", "start", "end"]),
    _tool("list_refunds", "Refund events for order IDs through as_of inclusive. Includes pending events; examine status.",
          {"order_ids": _IDS, "as_of": _DATE}, ["order_ids", "as_of"]),
    _tool("list_fulfillment_costs", "Signed fulfillment ledger through as_of inclusive. Includes draft entries; examine status.",
          {"order_ids": _IDS, "as_of": _DATE}, ["order_ids", "as_of"]),
    _tool("campaign_dashboard", "Advertising attribution dashboard; not an accounting ledger."),
    _tool("platform_gmv_dashboard", "Consumer GMV leaderboard, includes unpaid orders and does not deduct refunds or costs."),
    _tool("inventory_snapshot", "Warehouse inventory snapshot."),
]


class Episode:
    def __init__(self, seed=0):
        self.prompt = task_prompt(seed)
        self._env = BusinessEnvironment(seed)

    def step(self, tool_name, arguments=None):
        return self._env.call(tool_name, arguments)

    def grade(self, final_result):
        return evaluate(self.prompt, final_result)

    def close(self):
        self._env.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
