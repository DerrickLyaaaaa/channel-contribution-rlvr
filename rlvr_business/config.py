"""Versioned business rules; amounts are integer cents, dates are ISO calendar dates."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Rules:
    version: str = "channel-contribution-v1"
    start: str = "2026-06-01"
    end: str = "2026-07-01"  # exclusive: order cohort
    cutoff: str = "2026-07-15"  # inclusive: accounting recognition
    region: str = "east"
    min_orders: int = 3
    max_refund_bps: int = 2000
    top_k: int = 2
    page_size: int = 5
    max_batch: int = 20
    max_seed: int = 9999
    max_output_bytes: int = 65536


RULES = Rules()
CHANNELS = ("C01", "C02", "C03", "C04", "C05")
METRICS = ("order_count", "gross_cents", "refund_cents", "net_cents",
           "cost_cents", "fee_cents", "contribution_cents")
WEIGHTS = {"metrics": 0.40, "eligibility": 0.20, "selection": 0.20, "ranking": 0.10, "total": 0.10}
MAX_AMOUNT = 10**12
CHANNEL_CATALOG = (
    ("C01", "淘宝旗舰店", "east", 300),
    ("C02", "京东自营供货", "east", 700),
    ("C03", "拼多多旗舰店", "east", 450),
    ("C04", "抖音店播", "east", 250),
    ("C05", "抖音达人带货", "east", 600),
    ("W01", "淘宝西区店", "west", 300),
)
