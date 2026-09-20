"""Finite, reproducible task family. Natural language is a registered task spec."""
import re
from .config import RULES


def task_prompt(seed: int = 0) -> str:
    if type(seed) is not int or not 0 <= seed <= RULES.max_seed:
        raise ValueError("seed must be an integer in [0, 9999]")
    return f"""任务 {RULES.version}/{seed}：请为华东电商业务选择下期应优先投入的渠道。
分析 {RULES.start}（含）至 {RULES.end}（不含）的已支付订单，按 {RULES.cutoff} 日终已确认的账务重述这一订单批次。
按环境提供的渠道政策，计算所有华东渠道的订单数、实收总额、已确认退款、净收入、履约净成本、渠道费和净贡献，并判断各渠道是否达到投放门槛。
只在合格渠道中按净贡献降序选前 {RULES.top_k} 名，同额按渠道 ID 升序；不足时全部选出，并计算入选渠道净贡献合计。
所有收入按商家口径计量：京东自营供货采用商家供货结算额，其余渠道采用商家订单实收；费用为模拟费率，不代表平台真实收费。
订单数按原始已支付订单计，完全退款也计入；跨期账务归属于原订单。退款不自动冲回履约成本，只有已入账的成本贷项可冲回。
金额均为整数分；渠道费按渠道净收入乘费率，以半入方式取整到分。退款率用退款/实收，使用精确比例判断门槛。
返回 JSON 对象：task_id、channels、ranking、total_contribution_cents。
channels 每项字段为 channel_id、order_count、gross_cents、refund_cents、net_cents、cost_cents、fee_cents、contribution_cents、eligible；ranking 为渠道 ID 数组。"""


def resolve_task(requirement: str) -> int:
    if not isinstance(requirement, str) or len(requirement) > RULES.max_output_bytes:
        raise ValueError("unknown task requirement")
    match = re.match(r"任务 " + re.escape(RULES.version) + r"/(\d{1,4})：", requirement)
    if not match:
        raise ValueError("unknown task requirement")
    seed = int(match[1])
    if requirement != task_prompt(seed):
        raise ValueError("requirement must match the registered task exactly")
    return seed


def task_id(seed: int) -> str:
    return f"{RULES.version}/{seed}"
