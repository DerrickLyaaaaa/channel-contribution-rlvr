"""Allowlisted, read-only business APIs. No raw SQL or database handle is exposed."""
from datetime import date
import sqlite3
from ..config import RULES
from ..task import task_prompt
from .data import build_database


class BusinessEnvironment:
    def __init__(self, seed: int = 0):
        task_prompt(seed)  # validate before constructing any state
        self.__db = build_database(seed)
        self.__closed = False

    def close(self):
        if not self.__closed:
            self.__db.close()
            self.__closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def call(self, name, arguments=None):
        """Harness entry: catches invalid method names, arguments and closed sessions."""
        methods = {key: getattr(self, key) for key in TOOL_NAMES}
        if not isinstance(name, str) or name not in methods:
            return {"ok": False, "error": {"code": "INVALID_API", "message": "unknown API"}}
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {"ok": False, "error": {"code": "INVALID_ARGUMENT", "message": "arguments must be an object"}}
        try:
            if self.__closed:
                raise ValueError("environment is closed")
            return {"ok": True, "data": methods[name](**arguments)}
        except (ValueError, TypeError, sqlite3.Error) as exc:
            return {"ok": False, "error": {"code": "INVALID_ARGUMENT", "message": str(exc)}}

    def _rows(self, sql, params=()):
        return [dict(row) for row in self.__db.execute(sql, params)]

    def list_channels(self, region):
        if region not in ("east", "west"):
            raise ValueError("region must be east or west")
        return self._rows("SELECT id AS channel_id,name,region,owner FROM channels WHERE region=? ORDER BY id", (region,))

    def get_channel_policy(self):
        return {"fee_bps": {r["id"]: r["fee_bps"] for r in self._rows("SELECT id,fee_bps FROM channels")},
                "min_orders": RULES.min_orders, "max_refund_bps": RULES.max_refund_bps,
                "require_positive_contribution": True,
                "refund_recognition": "confirmed_on <= cutoff AND status = confirmed",
                "cost_recognition": "booked_on <= cutoff AND status = booked; signed amounts",
                "fee_basis": "net_cents; half-up per channel", "currency": "CNY", "income_basis": "merchant receipts; JD uses supplier settlement, not retail GMV",
                "rates_are_synthetic": True}

    def list_orders(self, channel_ids, start, end, status="paid", cursor=0):
        self._ids(channel_ids)
        self._date(start)
        self._date(end)
        if start >= end or status not in ("paid", "cancelled") or type(cursor) is not int or cursor < 0:
            raise ValueError("invalid interval, status or cursor")
        rows = self._rows(f"SELECT * FROM orders WHERE channel_id IN ({self._marks(channel_ids)}) AND paid_on>=? AND paid_on<? AND status=? ORDER BY id LIMIT ? OFFSET ?",
                          (*channel_ids, start, end, status, RULES.page_size+1, cursor))
        return {"items": rows[:RULES.page_size], "next_cursor": cursor+RULES.page_size if len(rows)>RULES.page_size else None}

    def list_refunds(self, order_ids, as_of):
        self._ids(order_ids)
        self._date(as_of)
        return self._rows(f"SELECT * FROM refunds WHERE order_id IN ({self._marks(order_ids)}) AND confirmed_on<=? ORDER BY id", (*order_ids, as_of))

    def list_fulfillment_costs(self, order_ids, as_of):
        self._ids(order_ids)
        self._date(as_of)
        return self._rows(f"SELECT * FROM costs WHERE order_id IN ({self._marks(order_ids)}) AND booked_on<=? ORDER BY id", (*order_ids, as_of))

    def campaign_dashboard(self):
        return {"window": "2026-06", "basis": "advertising attribution, not accounting", "estimated_roas": 5.2, "impressions": 900000}

    def platform_gmv_dashboard(self):
        return {"basis": "consumer GMV before refunds, not merchant net contribution",
                "ranking": ["C03", "C04", "C02", "C05", "C01"],
                "window": "2026-06", "includes_unpaid": True}

    def inventory_snapshot(self):
        return {"sku": "DEMO-001", "available_units": 350, "warehouse": "east-1"}

    @staticmethod
    def _date(value):
        if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError("date must be YYYY-MM-DD")

    @staticmethod
    def _ids(values):
        if not isinstance(values, list) or not 1 <= len(values) <= RULES.max_batch or any(not isinstance(v, str) or not v or len(v)>80 for v in values) or len(set(values)) != len(values):
            raise ValueError("IDs must be a nonempty unique string list of at most 20 items")

    @staticmethod
    def _marks(values):
        return ",".join("?" for _ in values)


TOOL_NAMES = ("list_channels", "get_channel_policy", "list_orders", "list_refunds", "list_fulfillment_costs", "campaign_dashboard", "inventory_snapshot", "platform_gmv_dashboard")
