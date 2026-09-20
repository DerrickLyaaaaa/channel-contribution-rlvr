"""Synthetic fixtures only. Database stays within the trusted environment process."""
import random
import sqlite3
from ..config import CHANNEL_CATALOG


def build_database(seed: int) -> sqlite3.Connection:
    rng = random.Random(seed)
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE channels(id TEXT PRIMARY KEY, name TEXT, region TEXT, fee_bps INTEGER, owner TEXT);
    CREATE TABLE orders(id TEXT PRIMARY KEY, channel_id TEXT, paid_on TEXT, status TEXT,
                        gross_cents INTEGER, device TEXT, campaign TEXT);
    CREATE TABLE refunds(id TEXT PRIMARY KEY, order_id TEXT, confirmed_on TEXT,
                         status TEXT, amount_cents INTEGER, reason TEXT);
    CREATE TABLE costs(id TEXT PRIMARY KEY, order_id TEXT, booked_on TEXT,
                       status TEXT, amount_cents INTEGER, kind TEXT);
    """)
    channels = CHANNEL_CATALOG
    for cid, name, region, bps in channels:
        db.execute("INSERT INTO channels VALUES (?,?,?,?,?)", (cid, name, region, bps, "synthetic-owner"))
        for i in range(4):
            oid = f"{seed}-{cid}-{i}"
            gross = (10000 + rng.randrange(0, 15000)) if cid != "C04" else 7000 + rng.randrange(1000)
            cost = gross * {"C01": 45, "C02": 55, "C03": 35, "C04": 97, "C05": 50, "W01": 30}[cid] // 100
            # C05 has only two paid cohort orders; dates/status also supply distractors.
            status = "cancelled" if cid == "C05" and i >= 2 else "paid"
            db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", (oid, cid, f"2026-06-{5+i*6:02}", status, gross, "mobile", "summer"))
            db.execute("INSERT INTO costs VALUES (?,?,?,?,?,?)", (oid+"g", oid, "2026-06-29", "booked", cost, "goods"))
            db.execute("INSERT INTO costs VALUES (?,?,?,?,?,?)", (oid+"s", oid, "2026-07-02", "booked", 650, "shipping"))
            if i == 0:
                amount = gross if cid == "C03" else gross // 5
                db.execute("INSERT INTO refunds VALUES (?,?,?,?,?,?)", (oid+"r", oid, "2026-07-05", "confirmed", amount, "return"))
                db.execute("INSERT INTO costs VALUES (?,?,?,?,?,?)", (oid+"c", oid, "2026-07-08", "booked", -cost//4, "restock_credit"))
            if i == 1:
                for suffix, date, state in [("pending", "2026-07-06", "pending"), ("late", "2026-07-16", "confirmed")]:
                    db.execute("INSERT INTO refunds VALUES (?,?,?,?,?,?)", (oid+suffix, oid, date, state, 1200, "goodwill"))
                db.execute("INSERT INTO refunds VALUES (?,?,?,?,?,?)", (oid+"r1", oid, "2026-06-30", "confirmed", 101, "partial"))
                db.execute("INSERT INTO refunds VALUES (?,?,?,?,?,?)", (oid+"r2", oid, "2026-07-15", "confirmed", 202, "partial"))
                db.execute("INSERT INTO costs VALUES (?,?,?,?,?,?)", (oid+"late", oid, "2026-07-16", "booked", 9999, "adjustment"))
                db.execute("INSERT INTO costs VALUES (?,?,?,?,?,?)", (oid+"draft", oid, "2026-07-01", "draft", 8888, "adjustment"))
        for suffix, date in [("before", "2026-05-31"), ("after", "2026-07-01")]:
            oid = f"{seed}-{cid}-{suffix}"
            db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", (oid, cid, date, "paid", 99000, "desktop", "other"))
            db.execute("INSERT INTO refunds VALUES (?,?,?,?,?,?)", (oid+"r", oid, "2026-07-05", "confirmed", 88000, "return"))
    db.commit()
    return db
