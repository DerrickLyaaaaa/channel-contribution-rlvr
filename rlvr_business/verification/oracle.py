"""Trusted reference computation: SQL aggregation, independent of example agent."""
from ..config import RULES
from ..environment.data import build_database
from ..task import task_id


def reference(seed):
    db = build_database(seed)
    try:
        # Aggregate each ledger BEFORE joining; avoid refunds x costs fanout.
        rows = db.execute("""
        WITH cohort AS (
          SELECT * FROM orders WHERE paid_on>=? AND paid_on<? AND status='paid'
        ), r AS (
          SELECT order_id, SUM(amount_cents) amount FROM refunds
          WHERE confirmed_on<=? AND status='confirmed' GROUP BY order_id
        ), k AS (
          SELECT order_id, SUM(amount_cents) amount FROM costs
          WHERE booked_on<=? AND status='booked' GROUP BY order_id
        )
        SELECT c.id channel_id, c.fee_bps, COUNT(o.id) order_count,
               COALESCE(SUM(o.gross_cents),0) gross_cents,
               COALESCE(SUM(r.amount),0) refund_cents,
               COALESCE(SUM(k.amount),0) cost_cents
        FROM channels c LEFT JOIN cohort o ON c.id=o.channel_id
        LEFT JOIN r ON r.order_id=o.id LEFT JOIN k ON k.order_id=o.id
        WHERE c.region=? GROUP BY c.id ORDER BY c.id
        """, (RULES.start, RULES.end, RULES.cutoff, RULES.cutoff, RULES.region)).fetchall()
        result = []
        for raw in rows:
            row = dict(raw)
            bps = row.pop("fee_bps")
            row["net_cents"] = row["gross_cents"] - row["refund_cents"]
            # Exact half-up; fixture invariant: refunds <= original receipts.
            row["fee_cents"] = (row["net_cents"] * bps + 5000) // 10000
            row["contribution_cents"] = row["net_cents"] - row["cost_cents"] - row["fee_cents"]
            row["eligible"] = (row["order_count"] >= RULES.min_orders and row["gross_cents"] > 0
                               and row["refund_cents"] * 10000 <= row["gross_cents"] * RULES.max_refund_bps
                               and row["contribution_cents"] > 0)
            result.append(row)
        selected = sorted((r for r in result if r["eligible"]), key=lambda r: (-r["contribution_cents"], r["channel_id"]))[:RULES.top_k]
        return {"task_id": task_id(seed), "channels": result, "ranking": [r["channel_id"] for r in selected],
                "total_contribution_cents": sum(r["contribution_cents"] for r in selected)}
    finally:
        db.close()
