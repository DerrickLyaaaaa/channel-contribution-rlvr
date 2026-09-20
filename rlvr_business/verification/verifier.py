"""Final-answer-only rewards. No trajectory input, LLM, or network dependency."""
import json
from ..config import RULES, CHANNELS, METRICS, WEIGHTS, MAX_AMOUNT
from ..task import resolve_task, task_id
from .oracle import reference


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("non-finite number")


def _parse(answer, seed):
    if isinstance(answer, str):
        if len(answer.encode("utf-8")) > RULES.max_output_bytes:
            raise ValueError("answer too large")
        answer = json.loads(answer, object_pairs_hook=_unique, parse_constant=_reject_constant)
    if type(answer) is not dict or set(answer) != {"task_id", "channels", "ranking", "total_contribution_cents"}:
        raise ValueError("invalid output fields")
    if answer["task_id"] != task_id(seed):
        raise ValueError("task_id mismatch")
    rows, ranking = answer["channels"], answer["ranking"]
    if type(rows) is not list or len(rows) > len(CHANNELS):
        raise ValueError("invalid channels")
    seen = set()
    for row in rows:
        if type(row) is not dict or ("channel_id" not in row or not set(row) <= {"channel_id", "eligible", *METRICS}):
            raise ValueError("invalid channel fields")
        cid = row["channel_id"]
        if type(cid) is not str or cid not in CHANNELS or cid in seen:
            raise ValueError("unknown or duplicate channel")
        seen.add(cid)
        if ("eligible" in row and type(row["eligible"]) is not bool) or any(type(row[key]) is not int or abs(row[key]) > MAX_AMOUNT for key in METRICS if key in row):
            raise ValueError("metrics must be bounded integers; eligible must be boolean")
    if type(ranking) is not list or len(ranking) > RULES.top_k or any(type(cid) is not str or cid not in CHANNELS for cid in ranking) or len(set(ranking)) != len(ranking):
        raise ValueError("invalid ranking")
    if type(answer["total_contribution_cents"]) is not int or abs(answer["total_contribution_cents"]) > MAX_AMOUNT:
        raise ValueError("invalid total")
    return answer


def evaluate(requirement: str, final_result) -> dict:
    """Return JSON-serializable reward, success, score components and error code."""
    try:
        seed = resolve_task(requirement)
    except (ValueError, TypeError):
        return {"reward": 0.0, "success": False, "components": {}, "error": "UNKNOWN_TASK"}
    try:
        answer = _parse(final_result, seed)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return {"reward": 0.0, "success": False, "components": {}, "error": "INVALID_OUTPUT"}
    expected = reference(seed)
    actual = {row["channel_id"]: row for row in answer["channels"]}
    n = len(expected["channels"])
    metrics = sum(actual.get(row["channel_id"], {}).get(key) == row[key]
                  for row in expected["channels"] for key in METRICS) / (n * len(METRICS))
    eligibility = sum(actual.get(row["channel_id"], {}).get("eligible") is row["eligible"] for row in expected["channels"]) / n
    selection = float(set(answer["ranking"]) == set(expected["ranking"]))
    ranking = float(answer["ranking"] == expected["ranking"])
    total = float(bool(selection) and answer["total_contribution_cents"] == expected["total_contribution_cents"])
    components = {"metrics": metrics, "eligibility": eligibility, "selection": selection, "ranking": ranking, "total": total}
    success = all(value == 1 for value in components.values())
    score = 1.0 if success else sum(WEIGHTS[key] * value for key, value in components.items())
    return {"reward": score, "success": success, "components": components, "error": None}


def reward(requirement: str, final_result) -> float:
    """Stable training entry point: two inputs, float in [0, 1]."""
    return evaluate(requirement, final_result)["reward"]
